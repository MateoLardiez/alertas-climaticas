"""Configuracion de la app: lee las variables de entorno (.env) en una clase tipada."""

from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


class Settings(BaseSettings):
    db_host: str = "localhost"
    db_port: int = Field(default=5432, ge=1, le=65535)
    db_user: str
    db_password: str
    db_name: str
    # "Hoy" es el dia calendario en esta zona: los pronosticos son por dia de los campos.
    timezone: str = "America/Argentina/Buenos_Aires"
    evaluation_job_enabled: bool = True
    # El job corre una vez por dia a esta hora (hora local de `timezone`).
    evaluation_hour: int = Field(default=6, ge=0, le=23)

    # extra="ignore": el .env tambien tiene variables que lee otra cosa (HOST y PORT de uvicorn).
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def database_url(self) -> URL:
        # URL.create escapa los caracteres especiales (@, /, %) de la contrasena.
        return URL.create(
            "postgresql+asyncpg",
            username=self.db_user,
            password=self.db_password,
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
        )

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
