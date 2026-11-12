/* Pruebas de la página de métricas como informe de gestión
   (frontend/js/metricas.js y metricas.html).
   Ejecutar con: node --test frontend/tests/metricas_ui.test.js */

"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const leer = (archivo) => fs.readFileSync(path.join(__dirname, "..", archivo), "utf8");
const authSource = leer("js/auth.js");
const metricasSource = leer("js/metricas.js");
const css = leer("css/estilos.css");
const html = leer("metricas.html");

function nodo(tag) {
  return {
    tag, id: "", className: "", textContent: "", value: "", hidden: false, disabled: false, scope: "", colSpan: 1,
    open: false, max: "", style: {}, dataset: {}, children: [], listeners: {},
    appendChild(h) { this.children.push(h); return h; },
    replaceChildren(...h) { this.children = h; },
    addEventListener(t, fn) { (this.listeners[t] = this.listeners[t] || []).push(fn); },
    querySelector(sel) {
      if (sel === "canvas") return this.canvas;
      if (sel === "tbody") return this.cuerpo;
      if (sel === ".grafico-lienzo") return this.lienzo;
      if (sel === ".grafico-datos") return this.datos;
      if (sel === ".grafico-datos > div") return this.datos.cuerpo;
      return null;
    },
    querySelectorAll(sel) { return sel === "thead th" ? this.columnas || [] : []; },
  };
}

function texto(n) {
  return (n.textContent || "") + (n.children || []).map(texto).join("");
}

/* Cada fila del <tbody> como lista de textos de sus celdas. */
function filas(tabla) {
  return tabla.cuerpo.children.map((tr) => tr.children.map((c) => c.textContent));
}

const DATOS = {
  desde: "2026-09-20",
  hasta: "2026-10-19",
  tarjetas: { abiertos: 12, nuevo: 7, en_proceso: 5, resueltos_periodo: 30, tiempo_promedio_horas: 28.2,
              creados_periodo: 40, por_correo: 10, por_web: 30 },
  por_estado: [{ nombre: "Nuevo", total: 7 }, { nombre: "En proceso", total: 5 },
               { nombre: "Resuelto", total: 20 }, { nombre: "Cerrado", total: 8 }],
  por_categoria: [{ nombre: "Hardware", total: 10 }, { nombre: "Software", total: 30 }],
  por_persona: [
    { id: 4, nombre: "Luis Mora", rol: "Técnico", activo: false, area: null, abiertos: 0, resueltos: 2 },
    { id: 3, nombre: "Carlos Solís", rol: "Técnico", activo: true, area: "Soporte IT", abiertos: 4, resueltos: 9 },
    { id: 1, nombre: "Ana Admin", rol: "Administrador", activo: true, area: "Soporte IT", abiertos: 1, resueltos: 0 },
  ],
  sin_asignar_abiertos: 2,
  por_dia: [{ fecha: "2026-10-18", total: 3 }, { fecha: "2026-10-19", total: 1 }],
};

const TABLAS = { "tabla-resumen": 4, "tabla-hoy": 3, "tabla-categoria": 3, "tabla-tecnicos": 4 };

