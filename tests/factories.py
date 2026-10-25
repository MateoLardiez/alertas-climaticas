"""Funciones auxiliares para crear registros de prueba ya guardados en la base."""

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from alertas_climaticas.models import (
    Alert,
    Event,
    Farm,
    Notification,
    Region,
    User,
    WeatherForecast,
)


async def _save[T](session: AsyncSession, obj: T) -> T:
    session.add(obj)
    await session.commit()
    return obj


async def create_region(session: AsyncSession, name: str = "Mercedes") -> Region:
    return await _save(session, Region(name=name))


async def create_event(session: AsyncSession, name: str = "lluvia") -> Event:
    return await _save(session, Event(name=name))


async def create_user(session: AsyncSession, name: str = "Mateo") -> User:
    return await _save(session, User(name=name))


async def create_farm(
    session: AsyncSession, user: User, region: Region, name: str = "La Esperanza"
) -> Farm:
    return await _save(session, Farm(user_id=user.id, region_id=region.id, name=name))


async def create_alert(
    session: AsyncSession, farm: Farm, event: Event, threshold: int = 60
) -> Alert:
    return await _save(
        session, Alert(farm_id=farm.id, event_id=event.id, threshold=threshold)
    )


async def create_forecast(
    session: AsyncSession, region: Region, event: Event, day: date, probability: int
) -> WeatherForecast:
    return await _save(
        session,
        WeatherForecast(
            region_id=region.id, event_id=event.id, forecast_date=day, probability=probability
        ),
    )


async def create_notification(
    session: AsyncSession, alert: Alert, day: date, probability: int = 80
) -> Notification:
    return await _save(
        session, Notification(alert_id=alert.id, forecast_date=day, probability=probability)
    )
