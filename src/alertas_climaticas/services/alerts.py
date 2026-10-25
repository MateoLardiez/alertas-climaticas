"""Logica de alertas."""

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from alertas_climaticas.exceptions import AlreadyExistsError, NotFoundError
from alertas_climaticas.models import Alert, Event, Farm
from alertas_climaticas.schemas.alert import AlertCreate, AlertUpdate


async def create_alert(session: AsyncSession, data: AlertCreate) -> Alert:
    if await session.get(Farm, data.farm_id) is None:
        raise NotFoundError("Farm", data.farm_id)
    if await session.get(Event, data.event_id) is None:
        raise NotFoundError("Event", data.event_id)

    # ON CONFLICT DO NOTHING deja que la base decida de forma atomica si la alerta ya existe.
    # Un SELECT previo no alcanza: dos requests simultaneas podrian pasarlo a la vez.
    result = await session.scalars(
        insert(Alert)
        .values(farm_id=data.farm_id, event_id=data.event_id, threshold=data.threshold)
        .on_conflict_do_nothing(constraint="uq_alert_farm_event")
        .returning(Alert)
    )
    alert = result.one_or_none()
    if alert is None:
        raise AlreadyExistsError(
            f"An alert for farm {data.farm_id} and event {data.event_id} already exists"
        )
    await session.commit()
    return alert


async def get_alert(session: AsyncSession, alert_id: uuid.UUID) -> Alert:
    alert = await session.get(Alert, alert_id)
    if alert is None:
        raise NotFoundError("Alert", alert_id)
    return alert


async def list_alerts(session: AsyncSession, farm_id: uuid.UUID) -> Sequence[Alert]:
    result = await session.scalars(
        select(Alert)
        .join(Event, Event.id == Alert.event_id)
        .where(Alert.farm_id == farm_id)
        .order_by(Event.name, Alert.id)
    )
    return result.all()


async def update_alert(session: AsyncSession, alert_id: uuid.UUID, data: AlertUpdate) -> Alert:
    alert = await get_alert(session, alert_id)
    alert.threshold = data.threshold
    await session.commit()
    return alert


async def delete_alert(session: AsyncSession, alert_id: uuid.UUID) -> None:
    # Las notificaciones de la alerta se borran por ON DELETE CASCADE en la base.
    alert = await get_alert(session, alert_id)
    await session.delete(alert)
    await session.commit()