function crear({ rol = "Administrador", fetchImpl, conChart = true, variables = null }) {
  const ids = {};
  for (const id of ["form-rango", "desde", "hasta", "aplicar", "imprimir-informe", "estado-carga", "informe",
    "informe-alcance"]) {
    ids[id] = nodo(id === "form-rango" ? "form" : "span");
  }
  const area = nodo("select");
  area.options = [{ textContent: "Todos" }, { textContent: "Sin departamento" }, { textContent: "Soporte IT" }];
  area.selectedIndex = 0;
  ids["m-area"] = area;
  for (const [id, columnas] of Object.entries(TABLAS)) {
    const t = nodo("table");
    t.cuerpo = nodo("tbody");
    t.columnas = Array.from({ length: columnas }, () => nodo("th"));
    ids[id] = t;
  }
  const figuras = ["g-estado", "g-dia"].map((id) => {
    const f = nodo("figure");
    f.id = id;
    f.canvas = nodo("canvas");
    f.lienzo = nodo("div");
    f.datos = nodo("details");
    f.datos.cuerpo = nodo("div");
    ids[id] = f;
    return f;
  });
  const store = new Map([["access_token", "t"], ["user", JSON.stringify({ name: "Marta", role: rol })]]);
  const llamadas = [];
  const charts = [];
  const ventana = { location: { search: "", href: "" }, listeners: {}, impreso: 0 };
  ventana.addEventListener = (t, fn) => { (ventana.listeners[t] = ventana.listeners[t] || []).push(fn); };
  ventana.print = () => { ventana.impreso += 1; };
  const sandbox = {
    document: {
      getElementById: (id) => ids[id] || null,
      createElement: nodo,
      querySelector: () => null,
      querySelectorAll: (sel) => (sel === ".informe-grafico" ? figuras : []),
      addEventListener() {},
    },
    window: ventana,
    localStorage: { getItem: (k) => store.get(k) ?? null, setItem: (k, v) => store.set(k, v), removeItem: (k) => store.delete(k) },
    /* Los departamentos del filtro se piden aparte; acá se anotan solo las
       consultas de métricas. */
    fetch: (url, options = {}) => {
      if (String(url).startsWith("/api/areas")) return Promise.resolve(ok([]));
      llamadas.push(url);
      return fetchImpl(url, options);
    },
    console: { error() {} },
    URLSearchParams, Date, Math, Number, String, Object,
  };
  if (variables) {
    sandbox.document.documentElement = { setAttribute() {}, removeAttribute() {} };
    sandbox.getComputedStyle = () => ({ getPropertyValue: (v) => variables[v] || "" });
  }
  if (conChart) {
    sandbox.Chart = function Chart(canvas, config) {
      this.config = config;
      this.destroyed = false;
      this.destroy = () => { this.destroyed = true; };
      charts.push(this);
    };
    sandbox.Chart.defaults = { font: { family: "Helvetica Neue" } };
  }
  vm.createContext(sandbox);
  vm.runInContext(authSource, sandbox);
  vm.runInContext(metricasSource, sandbox);
  return { sandbox, ids, llamadas, charts, ventana };
}

const ok = (body) => ({ ok: true, status: 200, json: async () => body });
const ANTES = { ...DATOS, tarjetas: { ...DATOS.tarjetas, creados_periodo: 32, resueltos_periodo: 30,
                                      tiempo_promedio_horas: 20, por_correo: 12, por_web: 20 } };

/* El período elegido y el anterior (la segunda llamada de cada carga). */
function conAnterior(m, anterior = ANTES) {
  return async (url) => ok(m.llamadas.indexOf(url) % 2 === 1 ? anterior : DATOS);
}

test("rango por defecto: los últimos 30 días contando hoy", () => {
  const { sandbox } = crear({ fetchImpl: async () => ok(DATOS) });
  assert.deepEqual({ ...sandbox.rangoPorDefecto("2026-10-19") }, { desde: "2026-09-20", hasta: "2026-10-19" });
  assert.deepEqual({ ...sandbox.rangoPorDefecto("2026-03-01") }, { desde: "2026-01-31", hasta: "2026-03-01" });
});

test("al abrir pide el rango por defecto y el anterior; al aplicar, el elegido", async () => {
  const m = crear({ fetchImpl: async () => ok(DATOS) });
  await m.sandbox.iniciarMetricas();
  const hoy = m.sandbox.fechaLocal();
  const { desde } = m.sandbox.rangoPorDefecto(hoy);
  assert.equal(m.llamadas[0], `/api/metricas?desde=${desde}&hasta=${hoy}`);
  assert.equal(m.llamadas[1], `/api/metricas?desde=${m.sandbox.rangoAnterior(desde, hoy).desde}&hasta=${m.sandbox.sumarDias(desde, -1)}`);
  assert.equal(m.ids.desde.value, desde);

  m.ids.desde.value = "2026-10-01";
  m.ids.hasta.value = "2026-10-05";
  m.ids["form-rango"].listeners.submit[0]({ preventDefault() {} });
  await new Promise((r) => setImmediate(r));
  assert.equal(m.llamadas[2], "/api/metricas?desde=2026-10-01&hasta=2026-10-05");
  assert.equal(m.llamadas[3], "/api/metricas?desde=2026-09-26&hasta=2026-09-30");
  // Dos gráficos por carga; los anteriores se destruyen antes de los nuevos.
  assert.equal(m.charts.length, 4);
  assert.ok(m.charts.slice(0, 2).every((c) => c.destroyed));
});

