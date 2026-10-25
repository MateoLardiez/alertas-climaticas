"""Tests de los endpoints de alertas: crear, leer, listar, modificar y borrar."""

import asyncio
import uuid
from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from alertas_climaticas.database.session import engine
from alertas_climaticas.models import Alert, Event, Farm, Notification
from tests import factories

DAY = date(2026, 1, 15)


async def _farm_and_event(session: AsyncSession) -> tuple[Farm, Event]:
    user = await factories.create_user(session)
    region = await factories.create_region(session)
    farm = await factories.create_farm(session, user, region)
    event = await factories.create_event(session, "lluvia")
    return farm, event


def _payload(farm: Farm, event: Event, **overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "farm_id": str(farm.id),
        "event_id": str(event.id),
        "threshold": 60,
    }
    return base | overrides


async def _warm_up_connection_pool(size: int) -> None:
    connections = [await engine.connect() for _ in range(size)]
    for connection in connections:
        await connection.close()


async def _count(session: AsyncSession, model: type) -> int:
    return await session.scalar(select(func.count()).select_from(model)) or 0


class TestCreateAlert:
    async def test_returns_201_with_the_created_alert(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        farm, event = await _farm_and_event(session)

        response = await client.post("/alerts", json=_payload(farm, event))

        assert response.status_code == 201
        body = response.json()
        assert set(body) == {"id", "farm_id", "event_id", "threshold"}
        assert (body["farm_id"], body["event_id"], body["threshold"]) == (
            str(farm.id),
            str(event.id),
            60,
        )
        uuid.UUID(body["id"])

    async def test_is_persisted(self, client: AsyncClient, session: AsyncSession) -> None:
        farm, event = await _farm_and_event(session)

        response = await client.post("/alerts", json=_payload(farm, event, threshold=75))

        alert = await session.get(Alert, uuid.UUID(response.json()["id"]))
        assert alert is not None
        assert (alert.farm_id, alert.event_id, alert.threshold) == (farm.id, event.id, 75)

    @pytest.mark.parametrize("threshold", [0, 1, 50, 99, 100])
    async def test_accepts_thresholds_from_0_to_100(
        self, client: AsyncClient, session: AsyncSession, threshold: int
    ) -> None:
        farm, event = await _farm_and_event(session)

        response = await client.post("/alerts", json=_payload(farm, event, threshold=threshold))

        assert response.status_code == 201
        assert response.json()["threshold"] == threshold

    async def test_one_farm_can_have_alerts_for_different_events(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        farm, rain = await _farm_and_event(session)
        frost = await factories.create_event(session, "helada")

        first = await client.post("/alerts", json=_payload(farm, rain))
        second = await client.post("/alerts", json=_payload(farm, frost))

        assert first.status_code == second.status_code == 201
        assert await _count(session, Alert) == 2

    async def test_the_same_event_can_have_alerts_on_different_farms(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        farm, event = await _farm_and_event(session)
        other_user = await factories.create_user(session, "Otro")
        other_region = await factories.create_region(session, "Otra")
        other_farm = await factories.create_farm(session, other_user, other_region)

        first = await client.post("/alerts", json=_payload(farm, event))
        second = await client.post("/alerts", json=_payload(other_farm, event))

        assert first.status_code == second.status_code == 201

    async def test_ignores_a_client_supplied_id(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        farm, event = await _farm_and_event(session)
        forged_id = str(uuid.uuid4())

        response = await client.post("/alerts", json=_payload(farm, event, id=forged_id))

        assert response.status_code == 201
        assert response.json()["id"] != forged_id

    async def test_duplicate_returns_409_and_keeps_the_original(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        farm, event = await _farm_and_event(session)
        first = await client.post("/alerts", json=_payload(farm, event, threshold=40))

        second = await client.post("/alerts", json=_payload(farm, event, threshold=90))

        assert second.status_code == 409
        assert second.json() == {
            "detail": f"An alert for farm {farm.id} and event {event.id} already exists"
        }
        assert await _count(session, Alert) == 1
        original = await session.get(Alert, uuid.UUID(first.json()["id"]))
        assert original is not None
        assert original.threshold == 40

    async def test_simultaneous_duplicates_create_exactly_one_alert(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        farm, event = await _farm_and_event(session)
        requests = 5
        # Con el pool vacio, las primeras requests terminarian antes de que las demas consigan
        # conexion y nunca se superpondrian. Con conexiones listas, todas arrancan a la vez.
        await _warm_up_connection_pool(requests)

        responses = await asyncio.gather(
            *(client.post("/alerts", json=_payload(farm, event)) for _ in range(requests))
        )

        statuses = sorted(response.status_code for response in responses)
        assert statuses == [201] + [409] * (requests - 1)
        assert await _count(session, Alert) == 1

    async def test_unknown_farm_returns_404_and_saves_nothing(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        _, event = await _farm_and_event(session)
        unknown = uuid.uuid4()
        payload = {"farm_id": str(unknown), "event_id": str(event.id), "threshold": 60}

        response = await client.post("/alerts", json=payload)

        assert response.status_code == 404
        assert response.json() == {"detail": f"Farm {unknown} not found"}
        assert await _count(session, Alert) == 0

    async def test_unknown_event_returns_404_and_saves_nothing(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        farm, _ = await _farm_and_event(session)
        unknown = uuid.uuid4()
        payload = {"farm_id": str(farm.id), "event_id": str(unknown), "threshold": 60}

        response = await client.post("/alerts", json=payload)

        assert response.status_code == 404
        assert response.json() == {"detail": f"Event {unknown} not found"}
        assert await _count(session, Alert) == 0

    async def test_reports_the_farm_first_when_both_are_unknown(
        self, client: AsyncClient
    ) -> None:
        payload = {
            "farm_id": str(uuid.uuid4()),
            "event_id": str(uuid.uuid4()),
            "threshold": 60,
        }

        response = await client.post("/alerts", json=payload)

        assert response.status_code == 404
        assert response.json()["detail"].startswith("Farm")

    @pytest.mark.parametrize("field", ["farm_id", "event_id", "threshold"])
    async def test_missing_fields_return_422(
        self, client: AsyncClient, session: AsyncSession, field: str
    ) -> None:
        farm, event = await _farm_and_event(session)
        payload = _payload(farm, event)
        del payload[field]

        response = await client.post("/alerts", json=payload)

        assert response.status_code == 422
        assert await _count(session, Alert) == 0

    @pytest.mark.parametrize(
        "threshold",
        [-1, 101, 1000, "50", "abc", 50.5, 50.0, True, None, [], {}],
    )
    async def test_invalid_thresholds_return_422(
        self, client: AsyncClient, session: AsyncSession, threshold: object
    ) -> None:
        farm, event = await _farm_and_event(session)

        response = await client.post("/alerts", json=_payload(farm, event, threshold=threshold))

        assert response.status_code == 422
        assert await _count(session, Alert) == 0

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("farm_id", "no-es-un-uuid"),
            ("farm_id", 123),
            ("farm_id", None),
            ("event_id", "no-es-un-uuid"),
            ("event_id", None),
        ],
    )
    async def test_invalid_ids_return_422(
        self, client: AsyncClient, session: AsyncSession, field: str, value: object
    ) -> None:
        farm, event = await _farm_and_event(session)

        response = await client.post("/alerts", json=_payload(farm, event, **{field: value}))

        assert response.status_code == 422
        assert await _count(session, Alert) == 0


class TestGetAlert:
    async def test_returns_the_alert(self, client: AsyncClient, session: AsyncSession) -> None:
        farm, event = await _farm_and_event(session)
        alert = await factories.create_alert(session, farm, event, 70)

        response = await client.get(f"/alerts/{alert.id}")

        assert response.status_code == 200
        assert response.json() == {
            "id": str(alert.id),
            "farm_id": str(farm.id),
            "event_id": str(event.id),
            "threshold": 70,
        }

    async def test_returns_the_same_data_as_the_post(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        farm, event = await _farm_and_event(session)
        created = await client.post("/alerts", json=_payload(farm, event))

        response = await client.get(f"/alerts/{created.json()['id']}")

        assert response.json() == created.json()

    async def test_unknown_alert_returns_404(self, client: AsyncClient) -> None:
        unknown = uuid.uuid4()

        response = await client.get(f"/alerts/{unknown}")

        assert response.status_code == 404
        assert response.json() == {"detail": f"Alert {unknown} not found"}

    async def test_malformed_id_returns_422(self, client: AsyncClient) -> None:
        response = await client.get("/alerts/no-es-un-uuid")

        assert response.status_code == 422


class TestListAlerts:
    async def test_returns_only_the_alerts_of_the_farm(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        farm, event = await _farm_and_event(session)
        other_farm = await factories.create_farm(
            session, await factories.create_user(session, "Otro"), await factories.create_region(session, "Otra")
        )
        own = await factories.create_alert(session, farm, event, 30)
        await factories.create_alert(session, other_farm, event, 90)

        response = await client.get("/alerts", params={"farm_id": str(farm.id)})

        assert response.status_code == 200
        assert response.json() == [
            {
                "id": str(own.id),
                "farm_id": str(farm.id),
                "event_id": str(event.id),
                "threshold": 30,
            }
        ]

    async def test_is_sorted_by_event_name(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        farm, rain = await _farm_and_event(session)
        storm = await factories.create_event(session, "tormenta")
        frost = await factories.create_event(session, "helada")
        for event in [rain, storm, frost]:
            await factories.create_alert(session, farm, event)

        response = await client.get("/alerts", params={"farm_id": str(farm.id)})

        assert [alert["event_id"] for alert in response.json()] == [
            str(frost.id),
            str(rain.id),
            str(storm.id),
        ]

    async def test_is_empty_for_a_farm_without_alerts(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        farm, _ = await _farm_and_event(session)

        response = await client.get("/alerts", params={"farm_id": str(farm.id)})

        assert response.status_code == 200
        assert response.json() == []

    async def test_is_empty_for_an_unknown_farm(self, client: AsyncClient) -> None:
        response = await client.get("/alerts", params={"farm_id": str(uuid.uuid4())})

        assert response.status_code == 200
        assert response.json() == []

    async def test_farm_id_is_required(self, client: AsyncClient) -> None:
        response = await client.get("/alerts")

        assert response.status_code == 422

    async def test_invalid_farm_id_returns_422(self, client: AsyncClient) -> None:
        response = await client.get("/alerts", params={"farm_id": "no-es-un-uuid"})

        assert response.status_code == 422


class TestUpdateAlert:
    async def _alert(self, session: AsyncSession) -> Alert:
        farm, event = await _farm_and_event(session)
        return await factories.create_alert(session, farm, event, 50)

    async def test_updates_the_threshold(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        alert = await self._alert(session)

        response = await client.patch(f"/alerts/{alert.id}", json={"threshold": 80})

        assert response.status_code == 200
        assert response.json() == {
            "id": str(alert.id),
            "farm_id": str(alert.farm_id),
            "event_id": str(alert.event_id),
            "threshold": 80,
        }

    async def test_the_change_is_persisted(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        alert = await self._alert(session)

        await client.patch(f"/alerts/{alert.id}", json={"threshold": 80})

        await session.refresh(alert)
        assert alert.threshold == 80

    @pytest.mark.parametrize("threshold", [0, 100])
    async def test_accepts_the_boundary_thresholds(
        self, client: AsyncClient, session: AsyncSession, threshold: int
    ) -> None:
        alert = await self._alert(session)

        response = await client.patch(f"/alerts/{alert.id}", json={"threshold": threshold})

        assert response.status_code == 200
        assert response.json()["threshold"] == threshold

    async def test_unknown_alert_returns_404(self, client: AsyncClient) -> None:
        unknown = uuid.uuid4()

        response = await client.patch(f"/alerts/{unknown}", json={"threshold": 80})

        assert response.status_code == 404
        assert response.json() == {"detail": f"Alert {unknown} not found"}

    @pytest.mark.parametrize(
        "payload",
        [
            {},
            {"threshold": None},
            {"threshold": -1},
            {"threshold": 101},
            {"threshold": "80"},
            {"threshold": 80.5},
            {"threshold": True},
        ],
    )
    async def test_invalid_payloads_return_422_and_change_nothing(
        self, client: AsyncClient, session: AsyncSession, payload: dict[str, object]
    ) -> None:
        alert = await self._alert(session)

        response = await client.patch(f"/alerts/{alert.id}", json=payload)

        assert response.status_code == 422
        await session.refresh(alert)
        assert alert.threshold == 50

    @pytest.mark.parametrize("field", ["farm_id", "event_id", "id", "desconocido"])
    async def test_fields_that_cannot_be_changed_return_422(
        self, client: AsyncClient, session: AsyncSession, field: str
    ) -> None:
        alert = await self._alert(session)

        response = await client.patch(
            f"/alerts/{alert.id}", json={"threshold": 80, field: str(uuid.uuid4())}
        )

        assert response.status_code == 422
        await session.refresh(alert)
        assert alert.threshold == 50

    async def test_malformed_id_returns_422(self, client: AsyncClient) -> None:
        response = await client.patch("/alerts/no-es-un-uuid", json={"threshold": 80})

        assert response.status_code == 422


class TestDeleteAlert:
    async def test_returns_204_without_body(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        farm, event = await _farm_and_event(session)
        alert = await factories.create_alert(session, farm, event)

        response = await client.delete(f"/alerts/{alert.id}")

        assert response.status_code == 204
        assert response.content == b""

    async def test_the_alert_no_longer_exists(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        farm, event = await _farm_and_event(session)
        alert = await factories.create_alert(session, farm, event)

        await client.delete(f"/alerts/{alert.id}")

        assert (await client.get(f"/alerts/{alert.id}")).status_code == 404
        listing = await client.get("/alerts", params={"farm_id": str(farm.id)})
        assert listing.json() == []

    async def test_the_farm_can_create_the_alert_again(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        farm, event = await _farm_and_event(session)
        alert = await factories.create_alert(session, farm, event)

        await client.delete(f"/alerts/{alert.id}")
        recreated = await client.post("/alerts", json=_payload(farm, event))

        assert recreated.status_code == 201

    async def test_only_the_given_alert_is_deleted(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        farm, rain = await _farm_and_event(session)
        frost = await factories.create_event(session, "helada")
        doomed = await factories.create_alert(session, farm, rain)
        kept = await factories.create_alert(session, farm, frost)

        await client.delete(f"/alerts/{doomed.id}")

        listing = await client.get("/alerts", params={"farm_id": str(farm.id)})
        assert [alert["id"] for alert in listing.json()] == [str(kept.id)]

    async def test_deletes_its_notifications_but_not_others(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        farm, rain = await _farm_and_event(session)
        frost = await factories.create_event(session, "helada")
        doomed = await factories.create_alert(session, farm, rain)
        kept = await factories.create_alert(session, farm, frost)
        await factories.create_notification(session, doomed, DAY)
        await factories.create_notification(session, doomed, date(2026, 1, 16))
        kept_notification = await factories.create_notification(session, kept, DAY)
        kept_notification_id = kept_notification.id

        response = await client.delete(f"/alerts/{doomed.id}")

        assert response.status_code == 204
        remaining = (await session.scalars(select(Notification.id))).all()
        assert remaining == [kept_notification_id]

    async def test_deleting_twice_returns_404_the_second_time(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        farm, event = await _farm_and_event(session)
        alert = await factories.create_alert(session, farm, event)

        first = await client.delete(f"/alerts/{alert.id}")
        second = await client.delete(f"/alerts/{alert.id}")

        assert (first.status_code, second.status_code) == (204, 404)

    async def test_unknown_alert_returns_404(self, client: AsyncClient) -> None:
        unknown = uuid.uuid4()

        response = await client.delete(f"/alerts/{unknown}")

        assert response.status_code == 404
        assert response.json() == {"detail": f"Alert {unknown} not found"}

    async def test_malformed_id_returns_422(self, client: AsyncClient) -> None:
        response = await client.delete("/alerts/no-es-un-uuid")

        assert response.status_code == 422


async def test_deleting_a_farm_through_the_api_removes_its_alerts(
    client: AsyncClient, session: AsyncSession
) -> None:
    farm, event = await _farm_and_event(session)
    alert = await factories.create_alert(session, farm, event)
    alert_id = alert.id

    await client.delete(f"/farms/{farm.id}")

    assert (await client.get(f"/alerts/{alert_id}")).status_code == 404
