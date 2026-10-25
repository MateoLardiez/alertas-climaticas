"""Endpoints de eventos climaticos (solo lectura: se cargan con el seed)."""

from collections.abc import Sequence

from fastapi import APIRouter

from alertas_climaticas.database.session import SessionDep
from alertas_climaticas.models import Event
from alertas_climaticas.schemas.event import EventRead
from alertas_climaticas.services import events as event_service

router = APIRouter(prefix="/events", tags=["events"])


@router.get("", response_model=list[EventRead])
async def list_events(session: SessionDep) -> Sequence[Event]:
    return await event_service.list_events(session)
