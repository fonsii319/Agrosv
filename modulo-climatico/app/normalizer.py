"""Normalización y control de calidad (Fase 4 de la guía).

Reglas de oro implementadas:
- SEPARAR siempre observado / pronóstico / histórico / simulado (source_type).
- Nunca sustituir silenciosamente un dato faltante por cero: se marca
  quality_flag="missing" y el indicador reporta completitud.
- Conservar unidades explícitas y marcar valores físicamente imposibles.
"""

from __future__ import annotations

from datetime import date
from typing import Any

# Rangos físicos de sanidad (cap. 5.1: "valores físicamente imposibles").
PHYSICAL_RANGES = {
    "temperature_c": (-40.0, 55.0),
    "relative_humidity_pct": (0.0, 100.0),
    "precipitation_mm": (0.0, 500.0),       # mm/día; 500 es cota de sanidad, no umbral agronómico
    "wind_speed_kmh": (0.0, 250.0),
    "et0_mm": (0.0, 20.0),
    "precipitation_probability_pct": (0.0, 100.0),
}


def _qa(value: float | None, variable: str) -> str:
    """Etiqueta de calidad para un valor individual."""
    if value is None:
        return "missing"
    lo, hi = PHYSICAL_RANGES[variable]
    if not (lo <= value <= hi):
        return "out_of_range"
    return "ok"


def normalize_forecast(envelope: dict[str, Any]) -> dict[str, Any]:
    """Convierte la respuesta cruda de Open-Meteo en el modelo normalizado.

    Devuelve:
      current  — condiciones actuales (source_type="observed_by_model")
      past     — días previos a hoy (source_type="observed_by_model")
      forecast — hoy y días futuros (source_type="forecast")
      qa       — resumen de control de calidad
    """
    raw = envelope["raw"]
    qa_issues: list[str] = []
    cache = envelope.get("cache", {})
    if cache.get("stale"):
        qa_issues.append("cache_stale: se muestra la última respuesta válida; el proveedor no respondió")

    today = date.today().isoformat()

    # --- Condiciones actuales ---
    cur = raw.get("current", {})
    cur_units = raw.get("current_units", {})
    current = {
        "time": cur.get("time"),
        "source_type": "observed_by_model",  # análisis del modelo, no estación de la parcela
        "temperature_c": _qa_val(cur.get("temperature_2m"), "temperature_c", qa_issues, "current.temperature_2m"),
        "relative_humidity_pct": _qa_val(cur.get("relative_humidity_2m"), "relative_humidity_pct", qa_issues, "current.relative_humidity_2m"),
        "precipitation_mm": _qa_val(cur.get("precipitation"), "precipitation_mm", qa_issues, "current.precipitation"),
        "wind_speed_kmh": _qa_val(cur.get("wind_speed_10m"), "wind_speed_kmh", qa_issues, "current.wind_speed_10m"),
        "units": {k: cur_units.get(k) for k in ("temperature_2m", "relative_humidity_2m", "precipitation", "wind_speed_10m")},
    }

    # --- Serie diaria: separar pasado (observado) de futuro (pronóstico) ---
    daily = raw.get("daily", {})
    times = daily.get("time", [])
    past_days: list[dict[str, Any]] = []
    forecast_days: list[dict[str, Any]] = []

    def col(name: str, i: int) -> float | None:
        values = daily.get(name) or []
        return values[i] if i < len(values) else None

    for i, day in enumerate(times):
        row = {
            "date": day,
            "temperature_max_c": _qa_val(col("temperature_2m_max", i), "temperature_c", qa_issues, f"daily.{day}.tmax"),
            "temperature_min_c": _qa_val(col("temperature_2m_min", i), "temperature_c", qa_issues, f"daily.{day}.tmin"),
            "precipitation_mm": _qa_val(col("precipitation_sum", i), "precipitation_mm", qa_issues, f"daily.{day}.precip"),
            "precipitation_probability_pct": _qa_val(col("precipitation_probability_max", i), "precipitation_probability_pct", qa_issues, f"daily.{day}.pop"),
            "et0_mm": _qa_val(col("et0_fao_evapotranspiration", i), "et0_mm", qa_issues, f"daily.{day}.et0"),
        }
        if day < today:
            row["source_type"] = "observed_by_model"
            past_days.append(row)
        else:
            row["source_type"] = "forecast"
            forecast_days.append(row)

    missing = [i for i in qa_issues if i.endswith(": missing")]
    out_of_range = [i for i in qa_issues if i.endswith(": out_of_range")]
    completeness = 1.0
    total_cells = len(times) * 5 + 4
    if total_cells:
        completeness = max(0.0, 1.0 - len(missing) / total_cells)

    return {
        "location": {
            "latitude": raw.get("latitude"),
            "longitude": raw.get("longitude"),
            "elevation_m": raw.get("elevation"),
            "timezone": raw.get("timezone"),
        },
        "current": current,
        "past": past_days,
        "forecast": forecast_days,
        "qa": {
            "completeness": round(completeness, 3),
            "missing": missing,
            "out_of_range": out_of_range,
            "cache": cache,
            "issues": qa_issues,
        },
        "metadata": {
            "provider": envelope.get("provider"),
            "retrieved_at": envelope.get("retrieved_at"),
            "units_system": "metric",
        },
    }


def _qa_val(value: float | None, variable: str, issues: list[str], path: str) -> float | None:
    flag = _qa(value, variable)
    if flag != "ok":
        issues.append(f"{path}: {flag}")
    return value


def normalize_history(envelope: dict[str, Any]) -> dict[str, Any]:
    """Serie histórica diaria (reanálisis ERA5). source_type='historical_reanalysis'."""
    raw = envelope["raw"]
    daily = raw.get("daily", {})
    times = daily.get("time", [])
    qa_issues: list[str] = []
    days: list[dict[str, Any]] = []

    def col(name: str, i: int) -> float | None:
        values = daily.get(name) or []
        return values[i] if i < len(values) else None

    for i, day in enumerate(times):
        days.append({
            "date": day,
            "source_type": "historical_reanalysis",
            "temperature_max_c": _qa_val(col("temperature_2m_max", i), "temperature_c", qa_issues, f"history.{day}.tmax"),
            "temperature_min_c": _qa_val(col("temperature_2m_min", i), "temperature_c", qa_issues, f"history.{day}.tmin"),
            "precipitation_mm": _qa_val(col("precipitation_sum", i), "precipitation_mm", qa_issues, f"history.{day}.precip"),
            "et0_mm": _qa_val(col("et0_fao_evapotranspiration", i), "et0_mm", qa_issues, f"history.{day}.et0"),
        })

    return {
        "days": days,
        "qa": {"issues": qa_issues, "cache": envelope.get("cache", {})},
        "metadata": {
            "provider": envelope.get("provider"),
            "retrieved_at": envelope.get("retrieved_at"),
            "note": "Reanálisis ERA5/ERA5-Land: no es observación directa de estación.",
        },
    }
