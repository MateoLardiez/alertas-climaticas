"""Tests de la evaluacion de alertas: que notifica, cuando, y que nunca duplica."""

import asyncio
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from alertas_climaticas import seed
from alertas_climaticas.database.session import async_session_factory, engine
from alertas_climaticas.models import Alert, Event, Notification, Region, WeatherForecast
from alertas_climaticas.services.evaluation import FORECAST_WINDOW_DAYS, evaluate_alerts
from tests import factories

TODAY = date(2026, 3, 10)


def day(offset: int) -> date:
    return TODAY + timedelta(days=offset)


async def _notifications(session: AsyncSession) -> list[tuple[date, int]]:
    rows = await session.execute(
        select(Notification.forecast_date, Notification.probability).order_by(
            Notification.forecast_date
        )
    )
    return [(row.forecast_date, row.probability) for row in rows]


async def _count_notifications(session: AsyncSession) -> int:
    return await session.scalar(select(func.count()).select_from(Notification)) or 0


class Setup:
    """Un campo con una alerta de lluvia y su region, listos para recibir pronosticos."""

    def __init__(self, session: AsyncSession, region: Region, rain: Event, alert: Alert) -> None:
        self.session = session
        self.region = region
        self.rain = rain
        self.alert = alert

    @classmethod
    async def create(cls, session: AsyncSession, threshold: int = 60) -> "Setup":
        user = await factories.create_user(session)
        region = await factories.create_region(session, "Tandil")
        rain = await factories.create_event(session, "lluvia")
        farm = await factories.create_farm(session, user, region)
        alert = await factories.create_alert(session, farm, rain, threshold)
        return cls(session, region, rain, alert)

    async def forecast(self, offset: int, probability: int) -> None:
        await factories.create_forecast(
            self.session, self.region, self.rain, day(offset), probability
        )


def test_the_window_is_seven_days() -> None:
    assert FORECAST_WINDOW_DAYS == 7


class TestWhenToNotify:
    async def test_creates_a_notification_when_the_threshold_is_exceeded(
        self, session: AsyncSession
    ) -> None:
        setup = await Setup.create(session, threshold=60)
        await setup.forecast(2, 80)

        created = await evaluate_alerts(session, TODAY)

        assert created == 1
        notification = await session.scalar(select(Notification))
        assert notification is not None
        assert notification.alert_id == setup.alert.id
        assert notification.forecast_date == day(2)
        assert notification.probability == 80
        assert notification.read_at is None
        assert notification.created_at is not None

    async def test_notifies_when_the_probability_equals_the_threshold(
        self, session: AsyncSession
    ) -> None:
        setup = await Setup.create(session, threshold=60)
        await setup.forecast(1, 60)

        assert await evaluate_alerts(session, TODAY) == 1

    async def test_does_not_notify_below_the_threshold(self, session: AsyncSession) -> None:
        setup = await Setup.create(session, threshold=60)
        await setup.forecast(1, 59)

        assert await evaluate_alerts(session, TODAY) == 0
        assert await _count_notifications(session) == 0

    async def test_notifies_every_day_that_exceeds_the_threshold(
        self, session: AsyncSession
    ) -> None:
        setup = await Setup.create(session, threshold=60)
        for offset, probability in [(0, 80), (1, 40), (2, 60), (3, 100), (4, 0)]:
            await setup.forecast(offset, probability)

        created = await evaluate_alerts(session, TODAY)

        assert created == 3
        assert await _notifications(session) == [(day(0), 80), (day(2), 60), (day(3), 100)]

    async def test_threshold_zero_notifies_every_forecast_in_the_window(
        self, session: AsyncSession
    ) -> None:
        setup = await Setup.create(session, threshold=0)
        for offset in range(3):
            await setup.forecast(offset, 0)

        assert await evaluate_alerts(session, TODAY) == 3

    async def test_threshold_100_notifies_only_certain_forecasts(
        self, session: AsyncSession
    ) -> None:
        setup = await Setup.create(session, threshold=100)
        await setup.forecast(0, 99)
        await setup.forecast(1, 100)

        assert await evaluate_alerts(session, TODAY) == 1
        assert await _notifications(session) == [(day(1), 100)]


class TestTheWindow:
    async def test_covers_today_and_the_next_six_days_only(self, session: AsyncSession) -> None:
        setup = await Setup.create(session, threshold=60)
        for offset in [-1, 0, 6, 7, 8]:
            await setup.forecast(offset, 100)

        created = await evaluate_alerts(session, TODAY)

        assert created == 2
        assert [forecast_date for forecast_date, _ in await _notifications(session)] == [
            day(0),
            day(6),
        ]

    async def test_ignores_past_forecasts(self, session: AsyncSession) -> None:
        setup = await Setup.create(session, threshold=60)
        for offset in range(-5, 0):
            await setup.forecast(offset, 100)

        assert await evaluate_alerts(session, TODAY) == 0

    async def test_the_window_moves_with_the_given_date(self, session: AsyncSession) -> None:
        setup = await Setup.create(session, threshold=60)
        await setup.forecast(7, 100)

        assert await evaluate_alerts(session, TODAY) == 0
        assert await evaluate_alerts(session, day(1)) == 1


