"""Tests de las funciones puras que generan el pronostico mockeado (sin base de datos)."""

import random
from collections import Counter
from datetime import date, timedelta

import pytest

from alertas_climaticas import seed
from alertas_climaticas.seed import (
    EVENTS,
    FROST,
    HEAT,
    HIGH,
    LOW,
    PROBABILITIES,
    RAIN,
    STORM,
    generate_region_forecast,
    next_thermal_state,
    rain_and_storm,
    thermal_probabilities,
)

START = date(2026, 1, 1)


def _by_day(rows: list[tuple[str, date, int]]) -> dict[date, dict[str, int]]:
    days: dict[date, dict[str, int]] = {}
    for event, day, probability in rows:
        days.setdefault(day, {})[event] = probability
    return days


def _sample(regions: int, days: int = 30, seed_value: int = 7) -> list[dict[date, dict[str, int]]]:
    rng = random.Random(seed_value)
    return [_by_day(generate_region_forecast(rng, START, days)) for _ in range(regions)]


def _thermal_state(day: dict[str, int]) -> str:
    if day[HEAT] >= 60:
        return "calido"
    if day[FROST] >= 60:
        return "frio"
    return "templado"


class TestShape:
    def test_generates_one_row_per_event_and_day(self) -> None:
        rows = generate_region_forecast(random.Random(1), START, 30)

        assert len(rows) == 30 * len(EVENTS)
        assert len({(event, day) for event, day, _ in rows}) == len(rows)

    def test_covers_consecutive_days_from_start(self) -> None:
        rows = generate_region_forecast(random.Random(1), START, 30)

        days = sorted({day for _, day, _ in rows})
        assert days == [START + timedelta(days=offset) for offset in range(30)]

    def test_every_day_has_all_events(self) -> None:
        rows = generate_region_forecast(random.Random(1), START, 10)

        for day in _by_day(rows).values():
            assert set(day) == set(EVENTS)

    def test_zero_days_generates_nothing(self) -> None:
        assert generate_region_forecast(random.Random(1), START, 0) == []

    def test_probabilities_are_only_multiples_of_twenty_up_to_100(self) -> None:
        for region in _sample(200):
            for day in region.values():
                assert set(day.values()) <= set(PROBABILITIES)


class TestDeterminism:
    def test_same_seed_generates_the_same_forecast(self) -> None:
        first = generate_region_forecast(random.Random(42), START, 30)
        second = generate_region_forecast(random.Random(42), START, 30)

        assert first == second

    def test_different_seeds_generate_different_forecasts(self) -> None:
        first = generate_region_forecast(random.Random(1), START, 30)
        second = generate_region_forecast(random.Random(2), START, 30)

        assert first != second


class TestHeatAndFrost:
    def test_extreme_heat_and_frost_are_never_high_together(self) -> None:
        checked = 0
        for region in _sample(1000):
            for day in region.values():
                checked += 1
                if day[HEAT] >= 60:
                    assert day[FROST] == 0
                if day[FROST] >= 60:
                    assert day[HEAT] == 0
        assert checked == 30_000

    @pytest.mark.parametrize("state", ["calido", "frio", "templado"])
    def test_thermal_probabilities_follow_the_state(self, state: str) -> None:
        rng = random.Random(3)

        for _ in range(300):
            heat, frost = thermal_probabilities(state, rng)
            if state == "calido":
                assert heat in HIGH and frost == 0
            elif state == "frio":
                assert heat == 0 and frost in HIGH
            else:
                assert heat in LOW and frost in LOW

    def test_thermal_states_follow_the_configured_weights(self) -> None:
        states = Counter(
            _thermal_state(day) for region in _sample(1000) for day in region.values()
        )
        total = sum(states.values())

        assert states["calido"] / total == pytest.approx(0.30, abs=0.03)
        assert states["frio"] / total == pytest.approx(0.30, abs=0.03)
        assert states["templado"] / total == pytest.approx(0.40, abs=0.03)

    def test_thermal_state_persists_between_days(self) -> None:
        same = total = 0
        for region in _sample(1000):
            states = [_thermal_state(region[day]) for day in sorted(region)]
            same += sum(a == b for a, b in zip(states, states[1:]))
            total += len(states) - 1

        # 60% de persistencia + 40% de re-sortear y repetir (0.3^2 + 0.3^2 + 0.4^2 = 0.34).
        assert same / total == pytest.approx(0.6 + 0.4 * 0.34, abs=0.03)

    def test_full_persistence_keeps_a_single_state(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(seed, "THERMAL_PERSISTENCE", 1.0)

        for region in _sample(100):
            assert len({_thermal_state(day) for day in region.values()}) == 1

    def test_no_persistence_changes_state_often(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(seed, "THERMAL_PERSISTENCE", 0.0)

        same = total = 0
        for region in _sample(500):
            states = [_thermal_state(region[day]) for day in sorted(region)]
            same += sum(a == b for a, b in zip(states, states[1:]))
            total += len(states) - 1

        assert same / total == pytest.approx(0.34, abs=0.03)

    def test_next_thermal_state_returns_a_known_state_without_history(self) -> None:
        rng = random.Random(5)

        assert {next_thermal_state(None, rng) for _ in range(200)} == {"calido", "frio", "templado"}

    def test_next_thermal_state_keeps_the_previous_one_with_full_persistence(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(seed, "THERMAL_PERSISTENCE", 1.0)
        rng = random.Random(5)

        assert all(next_thermal_state("frio", rng) == "frio" for _ in range(100))


class TestRainAndStorm:
    def test_values_are_valid_probabilities(self) -> None:
        rng = random.Random(9)

        for _ in range(2000):
            rain, storm = rain_and_storm(rng)
            assert rain in PROBABILITIES
            assert storm in PROBABILITIES

    def test_derived_storm_never_exceeds_rain(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(seed, "STORM_FROM_RAIN", 1.0)
        rng = random.Random(9)

        for _ in range(2000):
            rain, storm = rain_and_storm(rng)
            assert 0 <= storm <= rain

    def test_independent_storm_can_exceed_rain(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(seed, "STORM_FROM_RAIN", 0.0)
        rng = random.Random(9)

        draws = [rain_and_storm(rng) for _ in range(2000)]

        assert any(storm > rain for rain, storm in draws)

    def test_rain_favors_low_values(self) -> None:
        rng = random.Random(9)

        rains = Counter(rain_and_storm(rng)[0] for _ in range(5000))

        assert rains[0] > rains[60] > rains[100]

    def test_storm_is_correlated_with_rain_but_not_always(self) -> None:
        rng = random.Random(9)
        draws = [rain_and_storm(rng) for _ in range(10_000)]

        storms_in_heavy_rain = [storm for rain, storm in draws if rain >= 60]
        storms_without_rain = [storm for rain, storm in draws if rain == 0]
        mean_heavy = sum(storms_in_heavy_rain) / len(storms_in_heavy_rain)
        mean_dry = sum(storms_without_rain) / len(storms_without_rain)

        assert mean_heavy > mean_dry + 20
        assert any(rain == 0 and storm > 0 for rain, storm in draws)
        assert any(rain >= 60 and storm == 0 for rain, storm in draws)


def test_event_names_are_the_four_expected_ones() -> None:
    assert set(EVENTS) == {RAIN, FROST, HEAT, STORM} == {
        "lluvia",
        "helada",
        "calor extremo",
        "tormenta",
    }
