"""Modelo Event: tipo de evento climatico (lluvia, helada, tormenta, calor extremo)."""

import uuid

from sqlalchemy import func
from sqlalchemy.orm import Mapped, mapped_column

from alertas_climaticas.database.base import Base


class Event(Base):
    __tablename__ = "event"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    name: Mapped[str] = mapped_column(unique=True)
