"""Fecha actual en la zona horaria configurada (la de los campos, no la del servidor)."""

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo


def current_date(timezone: str, now: datetime | None = None) -> date:
    """Dia calendario de `now` (por defecto, el instante actual) en la zona `timezone`."""
    instant = now or datetime.now(UTC)
    return instant.astimezone(ZoneInfo(timezone)).date()
