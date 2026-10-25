"""Schemas de Farm: datos que entran y salen por la API."""

import uuid
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FarmCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    user_id: uuid.UUID
    region_id: uuid.UUID
    name: str = Field(min_length=1)


class FarmUpdate(BaseModel):
    """Actualizacion parcial: solo se modifican los campos enviados. El duenio no se puede cambiar."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    name: str | None = Field(default=None, min_length=1)
    region_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def check_provided_fields(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("at least one field must be provided")
        for field in self.model_fields_set:
            if getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class FarmRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    region_id: uuid.UUID
    name: str
