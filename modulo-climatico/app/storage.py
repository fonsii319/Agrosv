"""Almacenamiento mínimo en JSON para el MVP (parcelas y ciclos de cultivo).

Sustituible por una base de datos real sin tocar adaptadores ni motor
(la guía exige componentes desacoplados, cap. 8).
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PARCELS_FILE = DATA_DIR / "parcels.json"
CYCLES_FILE = DATA_DIR / "crop_cycles.json"

# Parcela de demostración: coordenadas de San Salvador (guía cap. 3.2, ilustrativas)
DEMO_PARCEL = {
    "id": "parcela-demo",
    "user_id": "demo",
    "name": "Parcela Demo — San Salvador",
    "latitude": 13.69,
    "longitude": -89.19,
    "elevation_m": 645,
    "country_code": "SV",
    "admin_area": "San Salvador",
    "timezone": "America/El_Salvador",
    "soil_type": "franco (reportado, sin análisis)",
    "slope_pct": 8.0,
    "drainage": "moderado (reportado)",
}


def _load(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def _save(path: Path, data: Any) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def list_parcels() -> list[dict[str, Any]]:
    parcels = _load(PARCELS_FILE, [])
    if not any(p.get("id") == DEMO_PARCEL["id"] for p in parcels):
        parcels.insert(0, DEMO_PARCEL)
        _save(PARCELS_FILE, parcels)
    return parcels


def get_parcel(parcel_id: str) -> dict[str, Any] | None:
    for parcel in list_parcels():
        if parcel.get("id") == parcel_id:
            return parcel
    return None


def create_parcel(payload: dict[str, Any]) -> dict[str, Any]:
    parcels = list_parcels()
    parcel = {
        "id": f"parcela-{uuid.uuid4().hex[:8]}",
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        **payload,
    }
    parcels.append(parcel)
    _save(PARCELS_FILE, parcels)
    return parcel


def create_crop_cycle(payload: dict[str, Any]) -> dict[str, Any]:
    cycles = _load(CYCLES_FILE, [])
    cycle = {
        "id": f"ciclo-{uuid.uuid4().hex[:8]}",
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        **payload,
    }
    cycles.append(cycle)
    _save(CYCLES_FILE, cycles)
    return cycle


def get_active_cycle(parcel_id: str) -> dict[str, Any] | None:
    cycles = [c for c in _load(CYCLES_FILE, []) if c.get("parcel_id") == parcel_id]
    return cycles[-1] if cycles else None
