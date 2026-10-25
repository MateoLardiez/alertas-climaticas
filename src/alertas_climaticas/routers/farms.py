"""Endpoints de campos."""

import uuid
from collections.abc import Sequence

from fastapi import APIRouter, status

from alertas_climaticas.database.session import SessionDep
from alertas_climaticas.models import Farm
from alertas_climaticas.schemas.farm import FarmCreate, FarmRead, FarmUpdate
from alertas_climaticas.services import farms as farm_service

router = APIRouter(prefix="/farms", tags=["farms"])


@router.post(
    "",
    response_model=FarmRead,
    status_code=status.HTTP_201_CREATED,
    responses={404: {"description": "El usuario o la region no existen"}},
)
async def create_farm(data: FarmCreate, session: SessionDep) -> Farm:
    return await farm_service.create_farm(session, data)


@router.get("", response_model=list[FarmRead])
async def list_farms(user_id: uuid.UUID, session: SessionDep) -> Sequence[Farm]:
    return await farm_service.list_farms(session, user_id)


@router.get(
    "/{farm_id}",
    response_model=FarmRead,
    responses={404: {"description": "El campo no existe"}},
)
async def get_farm(farm_id: uuid.UUID, session: SessionDep) -> Farm:
    return await farm_service.get_farm(session, farm_id)


@router.patch(
    "/{farm_id}",
    response_model=FarmRead,
    responses={404: {"description": "El campo o la region no existen"}},
)
async def update_farm(farm_id: uuid.UUID, data: FarmUpdate, session: SessionDep) -> Farm:
    return await farm_service.update_farm(session, farm_id, data)


@router.delete(
    "/{farm_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"description": "El campo no existe"}},
)
async def delete_farm(farm_id: uuid.UUID, session: SessionDep) -> None:
    await farm_service.delete_farm(session, farm_id)
