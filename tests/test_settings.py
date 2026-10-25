"""Tests de la configuracion por variables de entorno."""

import pytest
from pydantic import ValidationError

from alertas_climaticas.config import Settings

URL = "postgresql+asyncpg://u:p@localhost:5433/db"


def _settings(**values: object) -> Settings:
    # _env_file=None: ignora los .env, asi solo cuentan los valores del test.
    return Settings(_env_file=None, database_url=URL, **values)  # type: ignore[call-arg, arg-type]


def test_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    # El entorno de test define estas variables (.env.test): hay que quitarlas para ver los defaults.
    for name in ("TIMEZONE", "EVALUATION_JOB_ENABLED", "EVALUATION_HOUR"):
        monkeypatch.delenv(name, raising=False)

    settings = _settings()

    assert settings.timezone == "America/Argentina/Buenos_Aires"
    assert settings.evaluation_job_enabled is True
    assert settings.evaluation_hour == 6


def test_values_come_from_environment_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", URL)
    monkeypatch.setenv("TIMEZONE", "UTC")
    monkeypatch.setenv("EVALUATION_JOB_ENABLED", "false")
    monkeypatch.setenv("EVALUATION_HOUR", "22")

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.timezone == "UTC"
    assert settings.evaluation_job_enabled is False
    assert settings.evaluation_hour == 22


def test_the_database_url_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore[call-arg]


@pytest.mark.parametrize("timezone", ["No/Existe", "", "Buenos Aires", "../etc/passwd"])
def test_an_unknown_timezone_is_rejected_at_startup(timezone: str) -> None:
    with pytest.raises(ValidationError, match="timezone"):
        _settings(timezone=timezone)


@pytest.mark.parametrize("hour", [0, 6, 23])
def test_the_hour_accepts_any_hour_of_the_day(hour: int) -> None:
    assert _settings(evaluation_hour=hour).evaluation_hour == hour


@pytest.mark.parametrize("hour", [-1, 24, 25, 100])
def test_the_hour_must_be_between_0_and_23(hour: int) -> None:
    with pytest.raises(ValidationError):
        _settings(evaluation_hour=hour)


@pytest.mark.parametrize("hour", ["a la manana", 6.5, None])
def test_the_hour_must_be_a_whole_number(hour: object) -> None:
    with pytest.raises(ValidationError):
        _settings(evaluation_hour=hour)
