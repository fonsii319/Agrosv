/* Módulo Climático — lógica del dashboard.
   Consume la API del mismo origen (FastAPI) y respeta el orden de la guía cap. 9:
   decisión primero; siempre visible qué dato es observado, pronosticado o simulado. */

"use strict";

const estadoUI = {
  parcelaId: "parcela-demo",
  cultivo: "maiz",
  etapa: "pre_sowing",
  suelo: "",          // "" = sin reporte; "ok" | "seco"
  escenario: "",      // "" = datos reales
};

const $ = (id) => document.getElementById(id);

const DIAS_SEMANA = ["dom", "lun", "mar", "mié", "jue", "vie", "sáb"];
const MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];

const ESTADOS = {
  favorable:   { texto: "Favorable",   nivel: "favorable" },
  caution:     { texto: "Precaución",  nivel: "caution" },
  unfavorable: { texto: "Desfavorable", nivel: "unfavorable" },
};
const CONFIANZA = { high: "alta", medium: "media", low: "baja" };
const RIESGO = { low: "bajo", moderate: "moderado", high: "alto", critical: "crítico", unknown: "sin evaluar" };

function fmtFechaCorta(isoDate) {
  const [y, m, d] = isoDate.split("-").map(Number);
  const fecha = new Date(y, m - 1, d);
  return { dia: DIAS_SEMANA[fecha.getDay()], texto: `${d} ${MESES[m - 1]}` };
}

async function fetchJSON(url) {
  const resp = await fetch(url);
  if (!resp.ok) throw new Error(`Error ${resp.status}: ${await resp.text()}`);
  return resp.json();
}

/* ---------- Carga principal ---------- */
async function cargar() {
  marcarCargando();
  try {
    const params = new URLSearchParams({ crop: estadoUI.cultivo, stage: estadoUI.etapa });
    if (estadoUI.suelo) params.set("soil_moisture_observed", estadoUI.suelo);

    const esSimulado = estadoUI.escenario !== "";
    const url = esSimulado
      ? `/api/v1/demo/scenario/${estadoUI.escenario}?${params}`
      : `/api/v1/parcels/${estadoUI.parcelaId}/advice?${params}`;

    const data = await fetchJSON(url);
    renderDecision(data, esSimulado);
    renderClima(data, esSimulado);
    renderPronostico(data);
    renderIndicadores(data);

    // El historial real solo aplica con datos reales
    if (!esSimulado) cargarHistorial();
    else $("panel-historial").style.display = "none";
  } catch (err) {
    renderError(err);
  }
}

async function cargarHistorial() {
  const panel = $("panel-historial");
  panel.style.display = "";
  try {
    const data = await fetchJSON(`/api/v1/parcels/${estadoUI.parcelaId}/history?days=30`);
    $("hist-total").textContent = `${data.aggregates.precip_total_mm}`;
    const dias = data.history.days;
    const max = Math.max(...dias.map((d) => d.precipitation_mm ?? 0), 1);
    $("sparkline-historial").innerHTML = dias
      .map((d) => {
        const v = d.precipitation_mm ?? 0;
        const h = Math.max(2, Math.round((v / max) * 70));
        return `<i class="${v < 1 ? "sec" : ""}" style="height:${h}px" title="${d.date}: ${v} mm"></i>`;
      })
      .join("");
  } catch {
    $("historial-contenido").innerHTML = `<p class="nota-tecnica">Historial no disponible en este momento.</p>`;
  }
}