test("encabezado: período en dd/mm/aaaa y el departamento elegido", async () => {
  const m = crear({ fetchImpl: async () => ok(DATOS) });
  m.ids["m-area"].selectedIndex = 2;
  await m.sandbox.iniciarMetricas();
  assert.equal(m.ids["informe-alcance"].textContent, "Período: 20/09/2026 al 19/10/2026 · Departamento: Soporte IT");
});

test("Resumen: este período, el anterior y la variación, sin colores", async () => {
  const m = crear({ fetchImpl: async () => ok(DATOS) });
  m.sandbox.fetch = (url) => {
    if (String(url).startsWith("/api/areas")) return Promise.resolve(ok([]));
    m.llamadas.push(url);
    return conAnterior(m)(url);
  };
  await m.sandbox.iniciarMetricas();
  assert.deepEqual(filas(m.ids["tabla-resumen"]), [
    ["Tickets creados", "40", "32", "+8 (+25 %)"],
    ["Tickets resueltos", "30", "30", "Sin cambio"],
    ["Tiempo promedio de resolución", "1 d 4 h", "20 h", "+8 h (+41 %)"],
    ["Creados por correo", "10 (25 %)", "12 (38 %)", "−2 (−17 %)"],
    ["Creados por la web", "30 (75 %)", "20 (63 %)", "+10 (+50 %)"],
  ]);
  const primera = m.ids["tabla-resumen"].cuerpo.children[0];
  assert.equal(primera.children[0].tag, "th", "el indicador es el encabezado de la fila");
  assert.deepEqual(primera.children.slice(1).map((c) => c.className), ["num", "num", "num"], "números a la derecha");
});

test("Resumen: sin datos del período anterior, «—»", async () => {
  const m = crear({
    fetchImpl: async () => (m.llamadas.length === 2 ? { ok: false, status: 500, json: async () => ({}) } : ok(DATOS)),
  });
  await m.sandbox.iniciarMetricas();
  const resumen = filas(m.ids["tabla-resumen"]);
  assert.deepEqual(resumen.map((f) => f.slice(2)), Array(5).fill(["—", "—"]));
  assert.equal(resumen[0][1], "40", "el informe se ve igual");
});

test("variación: cantidades, horas, sin cambio, desde cero y sin dato", () => {
  const { sandbox } = crear({ fetchImpl: async () => ok(DATOS) });
  assert.equal(sandbox.variacion(28, 25), "+3 (+12 %)");
  assert.equal(sandbox.variacion(20, 25), "−5 (−20 %)");
  assert.equal(sandbox.variacion(5, 5), "Sin cambio");
  assert.equal(sandbox.variacion(3, 0), "+3", "sin porcentaje desde 0");
  assert.equal(sandbox.variacion(null, 4), "—");
  assert.equal(sandbox.variacion(4, null), "—");
  assert.equal(sandbox.variacion(10, 34, { horas: true }), "−1 d (−71 %)");
  assert.doesNotMatch(metricasSource, /[▲▼]|bueno|malo/, "sin flechas ni verde y rojo");
});

test("Situación de hoy: Nuevo, En proceso y Total abiertos con su %", async () => {
  const m = crear({ fetchImpl: async () => ok(DATOS) });
  await m.sandbox.iniciarMetricas();
  assert.deepEqual(filas(m.ids["tabla-hoy"]), [
    ["Nuevo", "7", "58 %"], ["En proceso", "5", "42 %"], ["Total abiertos", "12", "100 %"],
  ]);
  assert.equal(m.ids["tabla-hoy"].cuerpo.children[2].className, "fila-total");
  const vacio = crear({ fetchImpl: async () => ok({ ...DATOS, tarjetas: { ...DATOS.tarjetas, abiertos: 0, nuevo: 0, en_proceso: 0 } }) });
  await vacio.sandbox.iniciarMetricas();
  assert.deepEqual(filas(vacio.ids["tabla-hoy"]).map((f) => f[2]), ["—", "—", "—"]);
});

