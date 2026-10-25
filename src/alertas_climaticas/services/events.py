"""Logica de eventos climaticos."""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from alertas_climaticas.models import Event


async def list_events(session: AsyncSession) -> Sequence[Event]:
    result = await session.scalars(select(Event).order_by(Event.name))
    return result.all()
