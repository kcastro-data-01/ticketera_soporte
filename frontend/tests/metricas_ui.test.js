/* Pruebas de la página de métricas (frontend/js/metricas.js).
   Ejecutar con: node --test frontend/tests/metricas_ui.test.js */

"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const authSource = fs.readFileSync(path.join(__dirname, "..", "js", "auth.js"), "utf8");
const metricasSource = fs.readFileSync(path.join(__dirname, "..", "js", "metricas.js"), "utf8");

function nodo(tag) {
  return {
    tag, id: "", className: "", textContent: "", value: "", hidden: false, disabled: false,
    open: false, max: "", style: {}, dataset: {}, children: [], listeners: {},
    appendChild(h) { this.children.push(h); return h; },
    replaceChildren(...h) { this.children = h; },
    addEventListener(t, fn) { (this.listeners[t] = this.listeners[t] || []).push(fn); },
    querySelector(sel) {
      if (sel === "canvas") return this.canvas;
      if (sel === ".grafico-lienzo") return this.lienzo;
      if (sel === ".grafico-datos") return this.datos;
      if (sel === ".grafico-datos > div") return this.datos.cuerpo;
      return null;
    },
  };
}

function texto(n) {
  return (n.textContent || "") + (n.children || []).map(texto).join("");
}

const DATOS = {
  desde: "2026-09-20",
  hasta: "2026-10-19",
  tarjetas: { abiertos: 12, en_proceso: 5, resueltos_periodo: 30, tiempo_promedio_horas: 28.2,
              creados_periodo: 40, por_correo: 10, por_web: 30 },
  por_estado: [{ nombre: "Nuevo", total: 7 }, { nombre: "En proceso", total: 5 }],
  por_categoria: [{ nombre: "Hardware", total: 10 }],
  por_persona: [
    { id: 3, nombre: "Carlos Solís", rol: "Técnico", activo: true, abiertos: 4, resueltos: 9 },
    { id: 4, nombre: "Luis Mora", rol: "Técnico", activo: false, abiertos: 0, resueltos: 2 },
  ],
  sin_asignar_abiertos: 2,
  por_dia: [{ fecha: "2026-10-18", total: 3 }, { fecha: "2026-10-19", total: 1 }],
};

