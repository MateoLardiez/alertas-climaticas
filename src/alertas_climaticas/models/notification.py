"""Modelo Notification: aviso generado por el job cuando una alerta supera su umbral en un dia."""

import uuid
from datetime import date, datetime

from sqlalchemy import DateTime, ForeignKey, SmallInteger, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from alertas_climaticas.database.base import Base


class Notification(Base):
    __tablename__ = "notification"
    __table_args__ = (
        UniqueConstraint("alert_id", "forecast_date", name="uq_notification_alert_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    alert_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("alert.id", ondelete="CASCADE"))
    forecast_date: Mapped[date]
    probability: Mapped[int] = mapped_column(SmallInteger)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
