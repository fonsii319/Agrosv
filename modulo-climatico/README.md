# Módulo Climático — Asistente Agronómico Inteligente (MVP)

Prototipo funcional extremo a extremo para hackathon, construido siguiendo la
**Guía de diseño e implementación del Módulo Climático** (v1.0, 21-nov-2026):
Fases 3–6 (obtención de datos → procesamiento → motor agronómico → frontend).

## Qué hace

1. Registra una parcela (coordenadas, suelo, pendiente).
2. Obtiene **datos reales** de Open-Meteo (pronóstico 7 días + 30 días de pasado reciente; historial ERA5).
3. Normaliza y valida con control de calidad (faltantes, rangos físicos, caché).
4. Calcula indicadores: lluvia acumulada 3/7/30 días, racha seca, días secos por delante, ET₀.
5. Evalúa **reglas agronómicas desacopladas en JSON** (`app/rules/maiz_sv.json`) para maíz.
6. Entrega recomendación de 3 estados (favorable / precaución / desfavorable) con
   **razones, acciones, confianza explicada y trazabilidad** (regla, versión, fuente, hora).

## Reglas de honestidad implementadas (guía)

- Observado / pronosticado / histórico / simulado **siempre separados y etiquetados**.
- El dato meteorológico **no mide la humedad de la parcela**: si falta la observación
  de campo, la confianza se degrada y la recomendación pide verificar el suelo.
- Los días faltantes **nunca** cuentan como lluvia cero: reducen la completitud.
- Escenarios de demo (`/api/v1/demo/scenario/...`) marcados como **DATOS SIMULADOS**.

## Ejecutar

Requisitos: Python 3.11+ y [uv](https://docs.astral.sh/uv/).

```bash
cd modulo-climatico
uv sync
uv run uvicorn app.main:app --reload --port 8000
```

Dashboard: http://localhost:8000 · API docs (Swagger): http://localhost:8000/docs

## Pruebas (Fase 7)

```bash
uv run pytest tests/ -q
```

28 pruebas: acumulados con días faltantes, racha seca, separación observado/pronóstico,
valores nulos e imposibles, caché stale con proveedor caído, reglas por etapa,
confianza degradada sin dato de suelo, contrato del frontend, escenarios simulados.

## Estructura

```
app/
  adapters/open_meteo.py   Adaptador HTTP: timeout, reintentos, caché, respuesta cruda guardada (data/raw/)
  normalizer.py            Normalización + control de calidad
  indicators.py            Acumulados, rachas secas, ET₀
  engine.py                Motor de reglas + confianza explicable
  rules/maiz_sv.json       Reglas de maíz (PROTOTIPO: umbrales por validar con agrónomos)
  storage.py               Parcelas y ciclos de cultivo (JSON; sustituible por BD)
  simulated.py             Escenarios simulados etiquetados (guía cap. 10)
  main.py                  API FastAPI (endpoints cap. 8.6) + dashboard
static/                    Dashboard (HTML/CSS/JS sin build)
tests/                     Pruebas mínimas de la guía cap. 11.3
data/                      Caché, respuestas crudas y almacenamiento local
```

## Endpoints principales

| Ruta | Función |
|---|---|
| `GET /api/v1/parcels/{id}/weather` | Actual + pronóstico normalizado + indicadores |
| `GET /api/v1/parcels/{id}/history?days=30` | Serie histórica ERA5 + agregados |
| `GET /api/v1/parcels/{id}/risks?crop=&stage=` | Evaluación de riesgo |
| `GET /api/v1/parcels/{id}/advice?crop=&stage=&soil_moisture_observed=` | Recomendación agronómica |
| `POST /api/v1/parcels` | Crear parcela |
| `POST /api/v1/crop-cycles` | Registrar ciclo de cultivo |
| `GET /api/v1/demo/scenario/{favorable\|lluvias_insuficientes\|lluvia_intensa\|racha_seca}` | Escenarios simulados |

## Guion de demo ante jueces (guía cap. 12.3)

1. Abrir el dashboard: parcela demo con **datos reales** de San Salvador.
2. Mostrar la tarjeta de decisión y abrir **Trazabilidad** (regla, versión, fuente, hora).
3. Cambiar la etapa del cultivo → cambia la recomendación.
4. Reportar "suelo húmedo" → sube la confianza (se ve en "¿por qué?").
5. Cambiar a un **escenario simulado** (p. ej. Lluvia intensa) → banner rojo de
   datos simulados + recomendación desfavorable.

## Pendiente (post-MVP, guía cap. 12)

Segundo proveedor (NASA POWER) para contraste, climatología de 30 años y anomalías,
ficha de suelo completa, notificaciones, validación con agrónomos y estaciones locales.