test("Tickets por categoría: cantidad, % y fila Total", async () => {
  const m = crear({ fetchImpl: async () => ok(DATOS) });
  await m.sandbox.iniciarMetricas();
  assert.deepEqual(filas(m.ids["tabla-categoria"]), [
    ["Hardware", "10", "25 %"], ["Software", "30", "75 %"], ["Total", "40", "100 %"],
  ]);
  assert.equal(m.ids["tabla-categoria"].cuerpo.children[2].className, "fila-total");
});

test("Por técnico: ordenada por abiertos, con departamento, rol si no es Técnico y «Sin asignar» al final", async () => {
  const m = crear({ fetchImpl: async () => ok(DATOS) });
  await m.sandbox.iniciarMetricas();
  assert.deepEqual(filas(m.ids["tabla-tecnicos"]), [
    ["Carlos Solís", "Soporte IT", "4", "9"],
    ["Ana Admin (Administrador)", "Soporte IT", "1", "0"],
    ["Luis Mora · desactivado", "—", "0", "2"],
    ["Sin asignar", "—", "2", "—"],
  ]);
  const fila = m.ids["tabla-tecnicos"].cuerpo.children[0];
  assert.deepEqual(fila.children.map((c) => c.className), ["", "", "num", "num"], "departamento como texto");

  const nadie = crear({ fetchImpl: async () => ok({ ...DATOS, por_persona: [], sin_asignar_abiertos: 0 }) });
  await nadie.sandbox.iniciarMetricas();
  const vacia = nadie.ids["tabla-tecnicos"].cuerpo.children[0].children[0];
  assert.equal(vacia.textContent, "No hay tickets asignados en el período.");
  assert.equal(vacia.colSpan, 4);
});

test("gráficos: barras clásicas en el azul de la app, ejes, líneas de fondo y el número arriba", async () => {
  const m = crear({
    fetchImpl: async () => ok(DATOS),
    variables: { "--color-primario": "#1746e0", "--color-tenue": "#5d6880", "--color-borde": "#dde3ee",
                 "--color-borde-fuerte": "#c4cddd" },
  });
  await m.sandbox.iniciarMetricas();
  const [estado, dia] = m.charts.map((c) => c.config);
  assert.equal(estado.type, "bar");
  assert.equal(dia.type, "bar", "por día también en barras");
  assert.deepEqual([...estado.data.labels], ["Nuevo", "En proceso", "Resuelto", "Cerrado"]);
  assert.deepEqual([...estado.data.datasets[0].data], [7, 5, 20, 8]);
  assert.deepEqual([...dia.data.labels], ["18/10", "19/10"]);
  for (const c of [estado, dia]) {
    assert.equal(c.data.datasets.length, 1);
    assert.equal(c.data.datasets[0].backgroundColor, "#1746e0", "un solo color");
    assert.equal(c.data.datasets[0].borderRadius, undefined, "barras rectas");
    assert.equal(c.options.plugins.legend.display, false);
    assert.equal(c.options.plugins.valoresEnBarras.activo, true, "número arriba de cada barra");
    assert.equal(c.options.scales.y.grid.color, "#dde3ee", "líneas de fondo suaves");
    assert.equal(c.options.scales.x.border.display, true, "con ejes");
    assert.equal(c.options.scales.y.border.display, true);
  }
  assert.equal(m.sandbox.Chart.defaults.font.family, '"Inter", system-ui, "Segoe UI", Roboto, Arial, sans-serif');
  assert.match(texto(m.ids["g-dia"].datos.cuerpo), /19\/10\/20261/);
});