class TestWhichForecastsCount:
    async def test_ignores_forecasts_of_other_events(self, session: AsyncSession) -> None:
        setup = await Setup.create(session, threshold=60)
        frost = await factories.create_event(session, "helada")
        await factories.create_forecast(session, setup.region, frost, day(1), 100)

        assert await evaluate_alerts(session, TODAY) == 0

    async def test_ignores_forecasts_of_other_regions(self, session: AsyncSession) -> None:
        setup = await Setup.create(session, threshold=60)
        other_region = await factories.create_region(session, "Lobos")
        await factories.create_forecast(session, other_region, setup.rain, day(1), 100)

        assert await evaluate_alerts(session, TODAY) == 0

    async def test_each_alert_uses_the_forecast_of_its_own_region_and_event(
        self, session: AsyncSession
    ) -> None:
        user = await factories.create_user(session)
        tandil = await factories.create_region(session, "Tandil")
        lobos = await factories.create_region(session, "Lobos")
        rain = await factories.create_event(session, "lluvia")
        frost = await factories.create_event(session, "helada")
        farm_tandil = await factories.create_farm(session, user, tandil, "En Tandil")
        farm_lobos = await factories.create_farm(session, user, lobos, "En Lobos")
        rain_tandil = await factories.create_alert(session, farm_tandil, rain, 50)
        frost_lobos = await factories.create_alert(session, farm_lobos, frost, 50)
        await factories.create_forecast(session, tandil, rain, day(1), 70)
        await factories.create_forecast(session, tandil, frost, day(2), 100)
        await factories.create_forecast(session, lobos, rain, day(3), 100)
        await factories.create_forecast(session, lobos, frost, day(4), 90)
        rain_tandil_id, frost_lobos_id = rain_tandil.id, frost_lobos.id

        created = await evaluate_alerts(session, TODAY)

        assert created == 2
        rows = await session.execute(
            select(Notification.alert_id, Notification.forecast_date, Notification.probability)
        )
        assert {(r.alert_id, r.forecast_date, r.probability) for r in rows} == {
            (rain_tandil_id, day(1), 70),
            (frost_lobos_id, day(4), 90),
        }

    async def test_every_alert_of_a_shared_region_is_notified_separately(
        self, session: AsyncSession
    ) -> None:
        setup = await Setup.create(session, threshold=60)
        other_user = await factories.create_user(session, "Otro")
        other_farm = await factories.create_farm(session, other_user, setup.region, "Vecino")
        await factories.create_alert(session, other_farm, setup.rain, 90)
        await setup.forecast(1, 95)

        created = await evaluate_alerts(session, TODAY)

        assert created == 2
        assert await _count_notifications(session) == 2

    async def test_a_stricter_alert_in_the_same_region_is_not_notified(
        self, session: AsyncSession
    ) -> None:
        setup = await Setup.create(session, threshold=60)
        other_user = await factories.create_user(session, "Otro")
        other_farm = await factories.create_farm(session, other_user, setup.region, "Vecino")
        await factories.create_alert(session, other_farm, setup.rain, 100)
        await setup.forecast(1, 80)

        assert await evaluate_alerts(session, TODAY) == 1


class TestEmptyCases:
    async def test_returns_zero_without_alerts(self, session: AsyncSession) -> None:
        region = await factories.create_region(session)
        rain = await factories.create_event(session)
        await factories.create_forecast(session, region, rain, day(1), 100)

        assert await evaluate_alerts(session, TODAY) == 0

    async def test_returns_zero_without_forecasts(self, session: AsyncSession) -> None:
        await Setup.create(session, threshold=60)

        assert await evaluate_alerts(session, TODAY) == 0

    async def test_returns_zero_on_an_empty_database(self, session: AsyncSession) -> None:
        assert await evaluate_alerts(session, TODAY) == 0


