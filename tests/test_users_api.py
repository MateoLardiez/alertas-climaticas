"""Tests de los endpoints de usuarios: crear, listar, leer, modificar y borrar."""

import uuid
from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from alertas_climaticas.models import Alert, Farm, Notification, User
from tests import factories


async def _count_users(session: AsyncSession) -> int:
    return await session.scalar(select(func.count()).select_from(User)) or 0


async def test_create_user_returns_201_with_generated_id(client: AsyncClient) -> None:
    response = await client.post("/users", json={"name": "Mateo"})

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"id", "name"}
    assert body["name"] == "Mateo"
    uuid.UUID(body["id"])


async def test_create_user_is_persisted(client: AsyncClient, session: AsyncSession) -> None:
    response = await client.post("/users", json={"name": "Mateo"})

    user = await session.get(User, uuid.UUID(response.json()["id"]))
    assert user is not None
    assert user.name == "Mateo"


async def test_create_user_strips_whitespace(client: AsyncClient) -> None:
    response = await client.post("/users", json={"name": "  Mateo  "})

    assert response.status_code == 201
    assert response.json()["name"] == "Mateo"


async def test_create_user_accepts_unicode_names(client: AsyncClient) -> None:
    response = await client.post("/users", json={"name": "José Ñandú"})

    assert response.status_code == 201
    assert response.json()["name"] == "José Ñandú"


async def test_create_user_allows_repeated_names(client: AsyncClient) -> None:
    first = await client.post("/users", json={"name": "Mateo"})
    second = await client.post("/users", json={"name": "Mateo"})

    assert first.status_code == second.status_code == 201
    assert first.json()["id"] != second.json()["id"]


async def test_create_user_ignores_a_client_supplied_id(client: AsyncClient) -> None:
    forged_id = str(uuid.uuid4())

    response = await client.post("/users", json={"name": "Mateo", "id": forged_id})

    assert response.status_code == 201
    assert response.json()["id"] != forged_id


@pytest.mark.parametrize(
    "payload",
    [{}, {"name": ""}, {"name": "   "}, {"name": None}, {"name": 123}, {"name": ["Mateo"]}],
)
async def test_create_user_rejects_invalid_payloads(
    client: AsyncClient, session: AsyncSession, payload: dict[str, object]
) -> None:
    response = await client.post("/users", json=payload)

    assert response.status_code == 422
    assert await _count_users(session) == 0


async def test_create_user_rejects_a_request_without_json(client: AsyncClient) -> None:
    no_body = await client.post("/users")
    not_json = await client.post(
        "/users", content="no es json", headers={"Content-Type": "application/json"}
    )

    assert no_body.status_code == 422
    assert not_json.status_code == 422