test("al imprimir los gráficos pasan a grises y después vuelven", async () => {
  const m = crear({ fetchImpl: async () => ok(DATOS) });
  await m.sandbox.iniciarMetricas();
  m.ventana.listeners.beforeprint.forEach((fn) => fn());
  assert.equal(m.charts.at(-1).config.data.datasets[0].backgroundColor, "#555555");
  m.ventana.listeners.afterprint.forEach((fn) => fn());
  assert.equal(m.charts.at(-1).config.data.datasets[0].backgroundColor, "#1746e0");
  m.ids["imprimir-informe"].listeners.click[0]();
  assert.equal(m.ventana.impreso, 1, "«Imprimir» abre la impresión");
});

test("sin Chart.js (sin internet) se muestran las tablas de los gráficos", async () => {
  const m = crear({ fetchImpl: async () => ok(DATOS), conChart: false });
  await m.sandbox.iniciarMetricas();
  for (const id of ["g-estado", "g-dia"]) {
    assert.equal(m.ids[id].lienzo.hidden, true);
    assert.equal(m.ids[id].datos.open, true);
  }
  assert.match(m.ids["estado-carga"].textContent, /Los datos se muestran en tablas/);
  assert.equal(filas(m.ids["tabla-resumen"])[0][1], "40", "las tablas del informe se ven igual");
});

test("formatearHoras", () => {
  const { sandbox } = crear({ fetchImpl: async () => ok(DATOS) });
  assert.equal(sandbox.formatearHoras(null), "—");
  assert.equal(sandbox.formatearHoras(0.4), "menos de 1 h");
  assert.equal(sandbox.formatearHoras(5.2), "5 h");
  assert.equal(sandbox.formatearHoras(48), "2 d");
  assert.equal(sandbox.formatearHoras(50.6), "2 d 3 h");
});

test("errores: rango inválido y rol sin permiso", async () => {
  for (const [status, detail, esperado] of [
    [422, "La fecha «desde» no puede ser posterior a «hasta».", /posterior/],
    [403, "No autorizado", /Su rol no tiene permiso para ver las métricas/],
  ]) {
    const m = crear({ fetchImpl: async () => ({ ok: false, status, json: async () => ({ detail }) }) });
    await m.sandbox.iniciarMetricas();
    assert.match(m.ids["estado-carga"].textContent, esperado);
    assert.equal(m.ids["estado-carga"].className, "estado error");
    assert.equal(m.ids.aplicar.disabled, false);
  }
});

test("el permiso «metricas» es solo para el Administrador", () => {
  for (const [rol, puede] of [["Administrador", true], ["Técnico", false], ["Solicitante", false]]) {
    const { sandbox } = crear({ rol, fetchImpl: async () => ok(DATOS) });
    assert.equal(sandbox.puede("metricas"), puede, rol);
  }
});

test("período anterior: misma duración, justo antes del rango", () => {
  const { sandbox } = crear({ fetchImpl: async () => ok(DATOS) });
  assert.deepEqual({ ...sandbox.rangoAnterior("2026-10-01", "2026-10-05") }, { desde: "2026-09-26", hasta: "2026-09-30" });
  assert.deepEqual({ ...sandbox.rangoAnterior("2026-03-01", "2026-03-01") }, { desde: "2026-02-28", hasta: "2026-02-28" });
});

// --- HTML y CSS ---------------------------------------------------------------

