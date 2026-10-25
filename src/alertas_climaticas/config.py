"""Configuracion de la app: lee las variables de entorno (.env) en una clase tipada."""

from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    # "Hoy" es el dia calendario en esta zona: los pronosticos son por dia de los campos.
    timezone: str = "America/Argentina/Buenos_Aires"
    evaluation_job_enabled: bool = True
    # El job corre una vez por dia a esta hora (hora local de `timezone`).
    evaluation_hour: int = Field(default=6, ge=0, le=23)

    model_config = SettingsConfigDict(env_file=".env")

    @field_validator("timezone")
    @classmethod
    def timezone_must_exist(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as error:
            raise ValueError(f"unknown timezone: {value}") from error
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
