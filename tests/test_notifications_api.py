"""Tests de GET /notifications y POST /notifications/consume."""

import asyncio
import uuid
from collections.abc import Iterator
from datetime import date, datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from alertas_climaticas.clock import current_date
from alertas_climaticas.config import get_settings
from alertas_climaticas.database.session import engine
from alertas_climaticas.dependencies import get_today
from alertas_climaticas.jobs.alert_evaluation import run_evaluation
from alertas_climaticas.main import app
from alertas_climaticas.models import Alert, Event, Farm, Notification, User
from tests import factories

TODAY = date(2026, 3, 10)


def day(offset: int) -> date:
    return TODAY + timedelta(days=offset)


@pytest.fixture
def fixed_today() -> Iterator[None]:
    """Fija "hoy" en TODAY para probar los limites de fechas sin depender del reloj."""
    app.dependency_overrides[get_today] = lambda: TODAY
    yield
    app.dependency_overrides.pop(get_today, None)


class World:
    """Un usuario con un campo y una alerta de lluvia, listo para recibir notificaciones."""

    def __init__(self, session: AsyncSession, user: User, farm: Farm, event: Event, alert: Alert):
        self.session = session
        self.user = user
        self.farm = farm
        self.event = event
        self.alert = alert

    @classmethod
    async def create(cls, session: AsyncSession, user_name: str = "Mateo") -> "World":
        user = await factories.create_user(session, user_name)
        region = await factories.create_region(session, f"Region de {user_name}")
        event = await factories.create_event(session, f"lluvia {user_name}")
        farm = await factories.create_farm(session, user, region, f"Campo de {user_name}")
        alert = await factories.create_alert(session, farm, event)
        return cls(session, user, farm, event, alert)

    async def notify(
        self, offset: int, probability: int = 80, read: bool = False
    ) -> Notification:
        notification = await factories.create_notification(
            self.session, self.alert, day(offset), probability
        )
        if read:
            await self.session.execute(
                update(Notification)
                .where(Notification.id == notification.id)
                .values(read_at=datetime(2026, 3, 9, 12, 0, tzinfo=timezone.utc))
            )
            await self.session.commit()
            await self.session.refresh(notification)
        return notification


async def _list(client: AsyncClient, user: User, **params: object) -> list[dict]:
    response = await client.get("/notifications", params={"user_id": str(user.id), **params})
    assert response.status_code == 200
    return response.json()


async def _consume(client: AsyncClient, user: User) -> list[dict]:
    response = await client.post("/notifications/consume", params={"user_id": str(user.id)})
    assert response.status_code == 200
    return response.json()


async def _read_at(session: AsyncSession, notification_id: uuid.UUID) -> datetime | None:
    return await session.scalar(
        select(Notification.read_at).where(Notification.id == notification_id)
    )


