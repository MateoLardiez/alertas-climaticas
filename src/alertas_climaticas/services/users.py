"""Logica de usuarios."""

from sqlalchemy.ext.asyncio import AsyncSession

from alertas_climaticas.models import User
from alertas_climaticas.schemas.user import UserCreate

async def create_user(session: AsyncSession, data: UserCreate) -> User:
    user = User(name=data.name)
    session.add(user)
    await session.commit()
    return user
