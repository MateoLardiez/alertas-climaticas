"""Tests del job periodico: programacion, ejecucion, errores y arranque con la app."""

import asyncio
import logging
import os
import sys
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from alertas_climaticas import main
from alertas_climaticas.clock import current_date
from alertas_climaticas.config import Settings, get_settings
from alertas_climaticas.jobs import alert_evaluation
from alertas_climaticas.jobs.alert_evaluation import (
    JOB_ID,
    create_scheduler,
    run_evaluation,
    scheduled_evaluation,
)
from alertas_climaticas.models import Notification
from tests import factories

DB = {"db_user": "u", "db_password": "p", "db_name": "db"}
BUENOS_AIRES = ZoneInfo("America/Argentina/Buenos_Aires")


def _settings(**values: object) -> Settings:
    return Settings(_env_file=None, **{**DB, **values})  # type: ignore[call-arg, arg-type]


async def _count_notifications(session: AsyncSession) -> int:
    return await session.scalar(select(func.count()).select_from(Notification)) or 0


async def _alert_with_forecast_today(session: AsyncSession, today: date) -> None:
    user = await factories.create_user(session)
    region = await factories.create_region(session)
    event = await factories.create_event(session, "lluvia")
    farm = await factories.create_farm(session, user, region)
    await factories.create_alert(session, farm, event, 60)
    await factories.create_forecast(session, region, event, today, 80)


class TestSchedulerConfiguration:
    def test_registers_a_single_job(self) -> None:
        scheduler = create_scheduler(_settings())

        assert [job.id for job in scheduler.get_jobs()] == [JOB_ID]

    def test_runs_the_error_safe_wrapper(self) -> None:
        job = create_scheduler(_settings()).get_job(JOB_ID)

        assert job is not None
        assert job.func is scheduled_evaluation

    def test_never_overlaps_and_coalesces_late_runs(self) -> None:
        job = create_scheduler(_settings()).get_job(JOB_ID)

        assert job is not None
        assert job.max_instances == 1
        assert job.coalesce is True

    def test_tolerates_being_late_by_up_to_an_hour(self) -> None:
        job = create_scheduler(_settings()).get_job(JOB_ID)

        assert job is not None
        assert job.misfire_grace_time == 3600

    def test_uses_the_configured_timezone(self) -> None:
        scheduler = create_scheduler(_settings(timezone="UTC"))

        assert str(scheduler.timezone) == "UTC"


