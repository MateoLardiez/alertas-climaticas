"""Tests de GET /events."""

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests import factories


async def test_list_events_is_empty_when_there_are_none(client: AsyncClient) -> None:
    response = await client.get("/events")

    assert response.status_code == 200
    assert response.json() == []


async def test_list_events_returns_id_and_name(
    client: AsyncClient, session: AsyncSession
) -> None:
    event = await factories.create_event(session, "lluvia")

    response = await client.get("/events")

    assert response.status_code == 200
    assert response.json() == [{"id": str(event.id), "name": "lluvia"}]


async def test_list_events_is_sorted_by_name(client: AsyncClient, session: AsyncSession) -> None:
    for name in ["tormenta", "calor extremo", "lluvia", "helada"]:
        await factories.create_event(session, name)

    response = await client.get("/events")

    assert [event["name"] for event in response.json()] == [
        "calor extremo",
        "helada",
        "lluvia",
        "tormenta",
    ]


async def test_events_are_read_only(client: AsyncClient) -> None:
    post = await client.post("/events", json={"name": "nuevo"})
    delete = await client.delete("/events")

    assert post.status_code == 405
    assert delete.status_code == 405
