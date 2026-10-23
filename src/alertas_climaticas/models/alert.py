"""Modelo Alert: alerta configurada por el usuario para un evento climatico en un campo."""

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, SmallInteger, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from alertas_climaticas.database.base import Base


class Alert(Base):
    __tablename__ = "alert"
    __table_args__ = (
        UniqueConstraint("farm_id", "event_id", name="uq_alert_farm_event"),
        CheckConstraint("threshold BETWEEN 0 AND 100", name="ck_alert_threshold_range"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    farm_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("farm.id", ondelete="CASCADE"))
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("event.id"))
    threshold: Mapped[int] = mapped_column(SmallInteger)
