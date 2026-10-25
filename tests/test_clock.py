"""Tests de la fecha actual segun la zona horaria configurada."""

from datetime import UTC, date, datetime

import pytest

from alertas_climaticas.clock import current_date

BUENOS_AIRES = "America/Argentina/Buenos_Aires"


def test_the_date_in_buenos_aires_is_the_previous_day_early_in_utc() -> None:
    # 02:00 UTC del 10/03 son las 23:00 del 09/03 en Buenos Aires (UTC-3).
    now = datetime(2026, 3, 10, 2, 0, tzinfo=UTC)

    assert current_date(BUENOS_AIRES, now) == date(2026, 3, 9)
    assert current_date("UTC", now) == date(2026, 3, 10)


def test_the_day_changes_exactly_at_local_midnight() -> None:
    before = datetime(2026, 3, 10, 2, 59, tzinfo=UTC)
    after = datetime(2026, 3, 10, 3, 0, tzinfo=UTC)

    assert current_date(BUENOS_AIRES, before) == date(2026, 3, 9)
    assert current_date(BUENOS_AIRES, after) == date(2026, 3, 10)


def test_it_applies_the_zone_to_aware_datetimes_of_any_offset() -> None:
    from zoneinfo import ZoneInfo

    now = datetime(2026, 3, 10, 23, 0, tzinfo=ZoneInfo("Asia/Tokyo"))  # 14:00 UTC

    assert current_date(BUENOS_AIRES, now) == date(2026, 3, 10)


@pytest.mark.parametrize("timezone", [BUENOS_AIRES, "UTC", "Europe/Madrid"])
def test_without_an_instant_it_uses_the_current_time(timezone: str) -> None:
    today = current_date(timezone)

    assert isinstance(today, date)
    assert abs((today - datetime.now(UTC).date()).days) <= 1


def test_an_unknown_zone_raises() -> None:
    with pytest.raises(Exception):  # noqa: B017
        current_date("No/Existe", datetime(2026, 3, 10, tzinfo=UTC))
