"""API: respuesta válida, proveedor caído con caché, contratos (guía 11.3)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.adapters import open_meteo
from app.main import app

client = TestClient(app)


def test_health():
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_advice_contract_for_frontend():
    """Contrato cap. 8.5: parcel, weather, agronomy, metadata."""
    resp = client.get("/api/v1/parcels/parcela-demo/advice?crop=maiz&stage=pre_sowing")
    assert resp.status_code == 200
    body = resp.json()
    assert body["parcel"]["id"] == "parcela-demo"
    assert body["weather"]["source_type"] == "forecast"
    assert body["agronomy"]["planting_suitability"] in ("favorable", "caution", "unfavorable")
    assert body["metadata"]["provider"] == "open-meteo"
    rec = body["agronomy"]["recommendation"]
    assert rec["reasons"] and rec["actions"] and rec["data_basis"]["retrieved_at"]


def test_parcel_not_found():
    assert client.get("/api/v1/parcels/no-existe/advice").status_code == 404


def test_create_parcel_and_cycle():
    resp = client.post("/api/v1/parcels", json={
        "name": "Parcela Prueba", "latitude": 13.7, "longitude": -89.2,
    })
    assert resp.status_code == 201
    parcel = resp.json()
    assert parcel["id"].startswith("parcela-")

    resp = client.post("/api/v1/crop-cycles", json={
        "parcel_id": parcel["id"], "crop_code": "maiz", "phenological_stage": "pre_sowing",
    })
    assert resp.status_code == 201


def test_invalid_coordinates_rejected():
    resp = client.post("/api/v1/parcels", json={
        "name": "Mala", "latitude": 95.0, "longitude": -89.2,
    })
    assert resp.status_code == 422


def test_provider_down_uses_stale_cache():
    """Proveedor caído: se sirve caché marcada como stale, no se oculta el fallo."""
    import time
    real_envelope = open_meteo.get_forecast(13.69, -89.19, forecast_days=7, past_days=7)
    # Forzar caché vieja (> TTL de 30 min) para que el adaptador intente la red
    real_envelope["cached_at_epoch"] = time.time() - 3600
    with patch.object(open_meteo.httpx, "Client") as mock_client:
        mock_client.return_value.__enter__.return_value.get.side_effect = open_meteo.httpx.ConnectError("caído")
        with patch.object(open_meteo, "_read_cache", return_value=real_envelope):
            env = open_meteo.get_forecast(13.69, -89.19, forecast_days=7, past_days=7)
    assert env["cache"]["stale"] is True
    assert "provider_error" in env["cache"]


def test_provider_down_without_cache_raises():
    with patch.object(open_meteo.httpx, "Client") as mock_client:
        mock_client.return_value.__enter__.return_value.get.side_effect = open_meteo.httpx.ConnectError("caído")
        with patch.object(open_meteo, "_read_cache", return_value=None):
            with pytest.raises(open_meteo.ProviderError):
                open_meteo.get_forecast(13.69, -89.19, forecast_days=1, past_days=0)


def test_demo_scenario_is_labeled_simulated():
    resp = client.get("/api/v1/demo/scenario/lluvia_intensa?crop=maiz&stage=pre_sowing")
    assert resp.status_code == 200
    body = resp.json()
    assert body["simulated"] is True
    assert "SIMULADOS" in body["label"]
    assert body["agronomy"]["planting_suitability"] == "unfavorable"


def test_demo_unknown_scenario_404():
    assert client.get("/api/v1/demo/scenario/inventado").status_code == 404
