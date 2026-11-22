"""Motor agronómico (Fase 5 de la guía).

- Reglas determinísticas configurables en JSON (separadas del código).
- Cada recomendación es trazable: regla, variables, fuentes y versión.
- Confianza ≠ riesgo: se construye de frescura, completitud, horizonte,
  concordancia de proveedores y disponibilidad de datos de campo (cap. 7.3).
- Si falta un dato crítico se degrada a confianza baja; nunca se inventa.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

RULES_DIR = Path(__file__).resolve().parent / "rules"

CONFIDENCE_ORDER = {"low": 0, "medium": 1, "high": 2}
RISK_ORDER = {"low": 0, "moderate": 1, "high": 2, "critical": 3}

STAGE_LABELS = {
    "pre_sowing": "pre-siembra",
    "preparation": "preparación del terreno",
    "sowing": "siembra",
    "emergence": "germinación/emergencia",
    "vegetative": "desarrollo vegetativo",
    "flowering": "floración",
    "grain_filling": "llenado de grano",
    "harvest": "cosecha",
}

CROP_LABELS = {"maiz": "maíz", "frijol": "frijol", "hortaliza": "hortaliza"}


def load_rules(crop: str, stage: str, region: str = "SV") -> list[dict[str, Any]]:
    """Carga reglas aplicables por cultivo/etapa/región desde app/rules/*.json."""
    applicable: list[dict[str, Any]] = []
    for path in sorted(RULES_DIR.glob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        for rule in doc.get("rules", []):
            if rule.get("crop") != crop:
                continue
            if rule.get("region") not in (region, "*"):
                continue
            if stage not in rule.get("stage", []):
                continue
            applicable.append(rule)
    return applicable


def _resolve(context: dict[str, Any], dotted: str) -> Any:
    """Resuelve 'rain_forecast.accum_7d.value_mm' contra el contexto."""
    node: Any = context
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def _check(condition: dict[str, Any], context: dict[str, Any]) -> bool:
    value = _resolve(context, condition["variable"])
    op = condition["operator"]
    expected = condition.get("value")

    if op == "is_null":
        return value is None
    if op == "not_null":
        return value is not None
    if value is None:
        return False  # dato faltante: la condición no se cumple; nunca se asume 0
    if op == ">=":
        return value >= expected
    if op == "<=":
        return value <= expected
    if op == ">":
        return value > expected
    if op == "<":
        return value < expected
    if op == "==":
        return value == expected
    if op == "!=":
        return value != expected
    if op == "in":
        return value in expected
    raise ValueError(f"Operador no soportado: {op}")


def _render(template: str, context: dict[str, Any]) -> str:
    """Sustituye {rutas.punteadas} por valores del contexto (si faltan, queda 'sin dato')."""
    out = template
    for token in _tokens(template):
        value = _resolve(context, token)
        out = out.replace("{" + token + "}", str(value) if value is not None else "sin dato")
    return out


def _tokens(template: str) -> list[str]:
    tokens, buf, depth = [], "", False
    for ch in template:
        if ch == "{":
            depth, buf = True, ""
        elif ch == "}" and depth:
            tokens.append(buf)
            depth = False
        elif depth:
            buf += ch
    return tokens


def _cap_confidence(confidence: str, cap: str | None) -> str:
    if cap is None:
        return confidence
    return confidence if CONFIDENCE_ORDER[confidence] <= CONFIDENCE_ORDER[cap] else cap


def score_confidence(
    *,
    completeness: float,
    retrieved_at: str | None,
    cache_stale: bool,
    forecast_horizon_days: int,
    field_data_available: bool,
    provider_count: int = 1,
) -> tuple[str, list[str]]:
    """Confianza alta/media/baja con explicación (NO es probabilidad calibrada)."""
    reasons: list[str] = []
    score = 0

    # Frescura del dato
    age_min: float | None = None
    if retrieved_at:
        try:
            dt = datetime.fromisoformat(retrieved_at.replace("Z", "+00:00"))
            age_min = (datetime.now(timezone.utc) - dt).total_seconds() / 60
        except ValueError:
            age_min = None
    if cache_stale:
        score -= 1
        reasons.append("se muestra caché porque el proveedor no respondió")
    elif age_min is not None and age_min <= 60:
        score += 2
        reasons.append(f"datos actualizados hace {int(age_min)} min")
    else:
        reasons.append("antigüedad del dato por verificar")

    # Completitud
    if completeness >= 0.95:
        score += 2
    elif completeness >= 0.8:
        score += 1
        reasons.append(f"completitud de datos {completeness:.0%}")
    else:
        score -= 1
        reasons.append(f"completitud de datos baja ({completeness:.0%})")

    # Horizonte del pronóstico
    if forecast_horizon_days <= 7:
        score += 1
    else:
        reasons.append("horizonte de pronóstico largo: mayor incertidumbre")

    # Datos de campo
    if field_data_available:
        score += 2
        reasons.append("con observación de campo de la parcela")
    else:
        score -= 1
        reasons.append("sin observación de humedad del suelo de la parcela")

    # Concordancia de proveedores
    if provider_count >= 2:
        score += 1
        reasons.append("con contraste de segundo proveedor")
    else:
        reasons.append("un solo proveedor meteorológico")

    if score >= 5:
        return "high", reasons
    if score >= 2:
        return "medium", reasons
    return "low", reasons


def evaluate(
    *,
    crop: str,
    stage: str,
    region: str,
    indicators: dict[str, Any],
    qa: dict[str, Any],
    metadata: dict[str, Any],
    field: dict[str, Any] | None = None,
    forecast_horizon_days: int = 7,
) -> dict[str, Any]:
    """Evalúa reglas y produce la salida explicable (formato cap. 7.6)."""
    field = field or {}
    context: dict[str, Any] = {**indicators, "field": field}

    base_confidence, conf_reasons = score_confidence(
        completeness=qa.get("completeness", 0.0),
        retrieved_at=metadata.get("retrieved_at"),
        cache_stale=bool(qa.get("cache", {}).get("stale")),
        forecast_horizon_days=forecast_horizon_days,
        field_data_available=field.get("soil_moisture_observed") is not None,
        provider_count=1,
    )

    matched: list[dict[str, Any]] = []
    for rule in load_rules(crop, stage, region):
        if all(_check(c, context) for c in rule.get("conditions", [])):
            matched.append(rule)

    if not matched:
        return {
            "status": "caution",
            "risk": "unknown",
            "confidence": "low",
            "headline": "No hay una señal clara para esta etapa: seguimiento habitual",
            "reasons": [
                "Ninguna regla de riesgo o de ventana favorable se activó con los datos actuales",
                *conf_reasons,
            ],
            "actions": ["Siga el monitoreo habitual y verifique la humedad del suelo en campo"],
            "matched_rules": [],
            "data_basis": _data_basis(metadata, qa),
            "confidence_explanation": conf_reasons,
        }

    matched.sort(key=lambda r: (-RISK_ORDER.get(r["risk"], 0), -r.get("priority", 0)))
    top = matched[0]
    max_risk = top["risk"]

    # Estado de 3 niveles para el MVP (favorable / precaución / desfavorable)
    if max_risk in ("high", "critical"):
        status = "unfavorable"
    elif any(r["risk"] == "moderate" for r in matched):
        status = "caution"
    else:
        status = "favorable"

    confidence = base_confidence
    for rule in matched:
        confidence = _cap_confidence(confidence, rule.get("confidence_cap"))

    reasons: list[str] = []
    actions: list[str] = []
    for rule in matched:
        reasons.extend(_render(t, context) for t in rule.get("reasons", []))
        actions.extend(_render(t, context) for t in rule.get("actions", []))

    return {
        "status": status,
        "risk": max_risk,
        "confidence": confidence,
        "headline": _render(top["headline"], context),
        "reasons": list(dict.fromkeys(reasons)),          # sin duplicados, orden estable
        "actions": list(dict.fromkeys(actions)),
        "matched_rules": [
            {
                "rule_id": r["rule_id"],
                "version": r["version"],
                "risk": r["risk"],
                "recommendation": r["recommendation"],
                "evidence": r["evidence"],
            }
            for r in matched
        ],
        "data_basis": _data_basis(metadata, qa),
        "confidence_explanation": conf_reasons,
        "labels": {
            "crop": CROP_LABELS.get(crop, crop),
            "stage": STAGE_LABELS.get(stage, stage),
        },
    }


def _data_basis(metadata: dict[str, Any], qa: dict[str, Any]) -> dict[str, Any]:
    return {
        "provider": metadata.get("provider"),
        "retrieved_at": metadata.get("retrieved_at"),
        "units_system": metadata.get("units_system", "metric"),
        "sources": [metadata.get("provider")] if metadata.get("provider") else [],
        "cache": qa.get("cache", {}),
        "note": "Datos de modelo meteorológico; no miden la humedad de la parcela.",
    }
