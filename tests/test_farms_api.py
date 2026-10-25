"""Tests de POST /farms y GET /farms/{id}."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from alertas_climaticas.models import Farm
from tests import factories


async def _valid_payload(session: AsyncSession, **overrides: object) -> dict[str, object]:
    user = await factories.create_user(session)
    region = await factories.create_region(session)
    payload: dict[str, object] = {
        "user_id": str(user.id),
        "region_id": str(region.id),
        "name": "La Esperanza",
    }
    return payload | overrides


async def _count_farms(session: AsyncSession) -> int:
    return await session.scalar(select(func.count()).select_from(Farm)) or 0


class TestCreateFarm:
    async def test_returns_201_with_the_created_farm(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        payload = await _valid_payload(session)

        response = await client.post("/farms", json=payload)

        assert response.status_code == 201
        body = response.json()
        assert set(body) == {"id", "user_id", "region_id", "name"}
        assert body["user_id"] == payload["user_id"]
        assert body["region_id"] == payload["region_id"]
        assert body["name"] == "La Esperanza"
        uuid.UUID(body["id"])

    async def test_is_persisted(self, client: AsyncClient, session: AsyncSession) -> None:
        payload = await _valid_payload(session)

        response = await client.post("/farms", json=payload)

        farm = await session.get(Farm, uuid.UUID(response.json()["id"]))
        assert farm is not None
        assert str(farm.user_id) == payload["user_id"]
        assert str(farm.region_id) == payload["region_id"]
        assert farm.name == "La Esperanza"

    async def test_strips_whitespace_from_the_name(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        payload = await _valid_payload(session, name="  La Esperanza  ")

        response = await client.post("/farms", json=payload)

        assert response.status_code == 201
        assert response.json()["name"] == "La Esperanza"

    async def test_a_user_can_have_several_farms_in_the_same_region(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        payload = await _valid_payload(session)

        first = await client.post("/farms", json=payload)
        second = await client.post("/farms", json=payload)

        assert first.status_code == second.status_code == 201
        assert first.json()["id"] != second.json()["id"]
        assert await _count_farms(session) == 2

    async def test_ignores_a_client_supplied_id(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        forged_id = str(uuid.uuid4())
        payload = await _valid_payload(session, id=forged_id)

        response = await client.post("/farms", json=payload)

        assert response.status_code == 201
        assert response.json()["id"] != forged_id

    async def test_unknown_user_returns_404_and_saves_nothing(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        unknown = uuid.uuid4()
        payload = await _valid_payload(session, user_id=str(unknown))

        response = await client.post("/farms", json=payload)

        assert response.status_code == 404
        assert response.json() == {"detail": f"User {unknown} not found"}
        assert await _count_farms(session) == 0

    async def test_unknown_region_returns_404_and_saves_nothing(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        unknown = uuid.uuid4()
        payload = await _valid_payload(session, region_id=str(unknown))

        response = await client.post("/farms", json=payload)

        assert response.status_code == 404
        assert response.json() == {"detail": f"Region {unknown} not found"}
        assert await _count_farms(session) == 0

    async def test_reports_the_user_first_when_both_are_unknown(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        payload = {
            "user_id": str(uuid.uuid4()),
            "region_id": str(uuid.uuid4()),
            "name": "Campo",
        }

        response = await client.post("/farms", json=payload)

        assert response.status_code == 404
        assert response.json()["detail"].startswith("User")

    @pytest.mark.parametrize("field", ["user_id", "region_id", "name"])
    async def test_missing_fields_return_422(
        self, client: AsyncClient, session: AsyncSession, field: str
    ) -> None:
        payload = await _valid_payload(session)
        del payload[field]

        response = await client.post("/farms", json=payload)

        assert response.status_code == 422
        assert await _count_farms(session) == 0

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("user_id", "no-es-un-uuid"),
            ("user_id", 123),
            ("user_id", None),
            ("region_id", "no-es-un-uuid"),
            ("region_id", None),
            ("name", ""),
            ("name", "   "),
            ("name", None),
            ("name", 5),
        ],
    )
    async def test_invalid_values_return_422(
        self, client: AsyncClient, session: AsyncSession, field: str, value: object
    ) -> None:
        payload = await _valid_payload(session, **{field: value})

        response = await client.post("/farms", json=payload)

        assert response.status_code == 422
        assert await _count_farms(session) == 0


class TestGetFarm:
    async def test_returns_the_farm(self, client: AsyncClient, session: AsyncSession) -> None:
        created = await client.post("/farms", json=await _valid_payload(session))

        response = await client.get(f"/farms/{created.json()['id']}")

        assert response.status_code == 200
        assert response.json() == created.json()

    async def test_unknown_farm_returns_404(self, client: AsyncClient) -> None:
        unknown = uuid.uuid4()

        response = await client.get(f"/farms/{unknown}")

        assert response.status_code == 404
        assert response.json() == {"detail": f"Farm {unknown} not found"}

    async def test_malformed_id_returns_422(self, client: AsyncClient) -> None:
        response = await client.get("/farms/no-es-un-uuid")

        assert response.status_code == 422


async def test_first_end_to_end_flow(client: AsyncClient, session: AsyncSession) -> None:
    """El primer test del paso 5: usuario, region, campo y lectura del campo."""
    await factories.create_region(session, "Tandil")

    user = (await client.post("/users", json={"name": "Mateo"})).json()
    regions = (await client.get("/regions")).json()
    farm = await client.post(
        "/farms",
        json={"user_id": user["id"], "region_id": regions[0]["id"], "name": "La Esperanza"},
    )
    fetched = await client.get(f"/farms/{farm.json()['id']}")

    assert farm.status_code == 201
    assert fetched.status_code == 200
    assert fetched.json() == {
        "id": farm.json()["id"],
        "user_id": user["id"],
        "region_id": regions[0]["id"],
        "name": "La Esperanza",
    }
