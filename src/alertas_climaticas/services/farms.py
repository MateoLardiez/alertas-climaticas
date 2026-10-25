"""Logica de campos."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from alertas_climaticas.exceptions import NotFoundError
from alertas_climaticas.models import Farm, Region, User
from alertas_climaticas.schemas.farm import FarmCreate


async def create_farm(session: AsyncSession, data: FarmCreate) -> Farm:
    if await session.get(User, data.user_id) is None:
        raise NotFoundError("User", data.user_id)
    if await session.get(Region, data.region_id) is None:
        raise NotFoundError("Region", data.region_id)

    farm = Farm(user_id=data.user_id, region_id=data.region_id, name=data.name)
    session.add(farm)
    await session.commit()
    return farm


async def get_farm(session: AsyncSession, farm_id: uuid.UUID) -> Farm:
    farm = await session.get(Farm, farm_id)
    if farm is None:
        raise NotFoundError("Farm", farm_id)
    return farm
