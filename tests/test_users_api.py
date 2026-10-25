"""Tests de POST /users, GET /users y GET /users/{id}."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from alertas_climaticas.models import User
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
        assert response.json() == {"id": str(user.id), "name": "Mateo"}

    async def test_returns_the_same_data_as_the_post(self, client: AsyncClient) -> None:
        created = await client.post("/users", json={"name": "Mateo"})

        response = await client.get(f"/users/{created.json()['id']}")

        assert response.json() == created.json()

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
