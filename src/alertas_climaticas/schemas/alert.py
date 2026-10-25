"""Schemas de Alert: datos que entran y salen por la API."""

import uuid

from pydantic import BaseModel, ConfigDict, Field

# Entero estricto: rechaza "50", 50.5 y true, que Pydantic aceptaria por defecto.
Threshold = Field(strict=True, ge=0, le=100)


class AlertCreate(BaseModel):
    farm_id: uuid.UUID
    event_id: uuid.UUID
    threshold: int = Threshold


class AlertUpdate(BaseModel):
    """Solo el umbral es modificable: otro campo o evento seria en la practica otra alerta."""

    model_config = ConfigDict(extra="forbid")

    threshold: int = Threshold


class AlertRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    farm_id: uuid.UUID
    event_id: uuid.UUID
    threshold: int
