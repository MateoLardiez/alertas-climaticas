"""Tests de GET /farms, PATCH /farms/{id} y DELETE /farms/{id}."""

import uuid
from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from alertas_climaticas.models import Alert, Farm, Notification
from tests import factories

DAY = date(2026, 1, 15)


class TestListFarms:
    async def test_returns_only_the_farms_of_the_user(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        mine = await factories.create_user(session, "Yo")
        other = await factories.create_user(session, "Otro")
        region = await factories.create_region(session)
        own_farm = await factories.create_farm(session, mine, region, "Mio")
        await factories.create_farm(session, other, region, "Ajeno")

        response = await client.get("/farms", params={"user_id": str(mine.id)})

        assert response.status_code == 200
        assert response.json() == [
            {
                "id": str(own_farm.id),
                "user_id": str(mine.id),
                "region_id": str(region.id),
                "name": "Mio",
            }
        ]

    async def test_is_sorted_by_name(self, client: AsyncClient, session: AsyncSession) -> None:
        user = await factories.create_user(session)
        region = await factories.create_region(session)
        for name in ["Zeta", "Alfa", "Mitad"]:
            await factories.create_farm(session, user, region, name)

        response = await client.get("/farms", params={"user_id": str(user.id)})

        assert [farm["name"] for farm in response.json()] == ["Alfa", "Mitad", "Zeta"]

    async def test_includes_farms_from_different_regions(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        user = await factories.create_user(session)
        first = await factories.create_region(session, "Tandil")
        second = await factories.create_region(session, "Lobos")
        await factories.create_farm(session, user, first, "Uno")
        await factories.create_farm(session, user, second, "Dos")

        response = await client.get("/farms", params={"user_id": str(user.id)})

        assert {farm["region_id"] for farm in response.json()} == {str(first.id), str(second.id)}

    async def test_is_empty_for_a_user_without_farms(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        user = await factories.create_user(session)

        response = await client.get("/farms", params={"user_id": str(user.id)})

        assert response.status_code == 200
        assert response.json() == []

    async def test_is_empty_for_an_unknown_user(self, client: AsyncClient) -> None:
        response = await client.get("/farms", params={"user_id": str(uuid.uuid4())})

        assert response.status_code == 200
        assert response.json() == []

    async def test_user_id_is_required(self, client: AsyncClient) -> None:
        response = await client.get("/farms")

        assert response.status_code == 422

    async def test_invalid_user_id_returns_422(self, client: AsyncClient) -> None:
        response = await client.get("/farms", params={"user_id": "no-es-un-uuid"})

        assert response.status_code == 422


class TestUpdateFarm:
    async def _farm(self, session: AsyncSession) -> Farm:
        user = await factories.create_user(session)
        region = await factories.create_region(session, "Tandil")
        return await factories.create_farm(session, user, region, "Original")

    async def test_updates_the_name(self, client: AsyncClient, session: AsyncSession) -> None:
        farm = await self._farm(session)

        response = await client.patch(f"/farms/{farm.id}", json={"name": "Nuevo"})

        assert response.status_code == 200
        assert response.json() == {
            "id": str(farm.id),
            "user_id": str(farm.user_id),
            "region_id": str(farm.region_id),
            "name": "Nuevo",
        }

    async def test_the_change_is_persisted(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        farm = await self._farm(session)

        await client.patch(f"/farms/{farm.id}", json={"name": "Nuevo"})

        await session.refresh(farm)
        assert farm.name == "Nuevo"

    async def test_updates_the_region(self, client: AsyncClient, session: AsyncSession) -> None:
        farm = await self._farm(session)
        other_region = await factories.create_region(session, "Lobos")

        response = await client.patch(f"/farms/{farm.id}", json={"region_id": str(other_region.id)})

        assert response.status_code == 200
        assert response.json()["region_id"] == str(other_region.id)
        assert response.json()["name"] == "Original"

    async def test_updates_name_and_region_together(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        farm = await self._farm(session)
        other_region = await factories.create_region(session, "Lobos")

        response = await client.patch(
            f"/farms/{farm.id}", json={"name": "Nuevo", "region_id": str(other_region.id)}
        )

        assert response.json()["name"] == "Nuevo"
        assert response.json()["region_id"] == str(other_region.id)

    async def test_strips_whitespace_from_the_name(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        farm = await self._farm(session)

        response = await client.patch(f"/farms/{farm.id}", json={"name": "  Nuevo  "})

        assert response.json()["name"] == "Nuevo"

    async def test_unknown_farm_returns_404(self, client: AsyncClient) -> None:
        unknown = uuid.uuid4()

        response = await client.patch(f"/farms/{unknown}", json={"name": "Nuevo"})

        assert response.status_code == 404
        assert response.json() == {"detail": f"Farm {unknown} not found"}

    async def test_unknown_region_returns_404_and_changes_nothing(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        farm = await self._farm(session)
        unknown = uuid.uuid4()

        response = await client.patch(
            f"/farms/{farm.id}", json={"name": "Nuevo", "region_id": str(unknown)}
        )

        assert response.status_code == 404
        assert response.json() == {"detail": f"Region {unknown} not found"}
        await session.refresh(farm)
        assert farm.name == "Original"

    @pytest.mark.parametrize(
        "payload",
        [
            {},
            {"name": None},
            {"region_id": None},
            {"name": ""},
            {"name": "   "},
            {"name": 5},
            {"region_id": "no-es-un-uuid"},
        ],
    )
    async def test_invalid_payloads_return_422_and_change_nothing(
        self, client: AsyncClient, session: AsyncSession, payload: dict[str, object]
    ) -> None:
        farm = await self._farm(session)

        response = await client.patch(f"/farms/{farm.id}", json=payload)

        assert response.status_code == 422
        await session.refresh(farm)
        assert farm.name == "Original"

    @pytest.mark.parametrize("field", ["user_id", "id", "desconocido"])
    async def test_fields_that_cannot_be_changed_return_422(
        self, client: AsyncClient, session: AsyncSession, field: str
    ) -> None:
        farm = await self._farm(session)

        response = await client.patch(
            f"/farms/{farm.id}", json={"name": "Nuevo", field: str(uuid.uuid4())}
        )

        assert response.status_code == 422
        await session.refresh(farm)
        assert farm.name == "Original"

    async def test_the_owner_never_changes(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        farm = await self._farm(session)
        owner_id = farm.user_id
        intruder = await factories.create_user(session, "Intruso")

        await client.patch(f"/farms/{farm.id}", json={"user_id": str(intruder.id)})

        await session.refresh(farm)
        assert farm.user_id == owner_id

    async def test_malformed_id_returns_422(self, client: AsyncClient) -> None:
        response = await client.patch("/farms/no-es-un-uuid", json={"name": "Nuevo"})

        assert response.status_code == 422


class TestDeleteFarm:
    async def test_returns_204_without_body(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        user = await factories.create_user(session)
        region = await factories.create_region(session)
        farm = await factories.create_farm(session, user, region)

        response = await client.delete(f"/farms/{farm.id}")

        assert response.status_code == 204
        assert response.content == b""

    async def test_the_farm_no_longer_exists(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        user = await factories.create_user(session)
        region = await factories.create_region(session)
        farm = await factories.create_farm(session, user, region)

        await client.delete(f"/farms/{farm.id}")

        assert (await client.get(f"/farms/{farm.id}")).status_code == 404
        listing = await client.get("/farms", params={"user_id": str(user.id)})
        assert listing.json() == []

    async def test_only_the_given_farm_is_deleted(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        user = await factories.create_user(session)
        region = await factories.create_region(session)
        doomed = await factories.create_farm(session, user, region, "A borrar")
        kept = await factories.create_farm(session, user, region, "A conservar")

        await client.delete(f"/farms/{doomed.id}")

        listing = await client.get("/farms", params={"user_id": str(user.id)})
        assert [farm["id"] for farm in listing.json()] == [str(kept.id)]

    async def test_deleting_twice_returns_404_the_second_time(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        user = await factories.create_user(session)
        region = await factories.create_region(session)
        farm = await factories.create_farm(session, user, region)

        first = await client.delete(f"/farms/{farm.id}")
        second = await client.delete(f"/farms/{farm.id}")

        assert first.status_code == 204
        assert second.status_code == 404

    async def test_unknown_farm_returns_404(self, client: AsyncClient) -> None:
        unknown = uuid.uuid4()

        response = await client.delete(f"/farms/{unknown}")

        assert response.status_code == 404
        assert response.json() == {"detail": f"Farm {unknown} not found"}

    async def test_malformed_id_returns_422(self, client: AsyncClient) -> None:
        response = await client.delete("/farms/no-es-un-uuid")

        assert response.status_code == 422

    async def test_deletes_its_alerts_and_notifications_but_not_others(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        user = await factories.create_user(session)
        region = await factories.create_region(session)
        event = await factories.create_event(session)
        doomed = await factories.create_farm(session, user, region, "A borrar")
        kept = await factories.create_farm(session, user, region, "A conservar")
        doomed_alert = await factories.create_alert(session, doomed, event)
        kept_alert = await factories.create_alert(session, kept, event)
        await factories.create_notification(session, doomed_alert, DAY)
        await factories.create_notification(session, kept_alert, DAY)
        kept_alert_id = kept_alert.id

        response = await client.delete(f"/farms/{doomed.id}")

        assert response.status_code == 204
        alerts = (await session.scalars(select(Alert.id))).all()
        notifications = await session.scalar(select(func.count()).select_from(Notification))
        assert alerts == [kept_alert_id]
        assert notifications == 1