/* ---------- Render ---------- */
function renderDecision(data, esSimulado) {
  const rec = data.agronomy.recommendation;
  const estado = ESTADOS[rec.status] ?? ESTADOS.caution;

  $("banner-simulado").hidden = !esSimulado;

  const tarjeta = $("decision");
  tarjeta.dataset.estado = estado.nivel;
  $("estado-texto").textContent = estado.texto;
  $("decision-titular").textContent = rec.headline;

  const badge = $("confianza-badge");
  badge.textContent = CONFIANZA[rec.confidence] ?? rec.confidence;
  badge.dataset.nivel = rec.confidence;

  $("lista-razones").innerHTML = rec.reasons.map((r) => `<li>${escapeHTML(r)}</li>`).join("");
  $("lista-acciones").innerHTML = rec.actions.map((a) => `<li>${escapeHTML(a)}</li>`).join("");

  $("traza-confianza").innerHTML =
    `<strong>Confianza ${CONFIANZA[rec.confidence] ?? rec.confidence}:</strong>` +
    (rec.confidence_explanation ?? []).map((e) => `<span>· ${escapeHTML(e)}</span>`).join("");

  $("tbody-reglas").innerHTML = (rec.matched_rules ?? [])
    .map(
      (r) => `<tr>
        <td><code>${escapeHTML(r.rule_id)}</code><br><small>${escapeHTML(r.recommendation)}</small></td>
        <td>${RIESGO[r.risk] ?? r.risk}</td>
        <td>v${r.version}</td>
        <td><small>${escapeHTML(r.evidence)}</small></td>
      </tr>`
    )
    .join("") || `<tr><td colspan="4">Ninguna regla se activó; seguimiento habitual.</td></tr>`;

  const basis = rec.data_basis ?? {};
  const cache = basis.cache ?? {};
  $("traza-fuente").textContent =
    `Fuente: ${basis.provider ?? "—"} · consultado: ${fmtHora(basis.retrieved_at)} · ` +
    (cache.stale
      ? `caché (proveedor no respondió: ${cache.provider_error ?? "error"})`
      : `respuesta ${cache.hit ? "desde caché válida" : "directa del proveedor"}`) +
    ` · ${basis.note ?? ""}`;
}

function renderClima(data, esSimulado) {
  const cur = data.weather.current ?? {};
  $("c-temp").textContent = cur.temperature_c ?? "—";
  $("c-humedad").textContent = cur.relative_humidity_pct ?? "—";
  $("c-lluvia").textContent = cur.precipitation_mm ?? "—";
  $("c-viento").textContent = cur.wind_speed_kmh ?? "—";

  const meta = data.metadata ?? {};
  $("fuente-datos").textContent = esSimulado ? "fuente: SIMULADO" : `fuente: ${meta.provider ?? "—"}`;
  $("fuente-datos").className = esSimulado ? "badge badge-simulado" : "badge badge-fuente";
  $("hora-actualizacion").textContent = `consultado: ${fmtHora(meta.retrieved_at)}`;

  // Badges de procedencia: nunca mostrar "observado"/"pronóstico" para datos simulados
  const badgeActual = $("badge-actual");
  const badgeProno = $("badge-pronostico");
  if (esSimulado) {
    badgeActual.textContent = "simulado"; badgeActual.className = "badge badge-simulado";
    badgeProno.textContent = "simulado"; badgeProno.className = "badge badge-simulado";
  } else {
    badgeActual.textContent = "observado por modelo"; badgeActual.className = "badge badge-observado";
    badgeProno.textContent = "pronóstico"; badgeProno.className = "badge badge-pronostico";
  }

  if (data.parcel) {
    $("parcela-nombre").textContent = data.parcel.name;
    $("parcela-detalle").textContent =
      `${data.parcel.admin_area ?? ""} · ${data.parcel.latitude}, ${data.parcel.longitude}` +
      ` · suelo: ${data.parcel.soil_type ?? "sin dato"} · pendiente: ${data.parcel.slope_pct ?? "—"}%`;
  } else {
    $("parcela-nombre").textContent = "Parcela Demo — San Salvador (escenario simulado)";
    $("parcela-detalle").textContent = "13.69, -89.19 · datos simulados de demostración";
  }
}

function renderPronostico(data) {
  const dias = (data.weather.daily ?? []).slice(0, 7);
  const maxMm = Math.max(...dias.map((d) => d.precipitation_mm ?? 0), 1);
  const hoy = new Date().toISOString().slice(0, 10);

  $("barras-lluvia").innerHTML = dias
    .map((d) => {
      const mm = d.precipitation_mm ?? 0;
      const h = Math.max(3, Math.round((mm / maxMm) * 120));
      const f = fmtFechaCorta(d.date);
      return `<div class="barra-dia ${d.date === hoy ? "dia-hoy" : ""}">
        <span class="barra-mm">${mm} mm</span>
        <div class="barra" style="height:${h}px" title="${f.texto}: ${mm} mm"></div>
        <span class="barra-prob">${d.precipitation_probability_pct ?? "—"}% prob.</span>
        <div class="barra-temp">
          <span class="temp-max">${d.temperature_max_c ?? "—"}°</span>
          <span class="temp-min">${d.temperature_min_c ?? "—"}°</span>
        </div>
        <span class="barra-fecha">${f.dia}<span>${f.texto}</span></span>
      </div>`;
    })
    .join("");
}

