"""Modelo User: dueno de uno o mas campos. La tabla se llama users porque user es palabra reservada."""

import uuid

from sqlalchemy import func
from sqlalchemy.orm import Mapped, mapped_column

from alertas_climaticas.database.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    name: Mapped[str]
