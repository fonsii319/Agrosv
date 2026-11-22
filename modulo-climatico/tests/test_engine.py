"""Motor agronómico: reglas por etapa, confianza, trazabilidad (guía 11.3)."""

from __future__ import annotations

from datetime import datetime, timezone

from app import engine

META = {"provider": "open-meteo", "retrieved_at": datetime.now(timezone.utc).isoformat(), "units_system": "metric"}
QA_OK = {"completeness": 1.0, "cache": {}}


def _ind(rain_fc_7d=25.0, dry_spell=1, dry_streak_obs=0, days_rain=3, max_daily=8.0, tmax=31.0):
    return {
        "rain_observed": {
            "accum_7d": {"value_mm": 20.0, "quality": "complete"},
            "dry_streak": {"days": dry_streak_obs, "threshold_mm_per_day": 1.0},
        },
        "rain_forecast": {
            "accum_7d": {"value_mm": rain_fc_7d, "quality": "complete"},
            "dry_spell_ahead": {"days": dry_spell, "threshold_mm_per_day": 1.0},
            "days_with_rain_expected": days_rain,
            "max_daily_mm": max_daily,
        },
        "et0": {"mean_forecast_mm_day": 4.0},
        "temperature_forecast": {"tmax_max_c": tmax, "tmin_min_c": 20.0},
        "params": {"dry_day_threshold_mm": 1.0},
    }


def test_rule_applicable_only_for_its_stage():
    """La regla de floración no aplica en pre-siembra y viceversa (guía 11.3)."""
    hot = _ind(tmax=36.0)
    flowering = engine.evaluate(crop="maiz", stage="flowering", region="SV",
                                indicators=hot, qa=QA_OK, metadata=META)
    assert "MAIZ_FLORACION_CALOR_V1" in [r["rule_id"] for r in flowering["matched_rules"]]

    pre_sowing = engine.evaluate(crop="maiz", stage="pre_sowing", region="SV",
                                 indicators=hot, qa=QA_OK, metadata=META)
    assert "MAIZ_FLORACION_CALOR_V1" not in [r["rule_id"] for r in pre_sowing["matched_rules"]]


def test_favorable_window_rule():
    res = engine.evaluate(crop="maiz", stage="pre_sowing", region="SV",
                          indicators=_ind(), qa=QA_OK, metadata=META)
    assert res["status"] == "favorable"
    assert res["matched_rules"][0]["rule_id"] == "MAIZ_VENTANA_FAVORABLE_V1"


def test_dry_spell_without_soil_moisture_gives_low_confidence():
    """Falta humedad de suelo: la guía exige degradar la confianza (cap. 6.5)."""
    res = engine.evaluate(crop="maiz", stage="pre_sowing", region="SV",
                          indicators=_ind(rain_fc_7d=8.0, dry_spell=6, days_rain=1),
                          qa=QA_OK, metadata=META, field={"soil_moisture_observed": None})
    assert res["confidence"] == "low"
    assert any("humedad del suelo" in r for r in res["reasons"])


def test_field_observation_raises_confidence():
    without = engine.evaluate(crop="maiz", stage="pre_sowing", region="SV",
                              indicators=_ind(), qa=QA_OK, metadata=META)
    with_obs = engine.evaluate(crop="maiz", stage="pre_sowing", region="SV",
                               indicators=_ind(), qa=QA_OK, metadata=META,
                               field={"soil_moisture_observed": "ok"})
    assert engine.CONFIDENCE_ORDER[with_obs["confidence"]] >= engine.CONFIDENCE_ORDER[without["confidence"]]


def test_single_provider_limits_confidence_explanation():
    res = engine.evaluate(crop="maiz", stage="pre_sowing", region="SV",
                          indicators=_ind(), qa=QA_OK, metadata=META,
                          field={"soil_moisture_observed": "ok"})
    assert any("un solo proveedor" in r for r in res["confidence_explanation"])


def test_every_recommendation_is_traceable():
    """Toda recomendación identifica regla, versión, evidencia y fuente (guía 7.6/12.4)."""
    res = engine.evaluate(crop="maiz", stage="pre_sowing", region="SV",
                          indicators=_ind(max_daily=60.0), qa=QA_OK, metadata=META)
    assert res["status"] == "unfavorable"
    for rule in res["matched_rules"]:
        assert rule["rule_id"] and rule["version"] >= 1 and rule["evidence"]
    assert res["data_basis"]["provider"] == "open-meteo"
    assert res["data_basis"]["retrieved_at"]


def test_no_rule_matched_returns_low_confidence_follow_up():
    res = engine.evaluate(crop="maiz", stage="harvest", region="SV",
                          indicators=_ind(), qa=QA_OK, metadata=META)
    assert res["status"] == "caution"
    assert res["confidence"] == "low"
    assert res["matched_rules"] == []


def test_missing_indicator_does_not_crash_nor_count_as_zero():
    """Dato crítico faltante: la condición no se cumple, nunca se asume 0."""
    ind = _ind()
    ind["rain_forecast"]["accum_7d"]["value_mm"] = None
    res = engine.evaluate(crop="maiz", stage="pre_sowing", region="SV",
                          indicators=ind, qa=QA_OK, metadata=META)
    assert "MAIZ_VENTANA_FAVORABLE_V1" not in [r["rule_id"] for r in res["matched_rules"]]
