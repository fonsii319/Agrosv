"""API backend del Módulo Climático (Fases 3-6).

Endpoints según guía cap. 8.6. Sirve además el dashboard estático.

Ejecutar:  uv run uvicorn app.main:app --reload --port 8000
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import engine, indicators, normalizer, simulated, storage
from .adapters import open_meteo

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

app = FastAPI(
    title="Módulo Climático — Asistente Agronómico",
    version="0.1.0",
    description="MVP hackathon: clima + reglas agronómicas explicables para El Salvador.",
)

# CORS abierto solo para el prototipo local; restringir en producción (cap. 8.7).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ParcelIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    elevation_m: float | None = None
    country_code: str = "SV"
    admin_area: str | None = None
    timezone: str = "America/El_Salvador"
    soil_type: str | None = None
    slope_pct: float | None = Field(default=None, ge=0, le=100)
    drainage: str | None = None


class CropCycleIn(BaseModel):
    parcel_id: str
    crop_code: str
    variety: str | None = None
    sowing_date: str | None = None
    phenological_stage: str
    irrigation_type: str | None = None
    area_ha: float | None = Field(default=None, gt=0)


def _parcel_or_404(parcel_id: str) -> dict[str, Any]:
    parcel = storage.get_parcel(parcel_id)
    if parcel is None:
        raise HTTPException(status_code=404, detail=f"Parcela no encontrada: {parcel_id}")
    return parcel


def _normalized_for(parcel: dict[str, Any]) -> dict[str, Any]:
    envelope = open_meteo.get_forecast(parcel["latitude"], parcel["longitude"], forecast_days=7, past_days=30)
    return normalizer.normalize_forecast(envelope)


@app.get("/api/v1/health")
def health() -> dict[str, str]:
    return {"status": "ok", "module": "modulo-climatico", "version": "0.1.0"}


@app.get("/api/v1/parcels")
def list_parcels() -> list[dict[str, Any]]:
    return storage.list_parcels()


@app.post("/api/v1/parcels", status_code=201)
def create_parcel(payload: ParcelIn) -> dict[str, Any]:
    data = payload.model_dump(exclude_none=True)
    # Aviso (no bloqueo) si la parcela cae fuera de El Salvador continental
    if not (13.1 <= payload.latitude <= 14.5 and -90.2 <= payload.longitude <= -87.6):
        data["location_warning"] = "Coordenadas fuera del rango continental de El Salvador; verifique el punto."
    return storage.create_parcel(data)


@app.post("/api/v1/crop-cycles", status_code=201)
def create_crop_cycle(payload: CropCycleIn) -> dict[str, Any]:
    _parcel_or_404(payload.parcel_id)
    return storage.create_crop_cycle(payload.model_dump(exclude_none=True))


@app.get("/api/v1/parcels/{parcel_id}/weather")
def get_weather(parcel_id: str) -> dict[str, Any]:
    parcel = _parcel_or_404(parcel_id)
    normalized = _normalized_for(parcel)
    return {
        "parcel": parcel,
        "weather": normalized,
        "indicators": indicators.compute_indicators(normalized),
    }


@app.get("/api/v1/parcels/{parcel_id}/history")
def get_history(
    parcel_id: str,
    days: int = Query(default=30, ge=5, le=90),
) -> dict[str, Any]:
    """Serie histórica (reanálisis ERA5) + agregados. NO es observación de estación."""
    parcel = _parcel_or_404(parcel_id)
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=days - 1)
    envelope = open_meteo.get_history(parcel["latitude"], parcel["longitude"], start.isoformat(), end.isoformat())
    history = normalizer.normalize_history(envelope)
    precip = [d["precipitation_mm"] for d in history["days"]]
    return {
        "parcel": parcel,
        "history": history,
        "aggregates": {
            "precip_total_mm": round(sum(v for v in precip if v is not None), 1),
            "days_with_data": sum(1 for v in precip if v is not None),
            "dry_streak": indicators._dry_streak(precip, indicators.DRY_DAY_THRESHOLD_MM),
        },
    }


@app.get("/api/v1/parcels/{parcel_id}/risks")
def get_risks(
    parcel_id: str,
    crop: str = Query(default="maiz"),
    stage: str = Query(default="pre_sowing"),
) -> dict[str, Any]:
    parcel = _parcel_or_404(parcel_id)
    normalized = _normalized_for(parcel)
    ind = indicators.compute_indicators(normalized)
    result = engine.evaluate(
        crop=crop, stage=stage, region=parcel.get("country_code", "SV"),
        indicators=ind, qa=normalized["qa"], metadata=normalized["metadata"],
        forecast_horizon_days=len(normalized["forecast"]),
    )
    return {
        "parcel": parcel,
        "crop": crop,
        "stage": stage,
        "risk_evaluation": result,
    }


@app.get("/api/v1/parcels/{parcel_id}/advice")
def get_advice(
    parcel_id: str,
    crop: str = Query(default="maiz"),
    stage: str = Query(default="pre_sowing"),
    soil_moisture_observed: str | None = Query(
        default=None,
        description="Observación de campo del agricultor: 'ok', 'seco' o null (sin dato)",
    ),
) -> dict[str, Any]:
    parcel = _parcel_or_404(parcel_id)
    normalized = _normalized_for(parcel)
    ind = indicators.compute_indicators(normalized)

    field: dict[str, Any] = {"soil_moisture_observed": None}
    if soil_moisture_observed in ("ok", "seco"):
        field["soil_moisture_observed"] = soil_moisture_observed

    result = engine.evaluate(
        crop=crop, stage=stage, region=parcel.get("country_code", "SV"),
        indicators=ind, qa=normalized["qa"], metadata=normalized["metadata"], field=field,
        forecast_horizon_days=len(normalized["forecast"]),
    )
    # Contrato para frontend (guía cap. 8.5)
    return {
        "parcel": parcel,
        "weather": {
            "issued_at": normalized["current"].get("time"),
            "source_type": "forecast",
            "current": normalized["current"],
            "daily": normalized["forecast"],
        },
        "agronomy": {
            "crop": crop,
            "stage": stage,
            "planting_suitability": result["status"],
            "confidence": result["confidence"],
            "recommendation": result,
        },
        "indicators": ind,
        "metadata": normalized["metadata"],
    }


@app.get("/api/v1/demo/scenario/{name}")
def demo_scenario(
    name: str,
    crop: str = Query(default="maiz"),
    stage: str = Query(default="pre_sowing"),
) -> dict[str, Any]:
    """Escenario SIMULADO claramente etiquetado para la demo ante jueces (cap. 12.1/12.3)."""
    try:
        fake = simulated.build_scenario(name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    ind = indicators.compute_indicators(fake)
    result = engine.evaluate(
        crop=crop, stage=stage, region="SV",
        indicators=ind, qa=fake["qa"], metadata=fake["metadata"],
        forecast_horizon_days=len(fake["forecast"]),
    )
    return {
        "simulated": True,
        "label": fake["label"],
        "scenario": name,
        "weather": {
            "issued_at": fake["current"].get("time"),
            "source_type": "simulated",
            "current": fake["current"],
            "daily": fake["forecast"],
        },
        "agronomy": {
            "crop": crop,
            "stage": stage,
            "planting_suitability": result["status"],
            "confidence": result["confidence"],
            "recommendation": result,
        },
        "indicators": ind,
        "metadata": fake["metadata"],
    }


# --- Dashboard estático ---
@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
