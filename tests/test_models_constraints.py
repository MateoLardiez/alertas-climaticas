"""Tests de las restricciones del esquema: checks, unicas, claves foraneas y borrados."""

import uuid
from datetime import date

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from alertas_climaticas.models import (
    Alert,
    Event,
    Farm,
    Notification,
    Region,
    User,
    WeatherForecast,
)
from tests import factories

DAY = date(2026, 1, 15)
OTHER_DAY = date(2026, 1, 16)


async def _count(session: AsyncSession, model: type) -> int:
    return await session.scalar(select(func.count()).select_from(model)) or 0


class TestPrimaryKeys:
    async def test_database_generates_uuid_ids(self, session: AsyncSession) -> None:
        region = await factories.create_region(session)
        user = await factories.create_user(session)

        assert isinstance(region.id, uuid.UUID)
        assert isinstance(user.id, uuid.UUID)
        assert region.id != user.id


class TestUniqueNames:
    async def test_region_name_must_be_unique(self, session: AsyncSession) -> None:
        await factories.create_region(session, "Tandil")

        session.add(Region(name="Tandil"))
        with pytest.raises(IntegrityError, match="region_name_key"):
            await session.commit()

    async def test_event_name_must_be_unique(self, session: AsyncSession) -> None:
        await factories.create_event(session, "lluvia")

        session.add(Event(name="lluvia"))
        with pytest.raises(IntegrityError, match="event_name_key"):
            await session.commit()

    async def test_user_names_can_repeat(self, session: AsyncSession) -> None:
        await factories.create_user(session, "Mateo")
        await factories.create_user(session, "Mateo")

        assert await _count(session, User) == 2

    @pytest.mark.parametrize("model", [Region, Event, User])
    async def test_names_are_required(self, session: AsyncSession, model: type) -> None:
        session.add(model())
        with pytest.raises(IntegrityError, match="null value in column .name."):
            await session.commit()


class TestWeatherForecast:
    @pytest.mark.parametrize("probability", [-1, 101, 1000])
    async def test_probability_out_of_range_is_rejected(
        self, session: AsyncSession, probability: int
    ) -> None:
        region = await factories.create_region(session)
        event = await factories.create_event(session)

        session.add(
            WeatherForecast(
                region_id=region.id, event_id=event.id, forecast_date=DAY, probability=probability
            )
        )
        with pytest.raises(IntegrityError, match="ck_weather_forecast_probability_range"):
            await session.commit()

    @pytest.mark.parametrize("probability", [0, 20, 100])
    async def test_probability_within_range_is_accepted(
        self, session: AsyncSession, probability: int
    ) -> None:
        region = await factories.create_region(session)
        event = await factories.create_event(session)

        forecast = await factories.create_forecast(session, region, event, DAY, probability)

        assert forecast.probability == probability

    async def test_same_region_event_and_day_is_rejected(self, session: AsyncSession) -> None:
        region = await factories.create_region(session)
        event = await factories.create_event(session)
        await factories.create_forecast(session, region, event, DAY, 20)

        session.add(
            WeatherForecast(
                region_id=region.id, event_id=event.id, forecast_date=DAY, probability=80
            )
        )
        with pytest.raises(IntegrityError, match="uq_weather_forecast_region_event_date"):
            await session.commit()

    async def test_same_event_can_repeat_on_other_days_regions_and_events(
        self, session: AsyncSession
    ) -> None:
        region = await factories.create_region(session, "Tandil")
        other_region = await factories.create_region(session, "Lobos")
        event = await factories.create_event(session, "lluvia")
        other_event = await factories.create_event(session, "helada")

        await factories.create_forecast(session, region, event, DAY, 20)
        await factories.create_forecast(session, region, event, OTHER_DAY, 20)
        await factories.create_forecast(session, other_region, event, DAY, 20)
        await factories.create_forecast(session, region, other_event, DAY, 20)

        assert await _count(session, WeatherForecast) == 4

    async def test_unknown_region_is_rejected(self, session: AsyncSession) -> None:
        event = await factories.create_event(session)

        session.add(
            WeatherForecast(
                region_id=uuid.uuid4(), event_id=event.id, forecast_date=DAY, probability=20
            )
        )
        with pytest.raises(IntegrityError, match="weather_forecast_region_id_fkey"):
            await session.commit()

    async def test_unknown_event_is_rejected(self, session: AsyncSession) -> None:
        region = await factories.create_region(session)

        session.add(
            WeatherForecast(
                region_id=region.id, event_id=uuid.uuid4(), forecast_date=DAY, probability=20
            )
        )
        with pytest.raises(IntegrityError, match="weather_forecast_event_id_fkey"):
            await session.commit()


