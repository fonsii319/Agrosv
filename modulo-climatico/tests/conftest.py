"""Fixtures: modelo normalizado sintético sin tocar la red."""

from __future__ import annotations

from datetime import date, timedelta

import pytest


def _day(offset: int, tmax=30.0, tmin=21.0, precip=0.0, pop=50, et0=4.0, source="observed_by_model"):
    return {
        "date": (date.today() + timedelta(days=offset)).isoformat(),
        "source_type": source,
        "temperature_max_c": tmax,
        "temperature_min_c": tmin,
        "precipitation_mm": precip,
        "precipitation_probability_pct": pop,
        "et0_mm": et0,
    }


@pytest.fixture
def normalized_base() -> dict:
    """7 días pasados observados + 7 de pronóstico, sin huecos."""
    past = [_day(-i, precip=5.0) for i in range(7, 0, -1)]
    forecast = [_day(i, precip=4.0, source="forecast") for i in range(7)]
    return {
        "location": {"latitude": 13.69, "longitude": -89.19, "elevation_m": 645, "timezone": "America/El_Salvador"},
        "current": {
            "time": date.today().isoformat() + "T12:00",
            "source_type": "observed_by_model",
            "temperature_c": 28.5,
            "relative_humidity_pct": 70,
            "precipitation_mm": 0.0,
            "wind_speed_kmh": 8.0,
            "units": {},
        },
        "past": past,
        "forecast": forecast,
        "qa": {"completeness": 1.0, "missing": [], "out_of_range": [], "cache": {}, "issues": []},
        "metadata": {"provider": "open-meteo", "retrieved_at": None, "units_system": "metric"},
    }


@pytest.fixture
def indicators_base(normalized_base):
    from app import indicators
    return indicators.compute_indicators(normalized_base)
