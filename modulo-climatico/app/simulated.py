"""Escenarios SIMULADOS para la demostración (guía cap. 10 y 12.1).

Todos los valores son datos simulados para probar la lógica.
NO representan condiciones reales de ninguna localidad salvadoreña.
La API los entrega con source_type="simulated" y etiqueta visible.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

SCENARIO_NAMES = ["favorable", "lluvias_insuficientes", "lluvia_intensa", "racha_seca"]


def _day(offset: int, tmax: float, tmin: float, precip: float, pop: int, et0: float, source: str) -> dict[str, Any]:
    return {
        "date": (date.today() + timedelta(days=offset)).isoformat(),
        "source_type": source,
        "temperature_max_c": tmax,
        "temperature_min_c": tmin,
        "precipitation_mm": precip,
        "precipitation_probability_pct": pop,
        "et0_mm": et0,
    }


def build_scenario(name: str) -> dict[str, Any]:
    """Devuelve un modelo normalizado simulado con la MISMA estructura que normalizer.py."""
    if name not in SCENARIO_NAMES:
        raise KeyError(f"Escenario desconocido: {name}. Disponibles: {SCENARIO_NAMES}")

    # Pasado observado (reanálisis simulado): 7 días con lluvia distribuida
    past_wet = [
        _day(-7, 29.5, 20.5, 6.2, 0, 4.0, "simulated"),
        _day(-6, 29.0, 20.8, 12.4, 0, 3.8, "simulated"),
        _day(-5, 28.5, 21.0, 0.0, 0, 4.1, "simulated"),
        _day(-4, 29.2, 20.6, 8.5, 0, 4.3, "simulated"),
        _day(-3, 28.8, 21.2, 3.1, 0, 3.9, "simulated"),
        _day(-2, 29.6, 20.4, 0.4, 0, 4.4, "simulated"),
        _day(-1, 29.1, 20.9, 5.8, 0, 4.2, "simulated"),
    ]
    past_dry = [
        _day(-7, 31.5, 21.5, 0.0, 0, 4.8, "simulated"),
        _day(-6, 31.8, 21.2, 0.0, 0, 4.9, "simulated"),
        _day(-5, 32.0, 21.0, 0.3, 0, 5.0, "simulated"),
        _day(-4, 31.6, 21.4, 0.0, 0, 4.7, "simulated"),
        _day(-3, 31.9, 21.1, 0.0, 0, 4.8, "simulated"),
        _day(-2, 32.2, 21.3, 0.0, 0, 5.1, "simulated"),
        _day(-1, 31.7, 21.0, 0.0, 0, 4.9, "simulated"),
    ]

    scenarios: dict[str, dict[str, Any]] = {
        # Cap. 10.1: condiciones favorables para iniciar siembra
        "favorable": {
            "current": _current(28.5, 72, 0.0, 6.0),
            "past": past_wet,
            "forecast": [
                _day(0, 29.0, 21.0, 4.5, 60, 3.8, "simulated"),
                _day(1, 28.6, 20.8, 8.2, 70, 3.5, "simulated"),
                _day(2, 29.3, 21.1, 2.0, 45, 3.9, "simulated"),
                _day(3, 29.8, 21.3, 6.5, 65, 3.7, "simulated"),
                _day(4, 29.0, 20.9, 3.4, 55, 3.8, "simulated"),
                _day(5, 29.5, 21.0, 5.0, 60, 3.6, "simulated"),
                _day(6, 29.2, 20.7, 2.2, 50, 3.9, "simulated"),
            ],
        },
        # Cap. 10.2: lluvias insuficientes
        "lluvias_insuficientes": {
            "current": _current(31.0, 55, 0.0, 9.0),
            "past": past_dry,
            "forecast": [
                _day(0, 31.5, 21.5, 0.0, 10, 4.9, "simulated"),
                _day(1, 32.0, 21.2, 0.0, 5, 5.0, "simulated"),
                _day(2, 31.8, 21.4, 0.0, 15, 4.8, "simulated"),
                _day(3, 31.2, 21.0, 1.2, 30, 4.6, "simulated"),
                _day(4, 31.6, 21.3, 0.0, 10, 4.9, "simulated"),
                _day(5, 32.1, 21.1, 0.0, 5, 5.1, "simulated"),
                _day(6, 31.9, 21.2, 0.4, 20, 4.8, "simulated"),
            ],
        },
        # Cap. 10.3: lluvias excesivas antes de siembra
        "lluvia_intensa": {
            "current": _current(27.0, 90, 12.0, 15.0),
            "past": past_wet,
            "forecast": [
                _day(0, 27.5, 21.5, 35.0, 90, 2.8, "simulated"),
                _day(1, 27.0, 21.8, 58.0, 95, 2.5, "simulated"),
                _day(2, 27.8, 21.6, 22.0, 80, 2.9, "simulated"),
                _day(3, 28.5, 21.2, 8.0, 60, 3.3, "simulated"),
                _day(4, 29.0, 21.0, 2.0, 40, 3.7, "simulated"),
                _day(5, 29.4, 20.8, 0.5, 25, 4.0, "simulated"),
                _day(6, 29.6, 20.6, 0.0, 15, 4.2, "simulated"),
            ],
        },
        # Racha seca prolongada (estrés en establecimiento)
        "racha_seca": {
            "current": _current(32.5, 48, 0.0, 11.0),
            "past": past_dry,
            "forecast": [
                _day(0, 32.8, 21.8, 0.0, 5, 5.2, "simulated"),
                _day(1, 33.0, 21.5, 0.0, 5, 5.3, "simulated"),
                _day(2, 32.5, 21.2, 0.0, 10, 5.1, "simulated"),
                _day(3, 32.2, 21.0, 0.0, 10, 5.0, "simulated"),
                _day(4, 31.8, 20.8, 0.0, 15, 4.8, "simulated"),
                _day(5, 31.5, 20.9, 0.6, 25, 4.6, "simulated"),
                _day(6, 31.9, 21.1, 0.0, 15, 4.9, "simulated"),
            ],
        },
    }

    selected = scenarios[name]
    return {
        "simulated": True,
        "scenario": name,
        "label": "DATOS SIMULADOS — no representan condiciones reales",
        "location": {
            "latitude": 13.69,
            "longitude": -89.19,
            "elevation_m": 645,
            "timezone": "America/El_Salvador",
        },
        "current": selected["current"],
        "past": selected["past"],
        "forecast": selected["forecast"],
        "qa": {"completeness": 1.0, "missing": [], "out_of_range": [], "cache": {}, "issues": []},
        "metadata": {
            "provider": "simulated",
            "retrieved_at": date.today().isoformat() + "T00:00:00-06:00",
            "units_system": "metric",
        },
    }


def _current(temp: float, rh: float, precip: float, wind: float) -> dict[str, Any]:
    return {
        "time": date.today().isoformat() + "T12:00",
        "source_type": "simulated",
        "temperature_c": temp,
        "relative_humidity_pct": rh,
        "precipitation_mm": precip,
        "wind_speed_kmh": wind,
        "units": {"temperature_2m": "°C", "relative_humidity_2m": "%", "precipitation": "mm", "wind_speed_10m": "km/h"},
    }
