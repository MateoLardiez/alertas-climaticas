"""Logica de usuarios."""

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from alertas_climaticas.exceptions import NotFoundError
from alertas_climaticas.models import Farm, User
from alertas_climaticas.schemas.user import UserCreate, UserDetailRead


async def create_user(session: AsyncSession, data: UserCreate) -> User:
    user = User(name=data.name)
    session.add(user)
    await session.commit()
    return user


async def get_user(session: AsyncSession, user_id: uuid.UUID) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise NotFoundError("User", user_id)
    return user


async def get_user_detail(session: AsyncSession, user_id: uuid.UUID) -> UserDetailRead:
    user = await get_user(session, user_id)
    farm_ids = await session.scalars(
        select(Farm.id).where(Farm.user_id == user_id).order_by(Farm.name, Farm.id)
    )
    return UserDetailRead(id=user.id, name=user.name, farm_ids=list(farm_ids.all()))


async def list_users(session: AsyncSession) -> Sequence[User]:
    result = await session.scalars(select(User).order_by(User.name, User.id))
    return result.all()
