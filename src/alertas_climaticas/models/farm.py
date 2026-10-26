"""Modelo Farm: campo de un usuario, ubicado en una region."""

import uuid

from sqlalchemy import ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from alertas_climaticas.database.base import Base


class Farm(Base):
    __tablename__ = "farm"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    region_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("region.id", ondelete="RESTRICT"))
    name: Mapped[str]
