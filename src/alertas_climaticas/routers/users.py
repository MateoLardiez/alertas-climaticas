"""Endpoints de usuarios."""

import uuid
from collections.abc import Sequence

from fastapi import APIRouter, status

from alertas_climaticas.database.session import SessionDep
from alertas_climaticas.models import User
from alertas_climaticas.schemas.user import UserCreate, UserDetailRead, UserRead, UserUpdate
from alertas_climaticas.services import users as user_service

router = APIRouter(prefix="/users", tags=["users"])


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def create_user(data: UserCreate, session: SessionDep) -> User:
    return await user_service.create_user(session, data)


@router.get("", response_model=list[UserRead])
async def list_users(session: SessionDep) -> Sequence[User]:
    return await user_service.list_users(session)


@router.get(
    "/{user_id}",
    response_model=UserDetailRead,
    responses={404: {"description": "El usuario no existe"}},
)
async def get_user(user_id: uuid.UUID, session: SessionDep) -> UserDetailRead:
    return await user_service.get_user_detail(session, user_id)


@router.patch(
    "/{user_id}",
    response_model=UserRead,
    responses={404: {"description": "El usuario no existe"}},
)
async def update_user(user_id: uuid.UUID, data: UserUpdate, session: SessionDep) -> User:
    return await user_service.update_user(session, user_id, data)


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"description": "El usuario no existe"}},
)
async def delete_user(user_id: uuid.UUID, session: SessionDep) -> None:
    await user_service.delete_user(session, user_id)