class TestSchedule:
    """Cuando dispara: una vez por dia, a las 6:00 hora Argentina."""

    def _trigger(self, **settings: object):  # type: ignore[no-untyped-def]
        job = create_scheduler(_settings(**settings)).get_job(JOB_ID)
        assert job is not None
        return job.trigger

    def test_fires_at_6am_argentina_time(self) -> None:
        trigger = self._trigger()

        next_run = trigger.get_next_fire_time(None, datetime(2026, 3, 10, 5, 59, tzinfo=BUENOS_AIRES))

        assert next_run == datetime(2026, 3, 10, 6, 0, tzinfo=BUENOS_AIRES)

    def test_after_6am_the_next_run_is_tomorrow(self) -> None:
        trigger = self._trigger()

        next_run = trigger.get_next_fire_time(None, datetime(2026, 3, 10, 6, 0, 1, tzinfo=BUENOS_AIRES))

        assert next_run == datetime(2026, 3, 11, 6, 0, tzinfo=BUENOS_AIRES)

    def test_fires_exactly_once_a_day(self) -> None:
        trigger = self._trigger()
        fire = trigger.get_next_fire_time(None, datetime(2026, 3, 10, 0, 0, tzinfo=BUENOS_AIRES))

        for _ in range(14):
            following = trigger.get_next_fire_time(fire, fire + timedelta(seconds=1))
            assert following - fire == timedelta(days=1)
            fire = following

    def test_it_is_argentine_time_whatever_the_server_clock_says(self) -> None:
        trigger = self._trigger()

        # 08:59 UTC son las 05:59 en Buenos Aires: faltan 60 segundos para las 6:00 locales.
        next_run = trigger.get_next_fire_time(None, datetime(2026, 3, 10, 8, 59, tzinfo=UTC))

        assert next_run == datetime(2026, 3, 10, 9, 0, tzinfo=UTC)
        assert next_run.astimezone(BUENOS_AIRES).hour == 6

    def test_late_evening_in_argentina_waits_for_the_next_morning(self) -> None:
        trigger = self._trigger()

        # 02:00 UTC del 10/03 son las 23:00 del 09/03 en Buenos Aires.
        next_run = trigger.get_next_fire_time(None, datetime(2026, 3, 10, 2, 0, tzinfo=UTC))

        assert next_run == datetime(2026, 3, 10, 6, 0, tzinfo=BUENOS_AIRES)

    def test_the_hour_can_be_configured(self) -> None:
        trigger = self._trigger(evaluation_hour=22)

        next_run = trigger.get_next_fire_time(None, datetime(2026, 3, 10, 7, 0, tzinfo=BUENOS_AIRES))

        assert next_run == datetime(2026, 3, 10, 22, 0, tzinfo=BUENOS_AIRES)

    def test_the_hour_follows_the_configured_timezone(self) -> None:
        trigger = self._trigger(timezone="UTC")

        next_run = trigger.get_next_fire_time(None, datetime(2026, 3, 10, 5, 59, tzinfo=UTC))

        assert next_run == datetime(2026, 3, 10, 6, 0, tzinfo=UTC)

    async def test_the_scheduler_really_runs_the_job_when_the_time_comes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ran = asyncio.Event()

        async def fake_evaluation() -> None:
            ran.set()

        monkeypatch.setattr(alert_evaluation, "scheduled_evaluation", fake_evaluation)
        soon = DateTrigger(run_date=datetime.now(UTC) + timedelta(milliseconds=200))
        scheduler = create_scheduler(_settings(), trigger=soon)
        scheduler.start()
        try:
            await asyncio.wait_for(ran.wait(), timeout=5)
        finally:
            scheduler.shutdown()

        assert ran.is_set()

    async def test_nothing_runs_when_the_app_starts(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls = 0

        async def fake_evaluation() -> None:
            nonlocal calls
            calls += 1

        monkeypatch.setattr(alert_evaluation, "scheduled_evaluation", fake_evaluation)
        scheduler = create_scheduler(_settings())
        scheduler.start()
        try:
            await asyncio.sleep(0.5)
        finally:
            scheduler.shutdown()

        assert calls == 0


class TestRunEvaluation:
    async def test_creates_the_notifications_and_returns_how_many(
        self, session: AsyncSession
    ) -> None:
        today = date(2026, 3, 10)
        await _alert_with_forecast_today(session, today)

        created = await run_evaluation(today)

        assert created == 1
        assert await _count_notifications(session) == 1

    async def test_a_second_run_creates_nothing(self, session: AsyncSession) -> None:
        today = date(2026, 3, 10)
        await _alert_with_forecast_today(session, today)

        first = await run_evaluation(today)
        second = await run_evaluation(today)

        assert (first, second) == (1, 0)

    async def test_uses_today_in_the_configured_timezone_by_default(
        self, session: AsyncSession
    ) -> None:
        today = current_date(get_settings().timezone)
        await _alert_with_forecast_today(session, today)

        assert await run_evaluation() == 1

    async def test_logs_how_many_notifications_it_created(
        self, session: AsyncSession, caplog: pytest.LogCaptureFixture
    ) -> None:
        today = date(2026, 3, 10)
        await _alert_with_forecast_today(session, today)

        with caplog.at_level(logging.INFO, logger=alert_evaluation.__name__):
            await run_evaluation(today)

        assert "2026-03-10 created 1 notifications" in caplog.text


class TestFailureHandling:
    async def test_an_error_is_logged_and_does_not_escape(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        async def failing_evaluation(today: date | None = None) -> int:
            raise RuntimeError("la base no responde")

        monkeypatch.setattr(alert_evaluation, "run_evaluation", failing_evaluation)

        with caplog.at_level(logging.ERROR, logger=alert_evaluation.__name__):
            await scheduled_evaluation()  # no debe lanzar

        assert "Alert evaluation failed" in caplog.text
        assert "la base no responde" in caplog.text

    async def test_the_next_run_works_after_a_failure(
        self, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        today = current_date(get_settings().timezone)
        await _alert_with_forecast_today(session, today)
        real_evaluation = alert_evaluation.run_evaluation
        calls = {"count": 0}

        async def flaky_evaluation(today: date | None = None) -> int:
            calls["count"] += 1
            if calls["count"] == 1:
                raise RuntimeError("falla transitoria")
            return await real_evaluation(today)

        monkeypatch.setattr(alert_evaluation, "run_evaluation", flaky_evaluation)

        await scheduled_evaluation()
        assert await _count_notifications(session) == 0
        await scheduled_evaluation()

        assert await _count_notifications(session) == 1

    async def test_a_cancellation_is_not_swallowed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def cancelled_evaluation(today: date | None = None) -> int:
            raise asyncio.CancelledError

        monkeypatch.setattr(alert_evaluation, "run_evaluation", cancelled_evaluation)

        with pytest.raises(asyncio.CancelledError):
            await scheduled_evaluation()


class TestLifespan:
    async def test_starts_the_scheduler_with_the_app_and_stops_it_on_shutdown(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def fake_evaluation() -> None:
            return None

        monkeypatch.setattr(alert_evaluation, "scheduled_evaluation", fake_evaluation)
        monkeypatch.setattr(main, "get_settings", lambda: _settings(evaluation_job_enabled=True))

        async with main.lifespan(main.app):
            scheduler = main.app.state.scheduler
            assert isinstance(scheduler, AsyncIOScheduler)
            assert scheduler.running
            assert scheduler.get_job(JOB_ID) is not None

        await asyncio.sleep(0)
        assert not scheduler.running

    async def test_does_not_start_a_scheduler_when_the_job_is_disabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(main, "get_settings", lambda: _settings(evaluation_job_enabled=False))

        async with main.lifespan(main.app):
            assert main.app.state.scheduler is None

    async def test_the_scheduler_is_stopped_even_if_the_app_fails(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def fake_evaluation() -> None:
            return None

        monkeypatch.setattr(alert_evaluation, "scheduled_evaluation", fake_evaluation)
        monkeypatch.setattr(main, "get_settings", lambda: _settings(evaluation_job_enabled=True))
        scheduler = None

        with pytest.raises(RuntimeError):
            async with main.lifespan(main.app):
                scheduler = main.app.state.scheduler
                raise RuntimeError("fallo durante la ejecucion")

        await asyncio.sleep(0)
        assert scheduler is not None
        assert not scheduler.running

    def test_the_test_environment_has_the_job_disabled(self) -> None:
        assert get_settings().evaluation_job_enabled is False


class TestManualRun:
    async def test_running_the_module_evaluates_once_and_exits(
        self, session: AsyncSession
    ) -> None:
        today = current_date(get_settings().timezone)
        await _alert_with_forecast_today(session, today)

        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "alertas_climaticas.jobs.alert_evaluation",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=os.environ.copy(),
        )
        _, stderr = await asyncio.wait_for(process.communicate(), timeout=30)

        assert process.returncode == 0, stderr.decode()
        assert b"created 1 notifications" in stderr
        assert await _count_notifications(session) == 1

    async def test_running_it_twice_does_not_duplicate(self, session: AsyncSession) -> None:
        today = current_date(get_settings().timezone)
        await _alert_with_forecast_today(session, today)

        for _ in range(2):
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "alertas_climaticas.jobs.alert_evaluation",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=os.environ.copy(),
            )
            await asyncio.wait_for(process.communicate(), timeout=30)

        assert await _count_notifications(session) == 1