function renderIndicadores(data) {
  const ind = data.indicators ?? {};
  const ro = ind.rain_observed ?? {};
  const rf = ind.rain_forecast ?? {};
  const et0 = ind.et0 ?? {};
  const filas = [
    ["Lluvia observada · 7 días", ro.accum_7d?.value_mm, "mm", `${ro.accum_7d?.days_with_data ?? 0} días con dato`],
    ["Lluvia observada · 30 días", ro.accum_30d?.value_mm, "mm", `${ro.accum_30d?.days_with_data ?? 0} días con dato`],
    ["Racha seca observada", ro.dry_streak?.days, "días", `umbral ${ro.dry_streak?.threshold_mm_per_day ?? 1} mm/día`],
    ["Lluvia pronosticada · 7 días", rf.accum_7d?.value_mm, "mm", `${rf.days_with_rain_expected ?? 0} días con lluvia esperada`],
    ["Días secos por delante", rf.dry_spell_ahead?.days, "días", "desde hoy hasta la próxima lluvia"],
    ["Demanda de agua de la atmósfera (ET₀)", et0.mean_forecast_mm_day, "mm/día", `~${et0.forecast_7d_mm ?? "—"} mm en 7 días`],
  ];
  $("lista-indicadores").innerHTML = filas
    .map(
      ([nombre, valor, unidad, detalle]) => `<div>
        <dt>${nombre}</dt>
        <dd>${valor ?? "sin dato"} <span class="unidad">${valor == null ? "" : unidad}</span><small>${detalle}</small></dd>
      </div>`
    )
    .join("");
  if (ind.params?.dry_day_threshold_mm != null) $("umbral-seco").textContent = ind.params.dry_day_threshold_mm;
}

/* ---------- Utilidades ---------- */
function fmtHora(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d)) return iso;
  return d.toLocaleString("es-SV", { timeZone: "America/El_Salvador", dateStyle: "short", timeStyle: "short" });
}

function escapeHTML(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function marcarCargando() {
  $("decision-titular").textContent = "Actualizando…";
}

function renderError(err) {
  $("decision").dataset.estado = "caution";
  $("estado-texto").textContent = "Sin conexión";
  $("decision-titular").textContent = "No se pudieron obtener los datos meteorológicos";
  $("lista-razones").innerHTML = `<li class="error-box">${escapeHTML(err.message)}. Si hay caché, el backend mostrará la última respuesta válida marcada como tal.</li>`;
  $("lista-acciones").innerHTML = `<li>Verifique su conexión y vuelva a intentar.</li>`;
}

/* ---------- Controles ---------- */
function enlazarControles() {
  $("sel-cultivo").addEventListener("change", (e) => { estadoUI.cultivo = e.target.value; cargar(); });
  $("sel-etapa").addEventListener("change", (e) => { estadoUI.etapa = e.target.value; cargar(); });

  document.querySelectorAll("[data-suelo]").forEach((btn) =>
    btn.addEventListener("click", () => {
      estadoUI.suelo = btn.dataset.suelo;
      document.querySelectorAll("[data-suelo]").forEach((b) => b.setAttribute("aria-pressed", String(b === btn)));
      cargar();
    })
  );

  document.querySelectorAll("[data-esc]").forEach((btn) =>
    btn.addEventListener("click", () => {
      estadoUI.escenario = btn.dataset.esc;
      document.querySelectorAll("[data-esc]").forEach((b) => b.classList.toggle("activo", b === btn));
      cargar();
    })
  );

  $("btn-porque-confianza").addEventListener("click", () => {
    $("detalle-confianza").open = true;
  });
}

enlazarControles();
cargar();
