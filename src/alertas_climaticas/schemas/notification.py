"""Schema de Notification: lo que ve el usuario, con el mensaje ya armado."""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, computed_field


class NotificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    alert_id: uuid.UUID
    farm_name: str
    event: str
    forecast_date: date
    probability: int
    read_at: datetime | None
    created_at: datetime

    @computed_field  # type: ignore[prop-decorator]
    @property
    def read(self) -> bool:
        return self.read_at is not None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def message(self) -> str:
        # No incluye el umbral: la alerta se puede editar despues y el texto quedaria inexacto.
        return (
            f"Alerta de {self.event} en {self.farm_name}: "
            f"{self.probability}% de probabilidad el {self.forecast_date:%d/%m/%Y}"
        )