class TestIdempotency:
    async def test_a_second_run_creates_nothing(self, session: AsyncSession) -> None:
        setup = await Setup.create(session, threshold=60)
        for offset in range(4):
            await setup.forecast(offset, 80)

        first = await evaluate_alerts(session, TODAY)
        second = await evaluate_alerts(session, TODAY)

        assert (first, second) == (4, 0)
        assert await _count_notifications(session) == 4

    async def test_a_later_run_creates_only_the_new_notifications(
        self, session: AsyncSession
    ) -> None:
        setup = await Setup.create(session, threshold=60)
        await setup.forecast(1, 80)
        await evaluate_alerts(session, TODAY)
        await setup.forecast(2, 100)

        created = await evaluate_alerts(session, TODAY)

        assert created == 1
        assert await _notifications(session) == [(day(1), 80), (day(2), 100)]

    async def test_the_next_day_only_notifies_the_day_that_entered_the_window(
        self, session: AsyncSession
    ) -> None:
        setup = await Setup.create(session, threshold=60)
        for offset in range(0, 8):
            await setup.forecast(offset, 100)

        today_run = await evaluate_alerts(session, TODAY)
        tomorrow_run = await evaluate_alerts(session, day(1))

        assert (today_run, tomorrow_run) == (7, 1)
        assert await _count_notifications(session) == 8

    async def test_a_forecast_that_changes_later_does_not_notify_again_or_change_the_snapshot(
        self, session: AsyncSession
    ) -> None:
        setup = await Setup.create(session, threshold=60)
        await setup.forecast(1, 60)
        await evaluate_alerts(session, TODAY)

        await session.execute(
            update(WeatherForecast).where(WeatherForecast.forecast_date == day(1)).values(probability=100)
        )
        await session.commit()
        created = await evaluate_alerts(session, TODAY)

        assert created == 0
        assert await _notifications(session) == [(day(1), 60)]

    async def test_a_forecast_that_drops_later_keeps_the_notification(
        self, session: AsyncSession
    ) -> None:
        setup = await Setup.create(session, threshold=60)
        await setup.forecast(1, 100)
        await evaluate_alerts(session, TODAY)

        await session.execute(update(WeatherForecast).values(probability=0))
        await session.commit()

        assert await evaluate_alerts(session, TODAY) == 0
        assert await _notifications(session) == [(day(1), 100)]

    async def test_read_notifications_stay_read(self, session: AsyncSession) -> None:
        setup = await Setup.create(session, threshold=60)
        await setup.forecast(1, 80)
        await evaluate_alerts(session, TODAY)
        read_at = datetime(2026, 3, 10, 12, 0, tzinfo=timezone.utc)
        await session.execute(update(Notification).values(read_at=read_at))
        await session.commit()

        await evaluate_alerts(session, TODAY)

        notification = await session.scalar(select(Notification))
        assert notification is not None
        await session.refresh(notification)
        assert notification.read_at == read_at

    async def test_a_new_alert_is_picked_up_by_the_next_run(self, session: AsyncSession) -> None:
        setup = await Setup.create(session, threshold=60)
        await setup.forecast(1, 80)
        await evaluate_alerts(session, TODAY)
        other_user = await factories.create_user(session, "Otro")
        other_farm = await factories.create_farm(session, other_user, setup.region, "Nuevo")
        await factories.create_alert(session, other_farm, setup.rain, 50)

        assert await evaluate_alerts(session, TODAY) == 1
        assert await _count_notifications(session) == 2


class TestConcurrency:
    async def test_simultaneous_evaluations_never_duplicate_notifications(
        self, session: AsyncSession
    ) -> None:
        user = await factories.create_user(session)
        region = await factories.create_region(session)
        events = [await factories.create_event(session, name) for name in ("lluvia", "helada")]
        for number in range(10):
            farm = await factories.create_farm(session, user, region, f"Campo {number}")
            for event in events:
                await factories.create_alert(session, farm, event, 40)
        for event in events:
            for offset in range(FORECAST_WINDOW_DAYS):
                await factories.create_forecast(session, region, event, day(offset), 80)
        expected = 10 * len(events) * FORECAST_WINDOW_DAYS
        runs = 5
        connections = [await engine.connect() for _ in range(runs)]
        for connection in connections:
            await connection.close()

        async def evaluate() -> int:
            async with async_session_factory() as other_session:
                return await evaluate_alerts(other_session, TODAY)

        created = await asyncio.gather(*(evaluate() for _ in range(runs)))

        assert sum(created) == expected
        assert await _count_notifications(session) == expected


async def test_evaluating_the_seeded_forecast_matches_an_independent_calculation(
    session: AsyncSession,
) -> None:
    await seed.seed()
    today = date.today()
    user = await factories.create_user(session)
    region = (await session.scalars(select(Region).order_by(Region.name))).first()
    assert region is not None
    farm = await factories.create_farm(session, user, region)
    threshold_by_event = {"lluvia": 60, "helada": 80, "calor extremo": 100, "tormenta": 40}
    events = {event.name: event for event in (await session.scalars(select(Event))).all()}
    for name, threshold in threshold_by_event.items():
        await factories.create_alert(session, farm, events[name], threshold)
    forecasts = await session.execute(
        select(Event.name, WeatherForecast.forecast_date, WeatherForecast.probability)
        .join(Event, Event.id == WeatherForecast.event_id)
        .where(WeatherForecast.region_id == region.id)
    )
    window_end = today + timedelta(days=FORECAST_WINDOW_DAYS - 1)
    expected = {
        (name, forecast_date)
        for name, forecast_date, probability in forecasts
        if today <= forecast_date <= window_end and probability >= threshold_by_event[name]
    }

    created = await evaluate_alerts(session, today)

    assert created == len(expected)
    assert created > 0
    assert await evaluate_alerts(session, today) == 0
