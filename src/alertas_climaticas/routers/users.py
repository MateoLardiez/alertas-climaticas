"""Endpoints de usuarios."""

from fastapi import APIRouter, status

from alertas_climaticas.database.session import SessionDep
from alertas_climaticas.models import User
from alertas_climaticas.schemas.user import UserCreate, UserRead
from alertas_climaticas.services import users as user_service

router = APIRouter(prefix="/users", tags=["users"])


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def create_user(data: UserCreate, session: SessionDep) -> User:
    return await user_service.create_user(session, data)
