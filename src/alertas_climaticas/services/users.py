"""Logica de usuarios."""

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from alertas_climaticas.exceptions import NotFoundError
from alertas_climaticas.models import User
from alertas_climaticas.schemas.user import UserCreate


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


async def list_users(session: AsyncSession) -> Sequence[User]:
    result = await session.scalars(select(User).order_by(User.name, User.id))
    return result.all()
