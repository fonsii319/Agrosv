"""Adaptador Open-Meteo (Fase 3 de la guía).

Responsabilidades:
- Consultar pronóstico (Forecast API) e historial/reanálisis ERA5 (Archive API).
- Timeout configurable, reintentos limitados con backoff.
- Caché en disco de la última respuesta válida; si el proveedor falla,
  se sirve la caché marcada como "stale_cache" (nunca se silencia el origen).
- Guardar la respuesta CRUDA con proveedor, hora de consulta y modelo,
  tal como exige la guía (cap. 3.6 y 8.3).

Open-Meteo no requiere API key para uso no comercial (revisar términos).
Atribución: datos CC BY 4.0 (open-meteo.com).
"""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
PROVIDER = "open-meteo"

# Raíz de datos del proyecto (data/ junto a app/)
DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
CACHE_DIR = DATA_DIR / "cache"
RAW_DIR = DATA_DIR / "raw"

TIMEOUT_S = 15.0
MAX_RETRIES = 2
CACHE_TTL_FORECAST_S = 30 * 60      # pronóstico: 30 min
CACHE_TTL_HISTORY_S = 24 * 3600     # histórico: 24 h (serie cerrada)


class ProviderError(Exception):
    """El proveedor no respondió o respondió inválido. Lleva el detalle para auditoría."""


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _cache_key(url: str, params: dict[str, Any]) -> str:
    raw = url + "|" + json.dumps(params, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def _read_cache(key: str) -> dict[str, Any] | None:
    path = CACHE_DIR / f"{key}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _write_cache(key: str, envelope: dict[str, Any]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (CACHE_DIR / f"{key}.json").write_text(
        json.dumps(envelope, ensure_ascii=False), encoding="utf-8"
    )


def _save_raw(envelope: dict[str, Any], kind: str) -> None:
    """Guarda la respuesta cruda para trazabilidad (proveedor, hora, modelo)."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    name = f"{kind}_{PROVIDER}_{stamp}_{_cache_key(kind, envelope['request_params'])}.json"
    (RAW_DIR / name).write_text(
        json.dumps(envelope, ensure_ascii=False, indent=1), encoding="utf-8"
    )


def _fetch(url: str, params: dict[str, Any], kind: str, cache_ttl_s: int) -> dict[str, Any]:
    """GET con reintentos + caché. Devuelve sobre {provider, retrieved_at, request_params, raw, cache}."""
    key = _cache_key(url, params)
    cached = _read_cache(key)
    if cached is not None:
        age_s = time.time() - cached.get("cached_at_epoch", 0)
        if age_s <= cache_ttl_s:
            cached["cache"] = {"hit": True, "age_seconds": int(age_s), "stale": False}
            return cached

    last_error: str | None = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            with httpx.Client(timeout=TIMEOUT_S) as client:
                resp = client.get(url, params=params)
            resp.raise_for_status()
            payload = resp.json()
            if not isinstance(payload, dict) or "latitude" not in payload:
                raise ProviderError(f"Respuesta inesperada del proveedor: {str(payload)[:200]}")

            envelope = {
                "provider": PROVIDER,
                "retrieved_at": _utc_now_iso(),
                "cached_at_epoch": time.time(),
                "request_params": params,
                "raw": payload,
                "cache": {"hit": False, "age_seconds": 0, "stale": False},
            }
            _write_cache(key, envelope)
            _save_raw(envelope, kind)
            return envelope
        except (httpx.HTTPError, ProviderError, json.JSONDecodeError) as exc:  # red, HTTP, JSON
            last_error = str(exc)
            if attempt < MAX_RETRIES:
                time.sleep(0.5 * (attempt + 1))  # backoff simple

    # Proveedor caído: usar caché vieja si existe, marcándola como stale.
    if cached is not None:
        cached["cache"] = {
            "hit": True,
            "age_seconds": int(time.time() - cached.get("cached_at_epoch", 0)),
            "stale": True,
            "provider_error": last_error,
        }
        return cached
    raise ProviderError(f"Proveedor no disponible y sin caché previa: {last_error}")


def get_forecast(lat: float, lon: float, forecast_days: int = 7, past_days: int = 30) -> dict[str, Any]:
    """Pronóstico + pasado reciente.

    past_days>0 entrega días OBSERVADOS (reanálisis de modelo) antes de hoy;
    el normalizador los separa del pronóstico: nunca se mezclan ambos tipos.
    """
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m",
        "hourly": "temperature_2m,relative_humidity_2m,precipitation_probability,precipitation,wind_speed_10m",
        "daily": (
            "temperature_2m_max,temperature_2m_min,precipitation_sum,"
            "precipitation_probability_max,et0_fao_evapotranspiration"
        ),
        "forecast_days": forecast_days,
        "past_days": past_days,
        "timezone": "America/El_Salvador",
    }
    return _fetch(FORECAST_URL, params, kind="forecast", cache_ttl_s=CACHE_TTL_FORECAST_S)


def get_history(lat: float, lon: float, start_date: str, end_date: str) -> dict[str, Any]:
    """Serie histórica diaria (reanálisis ERA5/ERA5-Land). NO es observación de estación."""
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start_date,
        "end_date": end_date,
        "daily": (
            "temperature_2m_max,temperature_2m_min,precipitation_sum,"
            "et0_fao_evapotranspiration"
        ),
        "timezone": "America/El_Salvador",
    }
    return _fetch(ARCHIVE_URL, params, kind="history", cache_ttl_s=CACHE_TTL_HISTORY_S)