class TestFarm:
    async def test_unknown_user_is_rejected(self, session: AsyncSession) -> None:
        region = await factories.create_region(session)

        session.add(Farm(user_id=uuid.uuid4(), region_id=region.id, name="Campo"))
        with pytest.raises(IntegrityError, match="farm_user_id_fkey"):
            await session.commit()

    async def test_unknown_region_is_rejected(self, session: AsyncSession) -> None:
        user = await factories.create_user(session)

        session.add(Farm(user_id=user.id, region_id=uuid.uuid4(), name="Campo"))
        with pytest.raises(IntegrityError, match="farm_region_id_fkey"):
            await session.commit()

    async def test_user_can_have_several_farms_in_the_same_region(
        self, session: AsyncSession
    ) -> None:
        user = await factories.create_user(session)
        region = await factories.create_region(session)

        await factories.create_farm(session, user, region, "Campo 1")
        await factories.create_farm(session, user, region, "Campo 2")

        assert await _count(session, Farm) == 2

    async def test_region_with_farms_cannot_be_deleted(self, session: AsyncSession) -> None:
        user = await factories.create_user(session)
        region = await factories.create_region(session)
        await factories.create_farm(session, user, region)

        with pytest.raises(IntegrityError, match="farm_region_id_fkey"):
            await session.execute(delete(Region).where(Region.id == region.id))

    async def test_user_with_farms_cannot_be_deleted(self, session: AsyncSession) -> None:
        user = await factories.create_user(session)
        region = await factories.create_region(session)
        await factories.create_farm(session, user, region)

        with pytest.raises(IntegrityError, match="farm_user_id_fkey"):
            await session.execute(delete(User).where(User.id == user.id))


class TestAlert:
    @pytest.fixture
    async def farm(self, session: AsyncSession) -> Farm:
        user = await factories.create_user(session)
        region = await factories.create_region(session)
        return await factories.create_farm(session, user, region)

    @pytest.mark.parametrize("threshold", [-1, 101])
    async def test_threshold_out_of_range_is_rejected(
        self, session: AsyncSession, farm: Farm, threshold: int
    ) -> None:
        event = await factories.create_event(session)

        session.add(Alert(farm_id=farm.id, event_id=event.id, threshold=threshold))
        with pytest.raises(IntegrityError, match="ck_alert_threshold_range"):
            await session.commit()

    @pytest.mark.parametrize("threshold", [0, 60, 100])
    async def test_threshold_within_range_is_accepted(
        self, session: AsyncSession, farm: Farm, threshold: int
    ) -> None:
        event = await factories.create_event(session)

        alert = await factories.create_alert(session, farm, event, threshold)

        assert alert.threshold == threshold

    async def test_one_alert_per_farm_and_event(self, session: AsyncSession, farm: Farm) -> None:
        event = await factories.create_event(session)
        await factories.create_alert(session, farm, event, 40)

        session.add(Alert(farm_id=farm.id, event_id=event.id, threshold=80))
        with pytest.raises(IntegrityError, match="uq_alert_farm_event"):
            await session.commit()

    async def test_same_event_can_have_alerts_on_different_farms(
        self, session: AsyncSession, farm: Farm
    ) -> None:
        region = await factories.create_region(session, "Otra")
        user = await factories.create_user(session, "Otro")
        other_farm = await factories.create_farm(session, user, region)
        event = await factories.create_event(session)

        await factories.create_alert(session, farm, event)
        await factories.create_alert(session, other_farm, event)

        assert await _count(session, Alert) == 2

    async def test_one_farm_can_have_alerts_for_different_events(
        self, session: AsyncSession, farm: Farm
    ) -> None:
        rain = await factories.create_event(session, "lluvia")
        frost = await factories.create_event(session, "helada")

        await factories.create_alert(session, farm, rain)
        await factories.create_alert(session, farm, frost)

        assert await _count(session, Alert) == 2

    async def test_unknown_farm_is_rejected(self, session: AsyncSession) -> None:
        event = await factories.create_event(session)

        session.add(Alert(farm_id=uuid.uuid4(), event_id=event.id, threshold=50))
        with pytest.raises(IntegrityError, match="alert_farm_id_fkey"):
            await session.commit()

    async def test_unknown_event_is_rejected(self, session: AsyncSession, farm: Farm) -> None:
        session.add(Alert(farm_id=farm.id, event_id=uuid.uuid4(), threshold=50))
        with pytest.raises(IntegrityError, match="alert_event_id_fkey"):
            await session.commit()

    async def test_event_with_alerts_cannot_be_deleted(
        self, session: AsyncSession, farm: Farm
    ) -> None:
        event = await factories.create_event(session)
        await factories.create_alert(session, farm, event)

        with pytest.raises(IntegrityError, match="alert_event_id_fkey"):
            await session.execute(delete(Event).where(Event.id == event.id))


