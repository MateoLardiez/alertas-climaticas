"""Tests de POST /users."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from alertas_climaticas.models import User


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


async def test_users_endpoint_does_not_accept_get(client: AsyncClient) -> None:
    response = await client.get("/users")

    assert response.status_code == 405
