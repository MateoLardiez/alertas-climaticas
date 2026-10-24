"""Seed de desarrollo: carga regiones, eventos y un pronostico mockeado de 20 dias."""

import asyncio
import random
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from alertas_climaticas.database.session import async_session_factory, engine
from alertas_climaticas.models import Event, Region, WeatherForecast

REGIONS = [
    "Mercedes",
    "Tandil",
    "Navarro",
    "Pergamino",
    "Balcarce",
    "Trenque Lauquen",
    "San Pedro",
    "Cañuelas",
    "Tres Arroyos",
    "Lobos",
]
RAIN, FROST, HEAT, STORM = "lluvia", "helada", "calor extremo", "tormenta"
EVENTS = [RAIN, FROST, HEAT, STORM]

DAYS = 30
RNG_SEED = 42

PROBABILITIES = [0, 20, 40, 60, 80, 100]
LOW = [0, 20, 40]
HIGH = [60, 80, 100]

THERMAL_STATES = ["calido", "frio", "templado"]
THERMAL_WEIGHTS = [30, 30, 40]
THERMAL_PERSISTENCE = 0.6

RAIN_WEIGHTS = [35, 25, 18, 12, 7, 3]
STORM_FROM_RAIN = 0.7
INDEPENDENT_STORM_WEIGHTS = [60, 20, 10, 5, 3, 2]


def next_thermal_state(previous: str | None, rng: random.Random) -> str:
    if previous is not None and rng.random() < THERMAL_PERSISTENCE:
        return previous
    return rng.choices(THERMAL_STATES, THERMAL_WEIGHTS)[0]


def thermal_probabilities(state: str, rng: random.Random) -> tuple[int, int]:
    """Devuelve (calor extremo, helada). Nunca son ambas >= 60."""
    if state == "calido":
        return rng.choice(HIGH), 0
    if state == "frio":
        return 0, rng.choice(HIGH)
    return rng.choice(LOW), rng.choice(LOW)


def rain_and_storm(rng: random.Random) -> tuple[int, int]:
    """Devuelve (lluvia, tormenta). La tormenta suele acompanar a la lluvia, sin superarla."""
    rain = rng.choices(PROBABILITIES, RAIN_WEIGHTS)[0]
    if rng.random() < STORM_FROM_RAIN:
        storm = max(0, rain - 20 * rng.choice([0, 1, 2]))
    else:
        storm = rng.choices(PROBABILITIES, INDEPENDENT_STORM_WEIGHTS)[0]
    return rain, storm


def generate_region_forecast(
    rng: random.Random, start: date, days: int
) -> list[tuple[str, date, int]]:
    """Genera (evento, fecha, probabilidad) para todos los eventos de una region."""
    rows: list[tuple[str, date, int]] = []
    state: str | None = None
    for offset in range(days):
        state = next_thermal_state(state, rng)
        heat, frost = thermal_probabilities(state, rng)
        rain, storm = rain_and_storm(rng)
        day = start + timedelta(days=offset)
        rows += [(RAIN, day, rain), (FROST, day, frost), (HEAT, day, heat), (STORM, day, storm)]
    return rows


async def seed() -> None:
    rng = random.Random(RNG_SEED)
    start = date.today()

    async with async_session_factory() as session:
        await session.execute(
            insert(Region).values([{"name": name} for name in REGIONS])
            .on_conflict_do_nothing(index_elements=["name"])
        )
        await session.execute(
            insert(Event).values([{"name": name} for name in EVENTS])
            .on_conflict_do_nothing(index_elements=["name"])
        )
        region_ids = dict((await session.execute(select(Region.name, Region.id))).all())
        event_ids = dict((await session.execute(select(Event.name, Event.id))).all())

        forecasts = [
            {
                "region_id": region_ids[region],
                "event_id": event_ids[event],
                "forecast_date": day,
                "probability": probability,
            }
            for region in REGIONS
            for event, day, probability in generate_region_forecast(rng, start, DAYS)
        ]
        await session.execute(
            insert(WeatherForecast).values(forecasts)
            .on_conflict_do_nothing(constraint="uq_weather_forecast_region_event_date")
        )
        await session.commit()

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
