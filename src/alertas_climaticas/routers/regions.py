"""Endpoints de regiones (solo lectura: se cargan con el seed)."""

from collections.abc import Sequence

from fastapi import APIRouter

from alertas_climaticas.database.session import SessionDep
from alertas_climaticas.models import Region
from alertas_climaticas.schemas.region import RegionRead
from alertas_climaticas.services import regions as region_service

router = APIRouter(prefix="/regions", tags=["regions"])


@router.get("", response_model=list[RegionRead])
async def list_regions(session: SessionDep) -> Sequence[Region]:
    return await region_service.list_regions(session)
