"""Modelo WeatherForecast: probabilidad de un evento climatico en una region para un dia."""

import uuid
from datetime import date

from sqlalchemy import CheckConstraint, ForeignKey, SmallInteger, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from alertas_climaticas.database.base import Base


class WeatherForecast(Base):
    __tablename__ = "weather_forecast"
    __table_args__ = (
        UniqueConstraint(
            "region_id", "event_id", "forecast_date", name="uq_weather_forecast_region_event_date"
        ),
        CheckConstraint(
            "probability BETWEEN 0 AND 100", name="ck_weather_forecast_probability_range"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    region_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("region.id"))
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("event.id"))
    forecast_date: Mapped[date]
    probability: Mapped[int] = mapped_column(SmallInteger)
