"""Normalizador: separación observado/pronóstico, QA, nulos (guía 11.3)."""

from __future__ import annotations

from datetime import date, timedelta

from app import normalizer


def _envelope(daily_overrides=None, current_overrides=None):
    today = date.today()
    days = [(today + timedelta(days=o)).isoformat() for o in (-2, -1, 0, 1)]
    daily = {
        "time": days,
        "temperature_2m_max": [30.0, 31.0, 29.0, 28.0],
        "temperature_2m_min": [20.0, 21.0, 20.5, 19.5],
        "precipitation_sum": [5.0, 0.0, 2.0, 8.0],
        "precipitation_probability_max": [None, None, 60, 80],
        "et0_fao_evapotranspiration": [4.0, 4.1, 3.9, 3.8],
    }
    if daily_overrides:
        daily.update(daily_overrides)
    current = {
        "time": today.isoformat() + "T12:00",
        "temperature_2m": 28.0,
        "relative_humidity_2m": 65,
        "precipitation": 0.0,
        "wind_speed_10m": 7.0,
    }
    if current_overrides:
        current.update(current_overrides)
    return {
        "provider": "open-meteo",
        "retrieved_at": "2026-11-21T20:00:00+00:00",
        "request_params": {},
        "cache": {"hit": False, "age_seconds": 0, "stale": False},
        "raw": {
            "latitude": 13.69,
            "longitude": -89.19,
            "elevation": 645.0,
            "timezone": "America/El_Salvador",
            "current_units": {},
            "current": current,
            "daily_units": {},
            "daily": daily,
        },
    }


def test_observed_and_forecast_are_separated():
    """Los días previos a hoy se etiquetan observados; hoy y futuro, pronóstico."""
    norm = normalizer.normalize_forecast(_envelope())
    assert len(norm["past"]) == 2
    assert len(norm["forecast"]) == 2
    assert {d["source_type"] for d in norm["past"]} == {"observed_by_model"}
    assert {d["source_type"] for d in norm["forecast"]} == {"forecast"}


def test_null_values_flagged_not_zeroed():
    norm = normalizer.normalize_forecast(_envelope(current_overrides={"temperature_2m": None}))
    assert norm["current"]["temperature_c"] is None
    assert any("current.temperature_2m: missing" in i for i in norm["qa"]["issues"])
    assert norm["qa"]["completeness"] < 1.0


def test_physically_impossible_value_flagged():
    norm = normalizer.normalize_forecast(_envelope(current_overrides={"relative_humidity_2m": 140}))
    assert any("out_of_range" in i for i in norm["qa"]["issues"])


def test_stale_cache_flag_visible():
    env = _envelope()
    env["cache"] = {"hit": True, "age_seconds": 3600, "stale": True, "provider_error": "timeout"}
    norm = normalizer.normalize_forecast(env)
    assert any("cache_stale" in i for i in norm["qa"]["issues"])


def test_local_date_vs_utc_boundary():
    """La partición observado/pronóstico usa la fecha LOCAL de la zona horaria de la parcela."""
    norm = normalizer.normalize_forecast(_envelope())
    today = date.today().isoformat()
    assert all(d["date"] < today for d in norm["past"])
    assert all(d["date"] >= today for d in norm["forecast"])
