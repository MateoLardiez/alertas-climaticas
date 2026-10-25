"""Endpoints de notificaciones."""

import uuid

from fastapi import APIRouter

from alertas_climaticas.database.session import SessionDep
from alertas_climaticas.dependencies import TodayDep
from alertas_climaticas.schemas.notification import NotificationRead
from alertas_climaticas.services import notifications as notification_service

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=list[NotificationRead])
async def list_notifications(
    user_id: uuid.UUID, session: SessionDep, today: TodayDep, read: bool | None = None
) -> list[NotificationRead]:
    """Historial desde hoy, sin modificar nada. `read=false` deja solo las no leidas."""
    return await notification_service.list_notifications(session, user_id, today, read)


@router.post("/consume", response_model=list[NotificationRead])
async def consume_notifications(
    user_id: uuid.UUID, session: SessionDep, today: TodayDep
) -> list[NotificationRead]:
    """Devuelve las notificaciones nuevas desde hoy y las marca como leidas, en un solo paso."""
    return await notification_service.consume_notifications(session, user_id, today)
