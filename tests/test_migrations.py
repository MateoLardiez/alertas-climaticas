"""Tests de las migraciones de Alembic: esquema completo, reversible y sincronizado con los modelos."""

import asyncio

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text

from alertas_climaticas.database.session import async_session_factory, engine

APP_TABLES = {
    "alert",
    "event",
    "farm",
    "notification",
    "region",
    "users",
    "weather_forecast",
}


async def _table_names() -> set[str]:
    async with async_session_factory() as session:
        result = await session.scalars(
            text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
        )
        return set(result.all())


async def test_upgrade_head_creates_all_tables(clean_tables: None) -> None:
    assert await _table_names() == APP_TABLES | {"alembic_version"}


def test_migrations_have_a_single_head(alembic_cfg: Config) -> None:
    heads = ScriptDirectory.from_config(alembic_cfg).get_heads()

    assert len(heads) == 1


async def test_models_and_migrations_are_in_sync(clean_tables: None, alembic_cfg: Config) -> None:
    # command.check falla si autogenerate detectaria cambios sin migrar.
    await asyncio.to_thread(command.check, alembic_cfg)


@pytest.mark.parametrize("table", sorted(APP_TABLES))
async def test_every_table_has_uuid_primary_key_generated_by_database(
    clean_tables: None, table: str
) -> None:
    async with async_session_factory() as session:
        row = (
            await session.execute(
                text(
                    "SELECT data_type, column_default FROM information_schema.columns "
                    "WHERE table_name = :table AND column_name = 'id'"
                ),
                {"table": table},
            )
        ).one()

    assert row.data_type == "uuid"
    assert "gen_random_uuid()" in row.column_default


async def test_downgrade_drops_tables_and_upgrade_restores_them(
    clean_tables: None, alembic_cfg: Config
) -> None:
    await asyncio.to_thread(command.downgrade, alembic_cfg, "base")
    try:
        await engine.dispose()
        assert await _table_names() == {"alembic_version"}
    finally:
        await asyncio.to_thread(command.upgrade, alembic_cfg, "head")
        # El pool puede tener sentencias preparadas de las tablas anteriores.
        await engine.dispose()

    assert await _table_names() == APP_TABLES | {"alembic_version"}


async def _farm_user_fk_delete_rule() -> str:
    async with async_session_factory() as session:
        return str(
            await session.scalar(
                text("SELECT confdeltype::text FROM pg_constraint WHERE conname = 'farm_user_id_fkey'")
            )
        )


async def test_the_farm_user_fk_cascades_and_the_downgrade_restores_the_old_rule(
    clean_tables: None, alembic_cfg: Config
) -> None:
    assert await _farm_user_fk_delete_rule() == "c"  # CASCADE

    await asyncio.to_thread(command.downgrade, alembic_cfg, "-1")
    try:
        await engine.dispose()
        assert await _farm_user_fk_delete_rule() == "a"  # NO ACTION
    finally:
        await asyncio.to_thread(command.upgrade, alembic_cfg, "head")
        await engine.dispose()

    assert await _farm_user_fk_delete_rule() == "c"
