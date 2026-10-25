"""Tests de GET /regions."""

import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests import factories


async def test_list_regions_is_empty_when_there_are_none(client: AsyncClient) -> None:
    response = await client.get("/regions")

    assert response.status_code == 200
    assert response.json() == []


async def test_list_regions_returns_id_and_name(
    client: AsyncClient, session: AsyncSession
) -> None:
    region = await factories.create_region(session, "Tandil")

    response = await client.get("/regions")

    assert response.status_code == 200
    assert response.json() == [{"id": str(region.id), "name": "Tandil"}]


async def test_list_regions_is_sorted_by_name(client: AsyncClient, session: AsyncSession) -> None:
    for name in ["Zeta", "Alfa", "Mitad"]:
        await factories.create_region(session, name)

    response = await client.get("/regions")

    assert [region["name"] for region in response.json()] == ["Alfa", "Mitad", "Zeta"]


async def test_list_regions_returns_every_region(
    client: AsyncClient, session: AsyncSession
) -> None:
    for number in range(25):
        await factories.create_region(session, f"Region {number:02d}")

    response = await client.get("/regions")

    body = response.json()
    assert len(body) == 25
    assert len({region["id"] for region in body}) == 25
    for region in body:
        uuid.UUID(region["id"])


async def test_regions_are_read_only(client: AsyncClient) -> None:
    post = await client.post("/regions", json={"name": "Nueva"})
    delete = await client.delete("/regions")

    assert post.status_code == 405
    assert delete.status_code == 405
