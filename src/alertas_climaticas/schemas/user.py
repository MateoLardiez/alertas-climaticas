"""Schemas de User: datos que entran y salen por la API."""

import uuid

from pydantic import BaseModel, ConfigDict

from alertas_climaticas.schemas.fields import Name


class UserCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: Name


class UserUpdate(BaseModel):
    """Solo se puede cambiar el nombre. Cualquier otro campo se rechaza con 422."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    name: Name


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str


class UserDetailRead(UserRead):
    """Detalle de un usuario: ademas de sus datos, los ids de sus campos."""

    farm_ids: list[uuid.UUID]
