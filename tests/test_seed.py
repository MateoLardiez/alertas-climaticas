"""Tests del script de seed ejecutado contra la base de test."""

from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from alertas_climaticas import seed
from alertas_climaticas.models import Event, Region, WeatherForecast


async def _count(session: AsyncSession, model: type) -> int:
    return await session.scalar(select(func.count()).select_from(model)) or 0


async def test_seed_loads_regions_events_and_forecasts(session: AsyncSession) -> None:
    await seed.seed()

    assert await _count(session, Region) == len(seed.REGIONS)
    assert await _count(session, Event) == len(seed.EVENTS)
    assert await _count(session, WeatherForecast) == (
        len(seed.REGIONS) * len(seed.EVENTS) * seed.DAYS
    )
    regions = set((await session.scalars(select(Region.name))).all())
    events = set((await session.scalars(select(Event.name))).all())
    assert regions == set(seed.REGIONS)
    assert events == set(seed.EVENTS)


async def test_seed_covers_the_configured_window_starting_today(session: AsyncSession) -> None:
    await seed.seed()

    first, last = (
        await session.execute(
            select(func.min(WeatherForecast.forecast_date), func.max(WeatherForecast.forecast_date))
        )
    ).one()
    assert first == date.today()
    assert last == date.today() + timedelta(days=seed.DAYS - 1)


async def test_seed_gives_every_region_every_event_every_day(session: AsyncSession) -> None:
    await seed.seed()

    rows = (
        await session.execute(
            select(Region.name, Event.name, func.count(), func.count(func.distinct(WeatherForecast.forecast_date)))
            .select_from(WeatherForecast)
            .join(Region, Region.id == WeatherForecast.region_id)
            .join(Event, Event.id == WeatherForecast.event_id)
            .group_by(Region.name, Event.name)
        )
    ).all()

    assert len(rows) == len(seed.REGIONS) * len(seed.EVENTS)
    assert all(count == seed.DAYS == distinct_days for _, _, count, distinct_days in rows)


async def test_seed_is_idempotent(session: AsyncSession) -> None:
    await seed.seed()
    await seed.seed()

    assert await _count(session, Region) == len(seed.REGIONS)
    assert await _count(session, Event) == len(seed.EVENTS)
    assert await _count(session, WeatherForecast) == (
        len(seed.REGIONS) * len(seed.EVENTS) * seed.DAYS
    )


async def test_seed_does_not_overwrite_existing_forecasts(session: AsyncSession) -> None:
    await seed.seed()
    original = {
        (row.region_id, row.event_id, row.forecast_date): row.probability
        for row in (await session.scalars(select(WeatherForecast))).all()
    }

    await seed.seed()

    session.expire_all()
    current = {
        (row.region_id, row.event_id, row.forecast_date): row.probability
        for row in (await session.scalars(select(WeatherForecast))).all()
    }
    assert current == original


async def test_seeded_forecasts_respect_the_heat_and_frost_rule(session: AsyncSession) -> None:
    await seed.seed()

    rows = (
        await session.execute(
            select(
                WeatherForecast.region_id,
                WeatherForecast.forecast_date,
                Event.name,
                WeatherForecast.probability,
            ).join(Event, Event.id == WeatherForecast.event_id)
        )
    ).all()
    days: dict[tuple[object, date], dict[str, int]] = defaultdict(dict)
    for region_id, day, event, probability in rows:
        days[(region_id, day)][event] = probability

    assert len(days) == len(seed.REGIONS) * seed.DAYS
    for values in days.values():
        if values[seed.HEAT] >= 60:
            assert values[seed.FROST] == 0
        if values[seed.FROST] >= 60:
            assert values[seed.HEAT] == 0


async def test_seeded_probabilities_are_valid_steps(session: AsyncSession) -> None:
    await seed.seed()

    values = set((await session.scalars(select(WeatherForecast.probability))).all())

    assert values <= set(seed.PROBABILITIES)
