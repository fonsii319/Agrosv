"""Motor de indicadores (Fase 4).

Calcula acumulados de lluvia (3/7/30 días), racha seca observada, racha seca
pronosticada, ET₀ acumulada y estadísticos de temperatura.

- Días faltantes NUNCA cuentan como lluvia cero: reducen la completitud.
- El umbral de día seco es un parámetro operativo configurable (guía 11.2:
  1.0 mm/día como ejemplo, NO universal).
"""

from __future__ import annotations

from typing import Any

DRY_DAY_THRESHOLD_MM = 1.0  # parámetro operativo del prototipo, validar localmente


def _values(days: list[dict[str, Any]], key: str) -> list[float | None]:
    return [d.get(key) for d in days]


def _accumulate(values: list[float | None], window: int) -> dict[str, Any]:
    """Suma los últimos `window` valores. None reduce completitud, no suma cero."""
    tail = values[-window:] if window > 0 else []
    known = [v for v in tail if v is not None]
    missing = len(tail) - len(known)
    return {
        "value_mm": round(sum(known), 1) if known else None,
        "window_days": len(tail),
        "days_with_data": len(known),
        "days_missing": missing,
        "quality": "complete" if missing == 0 and tail else ("incomplete" if known else "missing"),
    }


def _dry_streak(values: list[float | None], threshold_mm: float) -> dict[str, Any]:
    """Días secos consecutivos hasta el último dato. None corta la racha con incertidumbre."""
    streak = 0
    truncated_by_missing = False
    for v in reversed(values):
        if v is None:
            truncated_by_missing = True
            break
        if v < threshold_mm:
            streak += 1
        else:
            break
    return {
        "days": streak,
        "threshold_mm_per_day": threshold_mm,
        "truncated_by_missing_data": truncated_by_missing,
    }


def _dry_spell_forward(values: list[float | None], threshold_mm: float) -> dict[str, Any]:
    """Días secos consecutivos DESDE HOY hacia adelante (cuánto falta para la próxima lluvia).

    Es la pregunta agronómica relevante: si siembro hoy, ¿cuántos días secos siguen?
    """
    streak = 0
    truncated_by_missing = False
    for v in values:
        if v is None:
            truncated_by_missing = True
            break
        if v < threshold_mm:
            streak += 1
        else:
            break
    return {
        "days": streak,
        "threshold_mm_per_day": threshold_mm,
        "truncated_by_missing_data": truncated_by_missing,
    }


def compute_indicators(normalized: dict[str, Any]) -> dict[str, Any]:
    """Indicadores a partir del modelo normalizado (past = observado, forecast = pronóstico)."""
    past = normalized.get("past", [])
    forecast = normalized.get("forecast", [])
    past_precip = _values(past, "precipitation_mm")
    fc_precip = _values(forecast, "precipitation_mm")

    past_et0 = [v for v in _values(past, "et0_mm") if v is not None]
    fc_et0 = [v for v in _values(forecast, "et0_mm") if v is not None]

    tmax_fc = [v for v in _values(forecast, "temperature_max_c") if v is not None]
    tmin_fc = [v for v in _values(forecast, "temperature_min_c") if v is not None]

    indicators = {
        # Lluvia OBSERVADA (reanálisis de modelo, días previos a hoy)
        "rain_observed": {
            "accum_3d": _accumulate(past_precip, 3),
            "accum_7d": _accumulate(past_precip, 7),
            "accum_30d": _accumulate(past_precip, 30),
            "dry_streak": _dry_streak(past_precip, DRY_DAY_THRESHOLD_MM),
            "source_type": "observed_by_model",
        },
        # Lluvia PRONOSTICADA (hoy en adelante)
        "rain_forecast": {
            "accum_3d": _accumulate(fc_precip, 3),
            "accum_7d": _accumulate(fc_precip, 7),
            "dry_spell_ahead": _dry_spell_forward(fc_precip, DRY_DAY_THRESHOLD_MM),
            "days_with_rain_expected": sum(1 for v in fc_precip if v is not None and v >= DRY_DAY_THRESHOLD_MM),
            "max_daily_mm": max((v for v in fc_precip if v is not None), default=None),
            "source_type": "forecast",
        },
        "et0": {
            "observed_7d_mm": round(sum(past_et0[-7:]), 1) if past_et0 else None,
            "forecast_7d_mm": round(sum(fc_et0[:7]), 1) if fc_et0 else None,
            "mean_forecast_mm_day": round(sum(fc_et0) / len(fc_et0), 2) if fc_et0 else None,
        },
        "temperature_forecast": {
            "tmax_max_c": max(tmax_fc) if tmax_fc else None,
            "tmin_min_c": min(tmin_fc) if tmin_fc else None,
            "source_type": "forecast",
        },
        "params": {"dry_day_threshold_mm": DRY_DAY_THRESHOLD_MM},
    }
    return indicators