class TestListUsers:
    async def test_is_empty_without_users(self, client: AsyncClient) -> None:
        response = await client.get("/users")

        assert response.status_code == 200
        assert response.json() == []

    async def test_returns_every_user_with_id_and_name(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        mateo = await factories.create_user(session, "Mateo")
        ana = await factories.create_user(session, "Ana")

        response = await client.get("/users")

        assert response.status_code == 200
        assert response.json() == [
            {"id": str(ana.id), "name": "Ana"},
            {"id": str(mateo.id), "name": "Mateo"},
        ]

    async def test_is_sorted_by_name(self, client: AsyncClient, session: AsyncSession) -> None:
        for name in ["Zeta", "Alfa", "Mitad"]:
            await factories.create_user(session, name)

        response = await client.get("/users")

        assert [user["name"] for user in response.json()] == ["Alfa", "Mitad", "Zeta"]

    async def test_includes_users_with_repeated_names(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        await factories.create_user(session, "Mateo")
        await factories.create_user(session, "Mateo")

        response = await client.get("/users")

        assert len(response.json()) == 2
        assert len({user["id"] for user in response.json()}) == 2

    async def test_includes_a_user_created_through_the_api(self, client: AsyncClient) -> None:
        created = await client.post("/users", json={"name": "Mateo"})

        listing = await client.get("/users")

        assert listing.json() == [created.json()]


class TestGetUser:
    async def test_returns_the_user(self, client: AsyncClient, session: AsyncSession) -> None:
        user = await factories.create_user(session, "Mateo")

        response = await client.get(f"/users/{user.id}")

        assert response.status_code == 200
        assert response.json() == {"id": str(user.id), "name": "Mateo", "farm_ids": []}

    async def test_returns_the_same_data_as_the_post_plus_the_farm_ids(
        self, client: AsyncClient
    ) -> None:
        created = await client.post("/users", json={"name": "Mateo"})

        response = await client.get(f"/users/{created.json()['id']}")

        assert response.json() == created.json() | {"farm_ids": []}

    async def test_includes_the_ids_of_the_users_farms_sorted_by_name(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        user = await factories.create_user(session)
        region = await factories.create_region(session)
        zeta = await factories.create_farm(session, user, region, "Zeta")
        alfa = await factories.create_farm(session, user, region, "Alfa")

        response = await client.get(f"/users/{user.id}")

        assert response.json()["farm_ids"] == [str(alfa.id), str(zeta.id)]

    async def test_does_not_include_farms_of_other_users(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        mine = await factories.create_user(session, "Yo")
        other = await factories.create_user(session, "Otro")
        region = await factories.create_region(session)
        own_farm = await factories.create_farm(session, mine, region, "Mio")
        await factories.create_farm(session, other, region, "Ajeno")

        response = await client.get(f"/users/{mine.id}")

        assert response.json()["farm_ids"] == [str(own_farm.id)]

    async def test_farm_ids_match_the_farms_listing(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        user = await factories.create_user(session)
        region = await factories.create_region(session)
        for name in ["Uno", "Dos", "Tres"]:
            await factories.create_farm(session, user, region, name)

        detail = await client.get(f"/users/{user.id}")
        listing = await client.get("/farms", params={"user_id": str(user.id)})

        assert detail.json()["farm_ids"] == [farm["id"] for farm in listing.json()]

    async def test_farm_ids_follow_the_farms_created_and_deleted_through_the_api(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        user = await factories.create_user(session)
        region = await factories.create_region(session)
        payload = {"user_id": str(user.id), "region_id": str(region.id), "name": "Campo"}

        farm = (await client.post("/farms", json=payload)).json()
        with_farm = await client.get(f"/users/{user.id}")
        await client.delete(f"/farms/{farm['id']}")
        without_farm = await client.get(f"/users/{user.id}")

        assert with_farm.json()["farm_ids"] == [farm["id"]]
        assert without_farm.json()["farm_ids"] == []

    async def test_list_and_create_do_not_include_farm_ids(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        user = await factories.create_user(session)
        region = await factories.create_region(session)
        await factories.create_farm(session, user, region)

        created = await client.post("/users", json={"name": "Nuevo"})
        listing = await client.get("/users")

        assert set(created.json()) == {"id", "name"}
        assert all(set(item) == {"id", "name"} for item in listing.json())

    async def test_returns_only_the_requested_user(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        await factories.create_user(session, "Ana")
        mateo = await factories.create_user(session, "Mateo")

        response = await client.get(f"/users/{mateo.id}")

        assert response.json()["name"] == "Mateo"

    async def test_unknown_user_returns_404(self, client: AsyncClient) -> None:
        unknown = uuid.uuid4()

        response = await client.get(f"/users/{unknown}")

        assert response.status_code == 404
        assert response.json() == {"detail": f"User {unknown} not found"}

    async def test_malformed_id_returns_422(self, client: AsyncClient) -> None:
        response = await client.get("/users/no-es-un-uuid")

        assert response.status_code == 422


class TestUpdateUser:
    async def test_updates_the_name(self, client: AsyncClient, session: AsyncSession) -> None:
        user = await factories.create_user(session, "Mateo")

        response = await client.patch(f"/users/{user.id}", json={"name": "Mateo L."})

        assert response.status_code == 200
        assert response.json() == {"id": str(user.id), "name": "Mateo L."}

    async def test_the_change_is_persisted(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        user = await factories.create_user(session, "Mateo")

        await client.patch(f"/users/{user.id}", json={"name": "Ana"})

        await session.refresh(user)
        assert user.name == "Ana"

    async def test_strips_whitespace_and_accepts_unicode(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        user = await factories.create_user(session)

        response = await client.patch(f"/users/{user.id}", json={"name": "  José Ñandú  "})

        assert response.json()["name"] == "José Ñandú"

    async def test_only_changes_the_given_user(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        user = await factories.create_user(session, "Mateo")
        other = await factories.create_user(session, "Ana")

        await client.patch(f"/users/{user.id}", json={"name": "Nuevo"})

        await session.refresh(other)
        assert other.name == "Ana"

    async def test_keeps_the_users_farms(self, client: AsyncClient, session: AsyncSession) -> None:
        user = await factories.create_user(session)
        region = await factories.create_region(session)
        farm = await factories.create_farm(session, user, region)

        await client.patch(f"/users/{user.id}", json={"name": "Nuevo"})

        detail = await client.get(f"/users/{user.id}")
        assert detail.json()["farm_ids"] == [str(farm.id)]

    async def test_unknown_user_returns_404(self, client: AsyncClient) -> None:
        unknown = uuid.uuid4()

        response = await client.patch(f"/users/{unknown}", json={"name": "Ana"})

        assert response.status_code == 404
        assert response.json() == {"detail": f"User {unknown} not found"}

    @pytest.mark.parametrize(
        "payload",
        [{}, {"name": ""}, {"name": "   "}, {"name": None}, {"name": 5}, {"name": ["Ana"]}],
    )
    async def test_invalid_payloads_return_422_and_change_nothing(
        self, client: AsyncClient, session: AsyncSession, payload: dict[str, object]
    ) -> None:
        user = await factories.create_user(session, "Mateo")

        response = await client.patch(f"/users/{user.id}", json=payload)

        assert response.status_code == 422
        await session.refresh(user)
        assert user.name == "Mateo"

    @pytest.mark.parametrize("field", ["id", "farm_ids", "desconocido"])
    async def test_fields_that_cannot_be_changed_return_422(
        self, client: AsyncClient, session: AsyncSession, field: str
    ) -> None:
        user = await factories.create_user(session, "Mateo")

        response = await client.patch(
            f"/users/{user.id}", json={"name": "Nuevo", field: str(uuid.uuid4())}
        )

        assert response.status_code == 422
        await session.refresh(user)
        assert user.name == "Mateo"

    async def test_malformed_id_returns_422(self, client: AsyncClient) -> None:
        response = await client.patch("/users/no-es-un-uuid", json={"name": "Ana"})

        assert response.status_code == 422


class TestDeleteUser:
    async def test_returns_204_without_body(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        user = await factories.create_user(session)

        response = await client.delete(f"/users/{user.id}")

        assert response.status_code == 204
        assert response.content == b""

    async def test_the_user_no_longer_exists(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        user = await factories.create_user(session)
        user_id = user.id

        await client.delete(f"/users/{user_id}")

        assert (await client.get(f"/users/{user_id}")).status_code == 404
        assert (await client.get("/users")).json() == []

    async def test_only_the_given_user_is_deleted(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        doomed = await factories.create_user(session, "A borrar")
        kept = await factories.create_user(session, "A conservar")

        await client.delete(f"/users/{doomed.id}")

        assert [user["id"] for user in (await client.get("/users")).json()] == [str(kept.id)]

    async def test_deletes_its_farms_alerts_and_notifications_but_not_others(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        doomed = await factories.create_user(session, "A borrar")
        kept = await factories.create_user(session, "A conservar")
        region = await factories.create_region(session)
        event = await factories.create_event(session)
        doomed_farm = await factories.create_farm(session, doomed, region, "Campo 1")
        another_doomed_farm = await factories.create_farm(session, doomed, region, "Campo 2")
        kept_farm = await factories.create_farm(session, kept, region)
        for farm in (doomed_farm, another_doomed_farm):
            alert = await factories.create_alert(session, farm, event)
            await factories.create_notification(session, alert, date(2026, 1, 15))
        kept_alert = await factories.create_alert(session, kept_farm, event)
        kept_notification = await factories.create_notification(
            session, kept_alert, date(2026, 1, 15)
        )
        expected = (kept_farm.id, kept_alert.id, kept_notification.id)

        response = await client.delete(f"/users/{doomed.id}")

        assert response.status_code == 204
        remaining = (
            await session.scalar(select(Farm.id)),
            await session.scalar(select(Alert.id)),
            await session.scalar(select(Notification.id)),
        )
        assert remaining == expected
        assert await _count_users(session) == 1
        for model in (Farm, Alert, Notification):
            assert await session.scalar(select(func.count()).select_from(model)) == 1

    async def test_the_farms_of_a_deleted_user_are_no_longer_reachable(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        user = await factories.create_user(session)
        region = await factories.create_region(session)
        farm = await factories.create_farm(session, user, region)
        farm_id = farm.id

        await client.delete(f"/users/{user.id}")

        assert (await client.get(f"/farms/{farm_id}")).status_code == 404

    async def test_deleting_twice_returns_404_the_second_time(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        user = await factories.create_user(session)

        first = await client.delete(f"/users/{user.id}")
        second = await client.delete(f"/users/{user.id}")

        assert (first.status_code, second.status_code) == (204, 404)

    async def test_unknown_user_returns_404(self, client: AsyncClient) -> None:
        unknown = uuid.uuid4()

        response = await client.delete(f"/users/{unknown}")

        assert response.status_code == 404
        assert response.json() == {"detail": f"User {unknown} not found"}

    async def test_malformed_id_returns_422(self, client: AsyncClient) -> None:
        response = await client.delete("/users/no-es-un-uuid")

        assert response.status_code == 422
