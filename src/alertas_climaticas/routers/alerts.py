"""Endpoints de alertas."""

import uuid
from collections.abc import Sequence

from fastapi import APIRouter, status

from alertas_climaticas.database.session import SessionDep
from alertas_climaticas.models import Alert
from alertas_climaticas.schemas.alert import AlertCreate, AlertRead, AlertUpdate
from alertas_climaticas.services import alerts as alert_service

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.post(
    "",
    response_model=AlertRead,
    status_code=status.HTTP_201_CREATED,
    responses={
        404: {"description": "El campo o el evento no existen"},
        409: {"description": "El campo ya tiene una alerta para ese evento"},
    },
)
async def create_alert(data: AlertCreate, session: SessionDep) -> Alert:
    return await alert_service.create_alert(session, data)


@router.get("", response_model=list[AlertRead])
async def list_alerts(farm_id: uuid.UUID, session: SessionDep) -> Sequence[Alert]:
    return await alert_service.list_alerts(session, farm_id)


@router.get(
    "/{alert_id}",
    response_model=AlertRead,
    responses={404: {"description": "La alerta no existe"}},
)
async def get_alert(alert_id: uuid.UUID, session: SessionDep) -> Alert:
    return await alert_service.get_alert(session, alert_id)


@router.patch(
    "/{alert_id}",
    response_model=AlertRead,
    responses={404: {"description": "La alerta no existe"}},
)
async def update_alert(alert_id: uuid.UUID, data: AlertUpdate, session: SessionDep) -> Alert:
    return await alert_service.update_alert(session, alert_id, data)


@router.delete(
    "/{alert_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"description": "La alerta no existe"}},
)
async def delete_alert(alert_id: uuid.UUID, session: SessionDep) -> None:
    await alert_service.delete_alert(session, alert_id)
