"""Modelo Region: zona geografica a la que pertenecen los campos y para la que hay pronostico."""

import uuid

from sqlalchemy import func
from sqlalchemy.orm import Mapped, mapped_column

from alertas_climaticas.database.base import Base


class Region(Base):
    __tablename__ = "region"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    name: Mapped[str] = mapped_column(unique=True)