@pytest.mark.usefixtures("fixed_today")
class TestListNotifications:
    async def test_returns_the_notification_with_its_data_and_message(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        world = await World.create(session)
        notification = await world.notify(2, probability=80)

        result = await _list(client, world.user)

        assert len(result) == 1
        item = result[0]
        assert item["id"] == str(notification.id)
        assert item["alert_id"] == str(world.alert.id)
        assert item["farm_name"] == "Campo de Mateo"
        assert item["event"] == "lluvia Mateo"
        assert item["forecast_date"] == "2026-03-12"
        assert item["probability"] == 80
        assert item["read"] is False
        assert item["read_at"] is None
        assert item["created_at"]
        assert item["message"] == "Alerta de lluvia Mateo en Campo de Mateo: 80% de probabilidad el 12/03/2026"

    async def test_is_empty_without_notifications(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        world = await World.create(session)

        assert await _list(client, world.user) == []

    async def test_only_returns_the_notifications_of_the_user(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        mine = await World.create(session, "Yo")
        other = await World.create(session, "Otro")
        own = await mine.notify(1)
        await other.notify(1)

        result = await _list(client, mine.user)

        assert [item["id"] for item in result] == [str(own.id)]

    async def test_includes_notifications_of_all_the_users_farms_and_events(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        world = await World.create(session)
        second_region = await factories.create_region(session, "Otra region")
        second_event = await factories.create_event(session, "helada")
        second_farm = await factories.create_farm(session, world.user, second_region, "Segundo")
        second_alert = await factories.create_alert(session, second_farm, second_event)
        await world.notify(1)
        await factories.create_notification(session, second_alert, day(1))

        result = await _list(client, world.user)

        assert {item["farm_name"] for item in result} == {"Campo de Mateo", "Segundo"}
        assert {item["event"] for item in result} == {"lluvia Mateo", "helada"}

    async def test_is_sorted_by_date_soonest_first(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        world = await World.create(session)
        for offset in (5, 0, 3):
            await world.notify(offset)

        result = await _list(client, world.user)

        assert [item["forecast_date"] for item in result] == [
            str(day(0)),
            str(day(3)),
            str(day(5)),
        ]

    async def test_listing_does_not_mark_anything_as_read(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        world = await World.create(session)
        notification = await world.notify(1)

        await _list(client, world.user)
        await _list(client, world.user)

        assert await _read_at(session, notification.id) is None

    async def test_unknown_user_returns_an_empty_list(self, client: AsyncClient) -> None:
        response = await client.get("/notifications", params={"user_id": str(uuid.uuid4())})

        assert response.status_code == 200
        assert response.json() == []

    async def test_user_id_is_required(self, client: AsyncClient) -> None:
        assert (await client.get("/notifications")).status_code == 422

    async def test_invalid_user_id_returns_422(self, client: AsyncClient) -> None:
        response = await client.get("/notifications", params={"user_id": "no-es-un-uuid"})

        assert response.status_code == 422


@pytest.mark.usefixtures("fixed_today")
class TestListFilters:
    async def test_read_false_returns_only_unread(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        world = await World.create(session)
        unread = await world.notify(1)
        await world.notify(2, read=True)

        result = await _list(client, world.user, read="false")

        assert [item["id"] for item in result] == [str(unread.id)]

    async def test_read_true_returns_only_read(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        world = await World.create(session)
        await world.notify(1)
        read = await world.notify(2, read=True)

        result = await _list(client, world.user, read="true")

        assert [item["id"] for item in result] == [str(read.id)]
        assert result[0]["read"] is True
        assert result[0]["read_at"] is not None

    async def test_without_the_filter_returns_both(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        world = await World.create(session)
        await world.notify(1)
        await world.notify(2, read=True)

        assert len(await _list(client, world.user)) == 2

    async def test_an_invalid_read_value_returns_422(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        world = await World.create(session)

        response = await client.get(
            "/notifications", params={"user_id": str(world.user.id), "read": "tal vez"}
        )

        assert response.status_code == 422


@pytest.mark.usefixtures("fixed_today")
class TestPastNotifications:
    async def test_list_skips_days_before_today(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        world = await World.create(session)
        for offset in (-30, -2, -1):
            await world.notify(offset)

        assert await _list(client, world.user) == []

    async def test_list_includes_today_and_the_future(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        world = await World.create(session)
        for offset in (-1, 0, 1, 6):
            await world.notify(offset)

        result = await _list(client, world.user)

        assert [item["forecast_date"] for item in result] == [str(day(0)), str(day(1)), str(day(6))]

    async def test_the_cut_is_the_given_today(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        world = await World.create(session)
        await world.notify(0)
        await world.notify(1)
        app.dependency_overrides[get_today] = lambda: day(1)

        result = await _list(client, world.user)

        assert [item["forecast_date"] for item in result] == [str(day(1))]

    async def test_past_read_filters_do_not_bring_them_back(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        world = await World.create(session)
        await world.notify(-1)
        old_read = await factories.create_notification(session, world.alert, day(-3))
        await session.execute(
            update(Notification)
            .where(Notification.id == old_read.id)
            .values(read_at=datetime(2026, 3, 1, tzinfo=timezone.utc))
        )
        await session.commit()

        assert await _list(client, world.user, read="false") == []
        assert await _list(client, world.user, read="true") == []

    async def test_without_an_override_today_comes_from_the_configured_timezone(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        app.dependency_overrides.pop(get_today, None)
        world = await World.create(session)
        today = current_date(get_settings().timezone)
        for offset in (-1, 0, 1):
            await factories.create_notification(
                session, world.alert, today + timedelta(days=offset)
            )

        result = await _list(client, world.user)

        assert [item["forecast_date"] for item in result] == [
            str(today),
            str(today + timedelta(days=1)),
        ]


@pytest.mark.usefixtures("fixed_today")
class TestConsumeNotifications:
    async def test_returns_the_unread_notifications_marked_as_read(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        world = await World.create(session)
        notification = await world.notify(1, probability=100)

        result = await _consume(client, world.user)

        assert len(result) == 1
        assert result[0]["id"] == str(notification.id)
        assert result[0]["read"] is True
        assert result[0]["read_at"] is not None
        assert result[0]["message"].endswith("100% de probabilidad el 11/03/2026")

    async def test_marks_them_as_read_in_the_database(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        world = await World.create(session)
        notification = await world.notify(1)

        await _consume(client, world.user)

        assert await _read_at(session, notification.id) is not None

    async def test_a_second_call_returns_nothing(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        world = await World.create(session)
        await world.notify(1)
        await world.notify(2)

        first = await _consume(client, world.user)
        second = await _consume(client, world.user)

        assert len(first) == 2
        assert second == []

    async def test_new_notifications_arrive_in_the_next_call(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        world = await World.create(session)
        await world.notify(1)
        await _consume(client, world.user)
        fresh = await world.notify(2)

        result = await _consume(client, world.user)

        assert [item["id"] for item in result] == [str(fresh.id)]

    async def test_does_not_return_notifications_that_were_already_read(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        world = await World.create(session)
        await world.notify(1, read=True)
        unread = await world.notify(2)

        result = await _consume(client, world.user)

        assert [item["id"] for item in result] == [str(unread.id)]

    async def test_keeps_the_original_read_time_of_already_read_notifications(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        world = await World.create(session)
        read = await world.notify(1, read=True)
        read_id = read.id
        before = await _read_at(session, read_id)

        await _consume(client, world.user)

        assert before is not None
        assert await _read_at(session, read_id) == before

    async def test_is_sorted_by_date_soonest_first(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        world = await World.create(session)
        for offset in (4, 0, 2):
            await world.notify(offset)

        result = await _consume(client, world.user)

        assert [item["forecast_date"] for item in result] == [
            str(day(0)),
            str(day(2)),
            str(day(4)),
        ]

    async def test_only_consumes_the_notifications_of_the_user(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        mine = await World.create(session, "Yo")
        other = await World.create(session, "Otro")
        own = await mine.notify(1)
        foreign = await other.notify(1)

        result = await _consume(client, mine.user)

        assert [item["id"] for item in result] == [str(own.id)]
        assert await _read_at(session, foreign.id) is None

    async def test_consumed_notifications_show_as_read_in_the_listing(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        world = await World.create(session)
        await world.notify(1)

        await _consume(client, world.user)

        assert await _list(client, world.user, read="false") == []
        listed = await _list(client, world.user, read="true")
        assert len(listed) == 1
        assert listed[0]["read"] is True

    async def test_unknown_user_returns_an_empty_list(self, client: AsyncClient) -> None:
        response = await client.post(
            "/notifications/consume", params={"user_id": str(uuid.uuid4())}
        )

        assert response.status_code == 200
        assert response.json() == []

    async def test_user_id_is_required(self, client: AsyncClient) -> None:
        assert (await client.post("/notifications/consume")).status_code == 422

    async def test_invalid_user_id_returns_422(self, client: AsyncClient) -> None:
        response = await client.post("/notifications/consume", params={"user_id": "nada"})

        assert response.status_code == 422

    async def test_consuming_with_no_notifications_changes_nothing(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        world = await World.create(session)

        assert await _consume(client, world.user) == []


@pytest.mark.usefixtures("fixed_today")
class TestConsumeSkipsPastNotifications:
    async def test_does_not_return_or_touch_notifications_before_today(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        world = await World.create(session)
        old = await world.notify(-1)
        current = await world.notify(0)

        result = await _consume(client, world.user)

        assert [item["id"] for item in result] == [str(current.id)]
        assert await _read_at(session, old.id) is None

    async def test_today_is_included(self, client: AsyncClient, session: AsyncSession) -> None:
        world = await World.create(session)
        await world.notify(0)

        assert len(await _consume(client, world.user)) == 1

    async def test_a_later_today_leaves_yesterdays_unread_untouched(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        world = await World.create(session)
        pending = await world.notify(0)
        app.dependency_overrides[get_today] = lambda: day(1)

        result = await _consume(client, world.user)

        assert result == []
        assert await _read_at(session, pending.id) is None


@pytest.mark.usefixtures("fixed_today")
class TestConcurrentConsumers:
    async def test_each_notification_is_delivered_to_exactly_one_consumer(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        world = await World.create(session)
        total = 7
        for offset in range(total):
            await world.notify(offset)
        consumers = 5
        # Con el pool vacio las primeras requests terminarian antes de que las demas
        # consigan conexion y no se superpondrian; con conexiones listas arrancan juntas.
        connections = [await engine.connect() for _ in range(consumers)]
        for connection in connections:
            await connection.close()

        responses = await asyncio.gather(
            *(
                client.post("/notifications/consume", params={"user_id": str(world.user.id)})
                for _ in range(consumers)
            )
        )

        delivered = [item["id"] for response in responses for item in response.json()]
        assert all(response.status_code == 200 for response in responses)
        assert len(delivered) == total
        assert len(set(delivered)) == total


class TestFromTheJobToTheUser:
    async def test_an_alert_becomes_a_notification_the_user_receives_once(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        today = current_date(get_settings().timezone)
        user = (await client.post("/users", json={"name": "Mateo"})).json()
        region = await factories.create_region(session, "Tandil")
        event = await factories.create_event(session, "lluvia")
        farm = (
            await client.post(
                "/farms",
                json={"user_id": user["id"], "region_id": str(region.id), "name": "La Esperanza"},
            )
        ).json()
        await client.post(
            "/alerts", json={"farm_id": farm["id"], "event_id": str(event.id), "threshold": 60}
        )
        await factories.create_forecast(session, region, event, today, 80)
        await factories.create_forecast(session, region, event, today + timedelta(days=1), 40)

        created = await run_evaluation()
        first = await client.post("/notifications/consume", params={"user_id": user["id"]})
        second = await client.post("/notifications/consume", params={"user_id": user["id"]})

        assert created == 1
        assert [item["message"] for item in first.json()] == [
            f"Alerta de lluvia en La Esperanza: 80% de probabilidad el {today:%d/%m/%Y}"
        ]
        assert second.json() == []
