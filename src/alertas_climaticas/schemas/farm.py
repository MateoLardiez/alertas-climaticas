"""Schemas de Farm: datos que entran y salen por la API."""

import uuid

from pydantic import BaseModel, ConfigDict, Field


class FarmCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    user_id: uuid.UUID
    region_id: uuid.UUID
    name: str = Field(min_length=1)


class FarmRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    region_id: uuid.UUID
    name: str