test("metricas.html: filtros con «Imprimir», encabezado y las secciones en orden, sin tarjetas", () => {
  assert.match(html, /<button type="submit" id="aplicar">Aplicar<\/button>\s*<!--[^>]*-->\s*<button type="button" id="imprimir-informe" class="secundario">Imprimir<\/button>/);
  assert.match(html, /<h2 id="informe-titulo">Indicadores de la mesa de soporte<\/h2>\s*<p id="informe-alcance" class="informe-alcance">/);
  const titulos = [...html.matchAll(/class="informe-seccion-titulo">([^<]+)</g)].map((r) => r[1]);
  assert.deepEqual(titulos, ["Resumen", "Situación de hoy", "Distribución", "Por día", "Por técnico"]);
  assert.match(html, /<th scope="col">Indicador<\/th><th scope="col" class="num">Este período<\/th><th scope="col" class="num">Período anterior<\/th><th scope="col" class="num">Variación<\/th>/);
  assert.match(html, /<th scope="col">Estado<\/th><th scope="col" class="num">Tickets<\/th><th scope="col" class="num">% del total abierto<\/th>/);
  assert.match(html, /<p class="informe-nota">Abiertos = Nuevo \+ En proceso, al momento de consultar\.<\/p>/);
  assert.match(html, /<th scope="col">Técnico<\/th><th scope="col">Departamento<\/th><th scope="col" class="num">Abiertos hoy<\/th><th scope="col" class="num">Resueltos en el período<\/th>/);
  const distribucion = html.slice(html.indexOf('id="s-distribucion"'), html.indexOf('id="s-dia"'));
  assert.ok(distribucion.indexOf('id="g-estado"') < distribucion.indexOf('id="tabla-categoria"'), "gráfico a la izquierda, tabla a la derecha");
  assert.doesNotMatch(html, /metricas-tarjetas|tarjeta-resumen|tarjeta-numero|g-persona|g-categoria|<svg[^>]*>(?![\s\S]*<\/nav>)/);
  assert.doesNotMatch(html, /\sstyle="|\son[a-z]+="/, "sin código inline (CSP)");
});

function bloqueInforme() {
  const inicio = css.indexOf("/* ===== Métricas: informe de gestión");
  assert.ok(inicio > 0);
  return css.slice(inicio, css.indexOf("/* ===== Avatares con iniciales", inicio));
}

test("CSS: hoja centrada con borde fino, línea oscura, títulos grises en mayúsculas y números a la derecha", () => {
  const b = bloqueInforme();
  assert.match(b, /\.informe \{[^}]*max-width: 980px;[^}]*margin: 0 auto[^}]*border: 1px solid var\(--color-borde-fuerte\);[^}]*background: var\(--color-superficie\);/);
  assert.match(b, /\.informe-encabezado \{[^}]*justify-content: space-between;[^}]*border-bottom: 2px solid var\(--color-titulo\);/);
  assert.match(b, /\.informe-seccion-titulo \{[^}]*text-transform: uppercase;[^}]*color: var\(--color-tenue\);/);
  assert.match(b, /\.tabla-informe \.num \{\s*text-align: right;/);
  assert.match(b, /\.tabla-informe \.fila-total th,\s*\.tabla-informe \.fila-total td \{[^}]*font-weight: 600;/);
  assert.doesNotMatch(b, /box-shadow|border-radius: (?!2px)|etiqueta-verde|etiqueta-rojo|color-exito|color-error/, "sin sombras, pastillas ni verde y rojo");
});

test("CSS: en el celular una sección debajo de la otra y las tablas se desplazan en su caja", () => {
  const b = bloqueInforme();
  assert.match(b, /\.informe-tabla \{\s*max-width: 100%;\s*overflow-x: auto;/);
  assert.match(b, /@media \(max-width: 900px\) \{\s*\.informe-columnas \{\s*grid-template-columns: minmax\(0, 1fr\);/);
  assert.match(b, /@media \(max-width: 600px\) \{\s*\.informe \{\s*padding: 1\.1rem 1rem 1\.3rem;/);
});

test("CSS: al imprimir solo el informe, en blanco y negro, sin menú, filtros ni chat", () => {
  const b = bloqueInforme();
  const p = b.slice(b.indexOf("@media print {"));
  for (const sel of ["body:has(.informe) .barra-lateral", "body:has(.informe) .cabecera", "body:has(.informe) .chat-asistente",
    ".metricas-rango", ".informe .grafico-datos"]) {
    assert.ok(p.includes(sel), sel);
  }
  assert.match(p, /display: none !important;/);
  assert.match(p, /\.informe \*,[\s\S]*color: #000 !important;/);
  assert.match(p, /\.informe \{[^}]*border: 0;[^}]*background: #fff !important;/);
});

test("ya no quedan los estilos de tarjetas con cambio verde/rojo ni las series de colores", () => {
  assert.doesNotMatch(css, /metrica-cambio|--color-serie-|metricas-graficos/);
  // Departamentos sigue usando sus tarjetas.
  assert.match(css, /\.metricas-tarjetas \{/);
  assert.match(css, /\.tarjeta-resumen\.metrica \{/);
});
