"""Tests de las dependencias compartidas de FastAPI."""

from datetime import date

import pytest

from alertas_climaticas import dependencies
from alertas_climaticas.clock import current_date
from alertas_climaticas.config import get_settings
from alertas_climaticas.dependencies import get_today


def test_today_is_the_date_in_the_configured_timezone() -> None:
    assert get_today() == current_date(get_settings().timezone)


def test_today_follows_the_timezone_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []

    def fake_current_date(timezone: str) -> date:
        seen.append(timezone)
        return date(2026, 3, 10)

    monkeypatch.setattr(dependencies, "current_date", fake_current_date)

    assert get_today() == date(2026, 3, 10)
    assert seen == [get_settings().timezone]
