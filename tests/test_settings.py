"""Tests de la configuracion por variables de entorno."""

from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy.engine import make_url

from alertas_climaticas.config import Settings

DB = {"db_user": "u", "db_password": "p", "db_name": "db"}


def _settings(**values: object) -> Settings:
    # _env_file=None: ignora los .env, asi solo cuentan los valores del test.
    return Settings(_env_file=None, **{**DB, **values})  # type: ignore[call-arg, arg-type]


def test_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    # El entorno de test define estas variables (.env.test): hay que quitarlas para ver los defaults.
    for name in ("TIMEZONE", "EVALUATION_JOB_ENABLED", "EVALUATION_HOUR", "DB_HOST", "DB_PORT"):
        monkeypatch.delenv(name, raising=False)

    settings = _settings()

    assert settings.timezone == "America/Argentina/Buenos_Aires"
    assert settings.evaluation_job_enabled is True
    assert settings.evaluation_hour == 6
    assert settings.db_host == "localhost"
    assert settings.db_port == 5432


def test_values_come_from_environment_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DB_HOST", "db")
    monkeypatch.setenv("DB_PORT", "5433")
    monkeypatch.setenv("DB_USER", "alertas")
    monkeypatch.setenv("DB_PASSWORD", "secreto")
    monkeypatch.setenv("DB_NAME", "alertas")
    monkeypatch.setenv("TIMEZONE", "UTC")
    monkeypatch.setenv("EVALUATION_JOB_ENABLED", "false")
    monkeypatch.setenv("EVALUATION_HOUR", "22")

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.timezone == "UTC"
    assert settings.evaluation_job_enabled is False
    assert settings.evaluation_hour == 22
    assert settings.database_url.render_as_string(hide_password=False) == (
        "postgresql+asyncpg://alertas:secreto@db:5433/alertas"
    )


@pytest.mark.parametrize("name", ["DB_USER", "DB_PASSWORD", "DB_NAME"])
def test_the_database_credentials_are_required(
    monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    for var, value in {"DB_USER": "u", "DB_PASSWORD": "p", "DB_NAME": "db"}.items():
        monkeypatch.setenv(var, value)
    monkeypatch.delenv(name)

    with pytest.raises(ValidationError, match=name.lower()):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_special_characters_in_the_password_are_escaped_in_the_url() -> None:
    settings = _settings(db_password="p@ss/w%rd:1")

    url = settings.database_url
    assert url.password == "p@ss/w%rd:1"
    # Re-parseada, la URL conserva host y base: la contrasena no la rompe.
    parsed = make_url(url.render_as_string(hide_password=False))
    assert (parsed.password, parsed.host, parsed.database) == ("p@ss/w%rd:1", "localhost", "db")


@pytest.mark.parametrize("port", [0, 65536, -1])
def test_the_database_port_must_be_a_valid_port(port: int) -> None:
    with pytest.raises(ValidationError):
        _settings(db_port=port)


def test_unknown_variables_in_the_env_file_are_ignored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Las variables del entorno ganan sobre el archivo: se quitan las de .env.test.
    for name in ("DB_USER", "DB_PASSWORD", "DB_NAME"):
        monkeypatch.delenv(name, raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("DB_USER=u\nDB_PASSWORD=p\nDB_NAME=db\nHOST=0.0.0.0\nPORT=8000\n")

    assert Settings(_env_file=env_file).db_name == "db"  # type: ignore[call-arg]


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
