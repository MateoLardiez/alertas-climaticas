"""Tests del service de notificaciones, sin pasar por HTTP."""

import asyncio
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from alertas_climaticas.database.session import async_session_factory, engine
from alertas_climaticas.models import Alert, Notification, User
from alertas_climaticas.services import notifications as notification_service
from tests import factories

TODAY = date(2026, 3, 10)


def day(offset: int) -> date:
    return TODAY + timedelta(days=offset)


async def _alert_for(session: AsyncSession, user_name: str = "Mateo") -> tuple[User, Alert]:
    user = await factories.create_user(session, user_name)
    region = await factories.create_region(session, f"Region {user_name}")
    event = await factories.create_event(session, f"lluvia {user_name}")
    farm = await factories.create_farm(session, user, region, f"Campo {user_name}")
    return user, await factories.create_alert(session, farm, event)


async def _read_ats(session: AsyncSession) -> list:
    return list((await session.scalars(select(Notification.read_at))).all())


class TestListNotifications:
    async def test_returns_notifications_with_names_and_state(self, session: AsyncSession) -> None:
        user, alert = await _alert_for(session)
        await factories.create_notification(session, alert, day(1), 70)

        result = await notification_service.list_notifications(session, user.id, TODAY)

        assert [(n.farm_name, n.event, n.probability, n.read) for n in result] == [
            ("Campo Mateo", "lluvia Mateo", 70, False)
        ]

    async def test_skips_dates_before_today_and_keeps_today(self, session: AsyncSession) -> None:
        user, alert = await _alert_for(session)
        for offset in (-1, 0, 1):
            await factories.create_notification(session, alert, day(offset))

        result = await notification_service.list_notifications(session, user.id, TODAY)

        assert [n.forecast_date for n in result] == [day(0), day(1)]

    async def test_filters_by_read_state(self, session: AsyncSession) -> None:
        user, alert = await _alert_for(session)
        await factories.create_notification(session, alert, day(1))
        await factories.create_notification(session, alert, day(2))
        await notification_service.consume_notifications(session, user.id, day(2))

        unread = await notification_service.list_notifications(session, user.id, TODAY, read=False)
        read = await notification_service.list_notifications(session, user.id, TODAY, read=True)

        assert [n.forecast_date for n in unread] == [day(1)]
        assert [n.forecast_date for n in read] == [day(2)]

    async def test_does_not_modify_anything(self, session: AsyncSession) -> None:
        user, alert = await _alert_for(session)
        await factories.create_notification(session, alert, day(1))

        await notification_service.list_notifications(session, user.id, TODAY)

        assert await _read_ats(session) == [None]

    async def test_is_empty_for_a_user_without_notifications(self, session: AsyncSession) -> None:
        user, _ = await _alert_for(session)

        assert await notification_service.list_notifications(session, user.id, TODAY) == []


class TestConsumeNotifications:
    async def test_returns_and_marks_the_unread_ones(self, session: AsyncSession) -> None:
        user, alert = await _alert_for(session)
        await factories.create_notification(session, alert, day(1))
        await factories.create_notification(session, alert, day(2))

        result = await notification_service.consume_notifications(session, user.id, TODAY)

        assert [n.forecast_date for n in result] == [day(1), day(2)]
        assert all(n.read and n.read_at is not None for n in result)
        assert all(read_at is not None for read_at in await _read_ats(session))

    async def test_commits_the_change(self, session: AsyncSession) -> None:
        user, alert = await _alert_for(session)
        await factories.create_notification(session, alert, day(1))

        await notification_service.consume_notifications(session, user.id, TODAY)

        async with async_session_factory() as other_session:
            assert all(read_at is not None for read_at in await _read_ats(other_session))

    async def test_a_second_consumption_returns_nothing(self, session: AsyncSession) -> None:
        user, alert = await _alert_for(session)
        await factories.create_notification(session, alert, day(1))

        await notification_service.consume_notifications(session, user.id, TODAY)
        second = await notification_service.consume_notifications(session, user.id, TODAY)

        assert second == []

    async def test_leaves_past_notifications_unread(self, session: AsyncSession) -> None:
        user, alert = await _alert_for(session)
        await factories.create_notification(session, alert, day(-1))

        result = await notification_service.consume_notifications(session, user.id, TODAY)

        assert result == []
        assert await _read_ats(session) == [None]

    async def test_leaves_other_users_notifications_unread(self, session: AsyncSession) -> None:
        mine, my_alert = await _alert_for(session, "Yo")
        _, other_alert = await _alert_for(session, "Otro")
        await factories.create_notification(session, my_alert, day(1))
        await factories.create_notification(session, other_alert, day(1))

        result = await notification_service.consume_notifications(session, mine.id, TODAY)

        assert len(result) == 1
        read_ats = await _read_ats(session)
        assert len(read_ats) == 2
        assert read_ats.count(None) == 1

    async def test_returns_nothing_when_there_is_nothing_to_deliver(
        self, session: AsyncSession
    ) -> None:
        user, _ = await _alert_for(session)

        assert await notification_service.consume_notifications(session, user.id, TODAY) == []

    async def test_simultaneous_consumers_split_the_notifications_without_overlap(
        self, session: AsyncSession
    ) -> None:
        user, alert = await _alert_for(session)
        for offset in range(7):
            await factories.create_notification(session, alert, day(offset))
        consumers = 5
        connections = [await engine.connect() for _ in range(consumers)]
        for connection in connections:
            await connection.close()

        async def consume() -> list[date]:
            async with async_session_factory() as other_session:
                delivered = await notification_service.consume_notifications(
                    other_session, user.id, TODAY
                )
                return [n.forecast_date for n in delivered]

        batches = await asyncio.gather(*(consume() for _ in range(consumers)))

        delivered = [forecast_date for batch in batches for forecast_date in batch]
        assert sorted(delivered) == [day(offset) for offset in range(7)]
