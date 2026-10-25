"""Logica de notificaciones: consulta del historial y entrega de las nuevas."""

import uuid
from datetime import date

from sqlalchemy import Select, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from alertas_climaticas.models import Alert, Event, Farm, Notification
from alertas_climaticas.schemas.notification import NotificationRead


def _notifications_query() -> Select:
    """Notificaciones con el nombre del campo y del evento, de la mas proxima a la mas lejana."""
    return (
        select(
            Notification.id,
            Notification.alert_id,
            Farm.name.label("farm_name"),
            Event.name.label("event"),
            Notification.forecast_date,
            Notification.probability,
            Notification.read_at,
            Notification.created_at,
        )
        .select_from(Notification)
        .join(Alert, Alert.id == Notification.alert_id)
        .join(Farm, Farm.id == Alert.farm_id)
        .join(Event, Event.id == Alert.event_id)
        .order_by(Notification.forecast_date, Event.name, Notification.id)
    )


async def list_notifications(
    session: AsyncSession, user_id: uuid.UUID, today: date, read: bool | None = None
) -> list[NotificationRead]:
    """Historial del usuario desde `today` (inclusive). No modifica nada."""
    query = _notifications_query().where(
        Farm.user_id == user_id, Notification.forecast_date >= today
    )
    if read is not None:
        query = query.where(
            Notification.read_at.is_not(None) if read else Notification.read_at.is_(None)
        )
    rows = await session.execute(query)
    return [NotificationRead.model_validate(row) for row in rows]


async def consume_notifications(
    session: AsyncSession, user_id: uuid.UUID, today: date
) -> list[NotificationRead]:
    """Entrega las notificaciones sin leer del usuario desde `today` y las marca como leidas.

    Es un solo UPDATE: si dos consumidores piden a la vez, PostgreSQL le entrega cada
    notificacion a uno solo. Las vencidas (anteriores a `today`) no se devuelven ni se tocan.
    """
    marked = await session.scalars(
        update(Notification)
        .where(
            Notification.read_at.is_(None),
            Notification.forecast_date >= today,
            Notification.alert_id.in_(
                select(Alert.id)
                .join(Farm, Farm.id == Alert.farm_id)
                .where(Farm.user_id == user_id)
            ),
        )
        .values(read_at=func.now())
        .returning(Notification.id)
        .execution_options(synchronize_session=False)
    )
    rows = await session.execute(_notifications_query().where(Notification.id.in_(marked.all())))
    notifications = [NotificationRead.model_validate(row) for row in rows]
    await session.commit()
    return notifications