class TestNotification:
    @pytest.fixture
    async def alert(self, session: AsyncSession) -> Alert:
        user = await factories.create_user(session)
        region = await factories.create_region(session)
        farm = await factories.create_farm(session, user, region)
        event = await factories.create_event(session)
        return await factories.create_alert(session, farm, event)

    async def test_defaults_are_unread_and_timestamped(
        self, session: AsyncSession, alert: Alert
    ) -> None:
        notification = await factories.create_notification(session, alert, DAY)

        assert notification.read_at is None
        assert notification.created_at is not None
        assert notification.created_at.tzinfo is not None

    async def test_one_notification_per_alert_and_day(
        self, session: AsyncSession, alert: Alert
    ) -> None:
        await factories.create_notification(session, alert, DAY, 80)

        session.add(Notification(alert_id=alert.id, forecast_date=DAY, probability=100))
        with pytest.raises(IntegrityError, match="uq_notification_alert_date"):
            await session.commit()

    async def test_same_alert_can_notify_on_different_days(
        self, session: AsyncSession, alert: Alert
    ) -> None:
        await factories.create_notification(session, alert, DAY)
        await factories.create_notification(session, alert, OTHER_DAY)

        assert await _count(session, Notification) == 2

    async def test_unknown_alert_is_rejected(self, session: AsyncSession) -> None:
        session.add(Notification(alert_id=uuid.uuid4(), forecast_date=DAY, probability=80))
        with pytest.raises(IntegrityError, match="notification_alert_id_fkey"):
            await session.commit()


class TestCascadeDeletes:
    async def test_deleting_a_farm_deletes_its_alerts_and_notifications(
        self, session: AsyncSession
    ) -> None:
        user = await factories.create_user(session)
        region = await factories.create_region(session)
        event = await factories.create_event(session)
        farm = await factories.create_farm(session, user, region, "A borrar")
        kept_farm = await factories.create_farm(session, user, region, "A conservar")
        alert = await factories.create_alert(session, farm, event)
        kept_alert = await factories.create_alert(session, kept_farm, event)
        await factories.create_notification(session, alert, DAY)
        await factories.create_notification(session, alert, OTHER_DAY)
        await factories.create_notification(session, kept_alert, DAY)

        await session.execute(delete(Farm).where(Farm.id == farm.id))
        await session.commit()

        assert await _count(session, Farm) == 1
        assert await _count(session, Alert) == 1
        assert await _count(session, Notification) == 1
        assert await session.scalar(select(Alert.id)) == kept_alert.id

    async def test_deleting_an_alert_deletes_its_notifications(
        self, session: AsyncSession
    ) -> None:
        user = await factories.create_user(session)
        region = await factories.create_region(session)
        event = await factories.create_event(session)
        farm = await factories.create_farm(session, user, region)
        alert = await factories.create_alert(session, farm, event)
        await factories.create_notification(session, alert, DAY)

        await session.execute(delete(Alert).where(Alert.id == alert.id))
        await session.commit()

        assert await _count(session, Farm) == 1
        assert await _count(session, Notification) == 0
