"""Evaluacion de alertas: cruza las alertas con el pronostico y genera las notificaciones."""

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from alertas_climaticas.models import Alert, Farm, Notification, WeatherForecast

FORECAST_WINDOW_DAYS = 7


async def evaluate_alerts(session: AsyncSession, today: date) -> int:
    """Crea una notificacion por cada alerta y dia en que el pronostico alcanza su umbral.

    Evalua los FORECAST_WINDOW_DAYS dias que empiezan en `today` (hoy incluido) y devuelve
    la cantidad de notificaciones nuevas. Se puede ejecutar varias veces, incluso a la vez:
    la clave unica (alerta, fecha) hace que cada notificacion se cree una sola vez.
    """
    last_day = today + timedelta(days=FORECAST_WINDOW_DAYS - 1)

    exceeded = (
        select(Alert.id, WeatherForecast.forecast_date, WeatherForecast.probability)
        .select_from(Alert)
        .join(Farm, Farm.id == Alert.farm_id)
        .join(
            WeatherForecast,
            (WeatherForecast.region_id == Farm.region_id)
            & (WeatherForecast.event_id == Alert.event_id),
        )
        .where(
            WeatherForecast.forecast_date.between(today, last_day),
            WeatherForecast.probability >= Alert.threshold,
        )
        # Orden fijo: dos evaluaciones simultaneas insertan en el mismo orden y no se bloquean
        # entre si (con orden distinto podrian quedar en deadlock).
        .order_by(Alert.id, WeatherForecast.forecast_date)
    )
    result = await session.scalars(
        insert(Notification)
        .from_select(["alert_id", "forecast_date", "probability"], exceeded)
        .on_conflict_do_nothing(constraint="uq_notification_alert_date")
        .returning(Notification.id)
    )
    created = len(result.all())
    await session.commit()
    return created
