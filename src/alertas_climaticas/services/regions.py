"""Logica de regiones."""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from alertas_climaticas.models import Region

async def list_regions(session: AsyncSession) -> Sequence[Region]:
    result = await session.scalars(select(Region).order_by(Region.name))
    return result.all()
