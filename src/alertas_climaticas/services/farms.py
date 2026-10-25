"""Logica de campos."""

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from alertas_climaticas.exceptions import NotFoundError
from alertas_climaticas.models import Farm, Region, User
from alertas_climaticas.schemas.farm import FarmCreate, FarmUpdate


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


async def list_farms(session: AsyncSession, user_id: uuid.UUID) -> Sequence[Farm]:
    result = await session.scalars(
        select(Farm).where(Farm.user_id == user_id).order_by(Farm.name, Farm.id)
    )
    return result.all()


async def update_farm(session: AsyncSession, farm_id: uuid.UUID, data: FarmUpdate) -> Farm:
    farm = await get_farm(session, farm_id)
    changes = data.model_dump(exclude_unset=True)

    region_id = changes.get("region_id")
    if region_id is not None and await session.get(Region, region_id) is None:
        raise NotFoundError("Region", region_id)

    for field, value in changes.items():
        setattr(farm, field, value)
    await session.commit()
    return farm


async def delete_farm(session: AsyncSession, farm_id: uuid.UUID) -> None:
    # Las alertas y notificaciones del campo se borran por ON DELETE CASCADE en la base.
    farm = await get_farm(session, farm_id)
    await session.delete(farm)
    await session.commit()
