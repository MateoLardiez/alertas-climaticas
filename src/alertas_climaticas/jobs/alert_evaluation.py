"""Job diario que evalua las alertas, programado con APScheduler.

Tambien se puede ejecutar una evaluacion a mano: python -m alertas_climaticas.jobs.alert_evaluation
"""

import asyncio
import logging
from datetime import date

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.base import BaseTrigger
from apscheduler.triggers.cron import CronTrigger

from alertas_climaticas.clock import current_date
from alertas_climaticas.config import Settings, get_settings
from alertas_climaticas.database.session import async_session_factory, engine
from alertas_climaticas.services.evaluation import evaluate_alerts

logger = logging.getLogger(__name__)

JOB_ID = "alert_evaluation"


async def run_evaluation(today: date | None = None) -> int:
    """Una evaluacion de alertas. Devuelve las notificaciones nuevas y propaga los errores."""
    today = today or current_date(get_settings().timezone)
    async with async_session_factory() as session:
        created = await evaluate_alerts(session, today)
    logger.info("Alert evaluation for %s created %d notifications", today, created)
    return created


async def scheduled_evaluation() -> None:
    """Lo que ejecuta el scheduler: un error se registra y no detiene las siguientes corridas."""
    try:
        await run_evaluation()
    except Exception:
        logger.exception("Alert evaluation failed; it will be retried on the next run")


def create_scheduler(settings: Settings, trigger: BaseTrigger | None = None) -> AsyncIOScheduler:
    """Programa la evaluacion una vez por dia a `evaluation_hour`, hora de `timezone`.

    `trigger` solo se pasa en los tests, para no esperar hasta la hora configurada.
    """
    scheduler = AsyncIOScheduler(timezone=settings.timezone)
    scheduler.add_job(
        scheduled_evaluation,
        trigger or CronTrigger(hour=settings.evaluation_hour, minute=0, timezone=settings.timezone),
        id=JOB_ID,
        # Nunca dos evaluaciones a la vez en este proceso; las corridas atrasadas se juntan en una.
        max_instances=1,
        coalesce=True,
        # Si el proceso estaba ocupado a la hora exacta, todavia corre dentro de la hora siguiente.
        misfire_grace_time=3600,
    )
    return scheduler


async def _run_once_from_the_command_line() -> None:
    logging.basicConfig(level=logging.INFO)
    try:
        await run_evaluation()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_run_once_from_the_command_line())