function crear({ rol = "Supervisor", fetchImpl, conChart = true }) {
  const ids = {};
  for (const id of ["form-rango", "desde", "hasta", "aplicar", "estado-carga", "m-abiertos", "m-en-proceso",
    "m-resueltos", "m-promedio", "m-origen", "m-origen-nota",
    "c-abiertos", "c-en-proceso", "c-resueltos", "c-promedio", "c-origen"]) {
    ids[id] = nodo(id === "form-rango" ? "form" : "span");
  }
  const figuras = ["g-estado", "g-categoria", "g-persona", "g-dia"].map((id) => {
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
  const sandbox = {
    document: {
      getElementById: (id) => ids[id] || null,
      createElement: nodo,
      querySelector: (sel) => (sel === "#g-persona .grafico-lienzo" ? ids["g-persona"].lienzo : null),
      querySelectorAll: (sel) => (sel === ".grafico" ? figuras : []),
      addEventListener() {},
    },
    window: { location: { search: "", href: "" } },
    localStorage: { getItem: (k) => store.get(k) ?? null, setItem: (k, v) => store.set(k, v), removeItem: (k) => store.delete(k) },
    fetch: (url, options = {}) => { llamadas.push(url); return fetchImpl(url, options); },
    console: { error() {} },
    URLSearchParams, Date, Math, Number, String, Object,
  };
  if (conChart) {
    sandbox.Chart = function Chart(canvas, config) {
      this.config = config;
      this.destroyed = false;
      this.destroy = () => { this.destroyed = true; };
      charts.push(this);
    };
  }
  vm.createContext(sandbox);
  vm.runInContext(authSource, sandbox);
  vm.runInContext(metricasSource, sandbox);
  return { sandbox, ids, llamadas, charts };
}

const ok = (body) => ({ ok: true, status: 200, json: async () => body });

test("rango por defecto: los últimos 30 días contando hoy", () => {
  const { sandbox } = crear({ fetchImpl: async () => ok(DATOS) });
  assert.deepEqual({ ...sandbox.rangoPorDefecto("2026-10-19") }, { desde: "2026-09-20", hasta: "2026-10-19" });
  assert.deepEqual({ ...sandbox.rangoPorDefecto("2026-03-01") }, { desde: "2026-01-31", hasta: "2026-03-01" });
});

test("al abrir pide el rango por defecto y al aplicar el elegido", async () => {
  const m = crear({ fetchImpl: async () => ok(DATOS) });
  await m.sandbox.iniciarMetricas();
  const hoy = m.sandbox.fechaLocal();
  const { desde } = m.sandbox.rangoPorDefecto(hoy);
  assert.equal(m.llamadas[0], `/api/metricas?desde=${desde}&hasta=${hoy}`);
  assert.equal(m.ids.desde.value, desde);

  m.ids.desde.value = "2026-10-01";
  m.ids.hasta.value = "2026-10-05";
  m.ids["form-rango"].listeners.submit[0]({ preventDefault() {} });
  await new Promise((r) => setImmediate(r));
  // Cada carga pide también el período anterior de la misma duración.
  assert.equal(m.llamadas[1], `/api/metricas?desde=${m.sandbox.rangoAnterior(desde, hoy).desde}&hasta=${m.sandbox.sumarDias(desde, -1)}`);
  assert.equal(m.llamadas[2], "/api/metricas?desde=2026-10-01&hasta=2026-10-05");
  assert.equal(m.llamadas[3], "/api/metricas?desde=2026-09-26&hasta=2026-09-30");
  // Los gráficos anteriores se destruyen antes de crear los nuevos.
  assert.equal(m.charts.length, 8);
  assert.ok(m.charts.slice(0, 4).every((c) => c.destroyed));
});

test("tarjetas: números, duración legible y correo frente a web", async () => {
  const m = crear({ fetchImpl: async () => ok(DATOS) });
  await m.sandbox.iniciarMetricas();
  assert.equal(m.ids["m-abiertos"].textContent, "12");
  assert.equal(m.ids["m-en-proceso"].textContent, "5");
  assert.equal(m.ids["m-resueltos"].textContent, "30");
  assert.equal(m.ids["m-promedio"].textContent, "1 d 4 h");
  assert.equal(m.ids["m-origen"].textContent, "10 / 30");
  assert.equal(m.ids["m-origen-nota"].textContent, "40 creados en el período · 25% por correo");
});

test("formatearHoras", () => {
  const { sandbox } = crear({ fetchImpl: async () => ok(DATOS) });
  assert.equal(sandbox.formatearHoras(null), "—");
  assert.equal(sandbox.formatearHoras(0.4), "menos de 1 h");
  assert.equal(sandbox.formatearHoras(5.2), "5 h");
  assert.equal(sandbox.formatearHoras(48), "2 d");
  assert.equal(sandbox.formatearHoras(50.6), "2 d 3 h");
});

test("gráfico por persona: nombre con rol, desactivados marcados y fila «Sin asignar»", async () => {
  const m = crear({ fetchImpl: async () => ok(DATOS) });
  await m.sandbox.iniciarMetricas();
  const persona = m.charts[2].config;
  assert.deepEqual([...persona.data.labels], ["Carlos Solís (Técnico)", "Luis Mora (Técnico) · desactivado", "Sin asignar"]);
  assert.deepEqual([...persona.data.datasets[0].data], [4, 0, 2]);
  assert.deepEqual([...persona.data.datasets[1].data], [9, 2, 0]);
  assert.equal(persona.options.indexAxis, "y");
  assert.equal(persona.options.plugins.legend.display, true); // dos series: con leyenda
  assert.equal(m.charts[0].config.options.plugins.legend.display, false); // una serie: sin leyenda
  assert.match(texto(m.ids["g-persona"].datos.cuerpo), /Carlos Solís \(Técnico\)49/);
});

test("sin Chart.js (sin internet) se muestran las tablas abiertas", async () => {
  const m = crear({ fetchImpl: async () => ok(DATOS), conChart: false });
  await m.sandbox.iniciarMetricas();
  for (const id of ["g-estado", "g-categoria", "g-persona", "g-dia"]) {
    assert.equal(m.ids[id].lienzo.hidden, true);
    assert.equal(m.ids[id].datos.open, true);
  }
  assert.match(texto(m.ids["g-dia"].datos.cuerpo), /19\/101/);
  assert.match(m.ids["estado-carga"].textContent, /Los datos se muestran en tablas/);
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

test("el permiso «metricas» es solo para Supervisor y Administrador", () => {
  for (const [rol, puede] of [["Administrador", true], ["Supervisor", true], ["Técnico", false], ["Solicitante", false]]) {
    const { sandbox } = crear({ rol, fetchImpl: async () => ok(DATOS) });
    assert.equal(sandbox.puede("metricas"), puede, rol);
  }
});


// --- Comparación con el período anterior ------------------------------------

test("período anterior: misma duración, justo antes del rango", () => {
  const { sandbox } = crear({ fetchImpl: async () => ok(DATOS) });
  assert.deepEqual({ ...sandbox.rangoAnterior("2026-10-01", "2026-10-05") }, { desde: "2026-09-26", hasta: "2026-09-30" });
  assert.deepEqual({ ...sandbox.rangoAnterior("2026-03-01", "2026-03-01") }, { desde: "2026-02-28", hasta: "2026-02-28" });
  assert.deepEqual({ ...sandbox.rangoAnterior("2026-09-20", "2026-10-19") }, { desde: "2026-08-21", hasta: "2026-09-19" });
});

test("texto y color del cambio según si es bueno o malo", () => {
  const { sandbox } = crear({ fetchImpl: async () => ok(DATOS) });
  const c = (...a) => ({ ...sandbox.cambioVsAnterior(...a) });
  assert.deepEqual(c(28, 25, "subir"), { texto: "▲ 12 % vs. período anterior", tono: "bueno" });
  assert.deepEqual(c(20, 25, "subir"), { texto: "▼ 20 % vs. período anterior", tono: "malo" });
  assert.deepEqual(c(10, 20, "bajar"), { texto: "▼ 50 % vs. período anterior", tono: "bueno" });
  assert.deepEqual(c(30, 20, "bajar"), { texto: "▲ 50 % vs. período anterior", tono: "malo" });
  assert.deepEqual(c(48, 40, "neutro", " creados"), { texto: "▲ 20 % creados vs. período anterior", tono: "neutro" });
  assert.deepEqual(c(5, 5, "subir"), { texto: "= igual vs. período anterior", tono: "neutro" });
  assert.deepEqual(c(3, 0, "subir"), { texto: "▲ desde 0 en el período anterior", tono: "bueno" });
  assert.deepEqual(c(null, 4, "bajar"), { texto: "Sin datos del período anterior", tono: "neutro" });
});

test("las tarjetas muestran la comparación con la segunda consulta", async () => {
  const ANTES = { ...DATOS, tarjetas: { ...DATOS.tarjetas, resueltos_periodo: 25, tiempo_promedio_horas: 20, creados_periodo: 40 } };
  const m = crear({ fetchImpl: async (url) => ok(url === m.llamadas[0] ? DATOS : ANTES) });
  await m.sandbox.iniciarMetricas();
  assert.equal(m.ids["c-resueltos"].textContent, "▲ 20 % vs. período anterior");
  assert.equal(m.ids["c-resueltos"].className, "metrica-cambio bueno");
  assert.equal(m.ids["c-promedio"].textContent, "▲ 41 % vs. período anterior");
  assert.equal(m.ids["c-promedio"].className, "metrica-cambio malo", "tardar más es malo");
  assert.equal(m.ids["c-origen"].textContent, "= igual vs. período anterior");
  assert.equal(m.ids["c-abiertos"].hidden, false, "aclara que es el valor de hoy");
});

test("si falla la consulta del período anterior, las métricas se ven igual", async () => {
  const m = crear({
    fetchImpl: async () => (m.llamadas.length === 2 ? { ok: false, status: 500, json: async () => ({}) } : ok(DATOS)),
  });
  await m.sandbox.iniciarMetricas();
  assert.equal(m.ids["m-resueltos"].textContent, "30");
  assert.equal(m.ids["c-resueltos"].hidden, true);
  assert.equal(m.ids["c-abiertos"].hidden, true);
});
