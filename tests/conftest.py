"""Fixtures compartidas: base de datos de test (migrada con Alembic), sesion y cliente HTTP."""

import asyncio
import os
from collections.abc import AsyncIterator
from pathlib import Path

import asyncpg
import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from dotenv import dotenv_values
from sqlalchemy import text
from sqlalchemy.engine import URL

ROOT = Path(__file__).resolve().parent.parent
_test_env = dotenv_values(ROOT / ".env.test")
TEST_DATABASE_URL = URL.create(
    "postgresql+asyncpg",
    username=_test_env["DB_USER"],
    password=_test_env["DB_PASSWORD"],
    host=_test_env["DB_HOST"],
    port=int(str(_test_env["DB_PORT"])),
    database=_test_env["DB_NAME"],
)
TEST_DB_NAME = str(TEST_DATABASE_URL.database)

# Salvaguarda: el fixture de la base borra todo el esquema, nunca debe apuntar a la base real.
assert TEST_DB_NAME.endswith("_test"), f"La base de tests debe terminar en _test: {TEST_DB_NAME}"

# Debe fijarse antes de importar la app: el engine se crea al importar el modulo de sesion.
# Se carga todo .env.test (no solo la URL) para no depender del .env de desarrollo.
for key, value in dotenv_values(ROOT / ".env.test").items():
    os.environ[key] = str(value)

from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from alertas_climaticas.database.base import Base  # noqa: E402
from alertas_climaticas.database.session import async_session_factory, engine  # noqa: E402
from alertas_climaticas.main import app  # noqa: E402


def _asyncpg_dsn(database: str) -> str:
    url = TEST_DATABASE_URL.set(drivername="postgresql", database=database)
    return url.render_as_string(hide_password=False)


# Mensaje de error si PostgreSQL no esta disponible. Lo llena pytest_collection_modifyitems.
_database_error: str | None = None


async def _try_connect() -> None:
    connection = await asyncpg.connect(_asyncpg_dsn("postgres"), timeout=3)
    await connection.close()


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Marca con `db` los tests que usan la base y, si no esta disponible, deja solo uno.

    Ese unico test falla con una explicacion clara, en lugar de decenas de errores identicos.
    Los tests que no usan la base se ejecutan igual (`pytest -m "not db"` corre solo esos).
    """
    global _database_error

    db_items = [item for item in items if "database" in getattr(item, "fixturenames", ())]
    for item in db_items:
        item.add_marker(pytest.mark.db)
    if not db_items:
        return

    try:
        asyncio.run(_try_connect())
    except Exception as exc:
        url = TEST_DATABASE_URL
        omitted = db_items[1:]
        _database_error = (
            f"No se pudo conectar a PostgreSQL en {url.host}:{url.port} "
            f"({type(exc).__name__}: {exc}).\n"
            "Levanta la base (por ejemplo: docker start alertas-db) y revisa el host, "
            "el puerto y las credenciales de .env.test.\n"
            f"Se omitieron {len(omitted)} tests que tambien usan la base. "
            'Para correr solo los que no la usan: pytest -m "not db"'
        )
        items[:] = [item for item in items if item not in omitted]
        config.hook.pytest_deselected(items=omitted)


@pytest.fixture(scope="session")
def alembic_cfg() -> Config:
    # Sin alembic.ini: asi env.py no reconfigura el logging de pytest.
    cfg = Config()
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    return cfg


@pytest_asyncio.fixture(scope="session")
async def database(alembic_cfg: Config) -> AsyncIterator[None]:
    """Crea la base de test si falta y la deja con el esquema migrado desde cero."""
    if _database_error is not None:
        pytest.fail(_database_error, pytrace=False)

    admin = await asyncpg.connect(_asyncpg_dsn("postgres"))
    try:
        exists = await admin.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1", TEST_DB_NAME
        )
        if not exists:
            await admin.execute(f'CREATE DATABASE "{TEST_DB_NAME}"')
    finally:
        await admin.close()

    conn = await asyncpg.connect(_asyncpg_dsn(TEST_DB_NAME))
    try:
        await conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public")
    finally:
        await conn.close()

    # env.py usa asyncio.run, que no puede correr dentro del loop de pytest: va en otro hilo.
    await asyncio.to_thread(command.upgrade, alembic_cfg, "head")
    yield
    await engine.dispose()


@pytest_asyncio.fixture
async def clean_tables(database: None) -> AsyncIterator[None]:
    """Vacia todas las tablas al terminar cada test que usa la base."""
    yield
    tables = ", ".join(table.name for table in Base.metadata.sorted_tables)
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} CASCADE"))


@pytest_asyncio.fixture
async def session(clean_tables: None) -> AsyncIterator[AsyncSession]:
    async with async_session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def client(clean_tables: None) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
