"""Indicadores: acumulados, días faltantes, rachas secas (guía 11.2/11.3)."""

from __future__ import annotations

from app import indicators


def test_accumulation_complete(normalized_base):
    ind = indicators.compute_indicators(normalized_base)
    assert ind["rain_observed"]["accum_7d"]["value_mm"] == 35.0
    assert ind["rain_observed"]["accum_7d"]["quality"] == "complete"
    assert ind["rain_forecast"]["accum_7d"]["value_mm"] == 28.0


def test_missing_days_are_not_zero_rain(normalized_base):
    """Un día faltante NO cuenta como lluvia cero: reduce completitud."""
    normalized_base["past"][-1]["precipitation_mm"] = None
    normalized_base["past"][-2]["precipitation_mm"] = None
    ind = indicators.compute_indicators(normalized_base)
    acc = ind["rain_observed"]["accum_7d"]
    assert acc["value_mm"] == 25.0          # 5 días con dato x 5 mm
    assert acc["days_missing"] == 2
    assert acc["quality"] == "incomplete"


def test_all_missing_means_no_value(normalized_base):
    for d in normalized_base["past"]:
        d["precipitation_mm"] = None
    ind = indicators.compute_indicators(normalized_base)
    assert ind["rain_observed"]["accum_7d"]["value_mm"] is None
    assert ind["rain_observed"]["accum_7d"]["quality"] == "missing"


def test_dry_streak_and_forecast_dry_spell(normalized_base):
    for d in normalized_base["past"]:
        d["precipitation_mm"] = 0.0
    normalized_base["past"][0]["precipitation_mm"] = 3.0  # rompe la racha hace 6 días
    for d in normalized_base["forecast"]:
        d["precipitation_mm"] = 0.2
    normalized_base["forecast"][5]["precipitation_mm"] = 8.0
    ind = indicators.compute_indicators(normalized_base)
    assert ind["rain_observed"]["dry_streak"]["days"] == 6
    assert ind["rain_forecast"]["dry_spell_ahead"]["days"] == 5
    assert ind["rain_forecast"]["days_with_rain_expected"] == 1


def test_dry_streak_truncated_by_missing(normalized_base):
    normalized_base["past"][-1]["precipitation_mm"] = None
    ind = indicators.compute_indicators(normalized_base)
    streak = ind["rain_observed"]["dry_streak"]
    assert streak["days"] == 0
    assert streak["truncated_by_missing_data"] is True


def test_et0_aggregation(normalized_base):
    ind = indicators.compute_indicators(normalized_base)
    assert ind["et0"]["observed_7d_mm"] == 28.0
    assert ind["et0"]["mean_forecast_mm_day"] == 4.0
