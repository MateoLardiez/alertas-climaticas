"""Dependencias de FastAPI compartidas por los routers."""

from datetime import date
from typing import Annotated

from fastapi import Depends

from alertas_climaticas.clock import current_date
from alertas_climaticas.config import get_settings


def get_today() -> date:
    return current_date(get_settings().timezone)


TodayDep = Annotated[date, Depends(get_today)]
