/* Filtros «Asignado a» y «Fecha de creación» (un solo día) del listado
   (app.js + index.html):
   cada uno solo, combinados con los que ya existen, «Limpiar filtros», la
   vista Tablero y el Solicitante sin «Asignado a».
   Ejecutar con: node --test frontend/tests/filtros_asignado_fechas.test.js */

"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const leer = (archivo) => fs.readFileSync(path.join(__dirname, "..", archivo), "utf8");
const indexHtml = leer("index.html");

const CAMPOS = ["search", "category", "priority", "state", "assigned", "fecha"];
const INICIAL = {};
const IDS = [
  "form-filtros", ...CAMPOS, "limpiar", "estado-carga", "lista-tickets", "total-tickets", "tabla-tickets", "tablero",
  "vista-todos", "vista-mios", "ver-tabla", "ver-tablero",
];
const USUARIOS = [
  { id: 4, name: "Luis Mora", is_active: true },
  { id: 2, name: "Ana Solís", is_active: true },
];
const TICKETS = [
  { id: 7, title: "VPN caída", category: "Red", priority: "Alta", state: "En proceso", assigned_to_id: 4, created_at: "2026-10-20T15:00:00Z" },
  { id: 8, title: "Monitor roto", category: "Hardware", priority: "Media", state: "Nuevo", assigned_to_id: null, created_at: "2026-10-21T15:00:00Z" },
];

function nodo(tag) {
  const clases = new Set();
  return {
    tag, value: INICIAL[tag] || "", textContent: "", children: [], dataset: {}, atributos: {},
    listeners: {}, hidden: false,
    classList: {
      add: (c) => clases.add(c), remove: (c) => clases.delete(c), contains: (c) => clases.has(c),
      toggle: (c, si) => ((si ?? !clases.has(c)) ? clases.add(c) : clases.delete(c)),
    },
    setAttribute(k, v) { this.atributos[k] = String(v); },
    removeAttribute(k) { delete this.atributos[k]; },
    addEventListener(t, fn) { (this.listeners[t] = this.listeners[t] || []).push(fn); },
    appendChild(h) { this.children.push(h); return h; },
    append(...hs) { hs.forEach((h) => this.appendChild(h)); },
    replaceChildren(...hs) { this.children = hs; },
    /* Como el formulario real: cada campo vuelve a su primera opción. */
    reset() { CAMPOS.forEach((id) => { this.campos.get(id).value = INICIAL[id] || ""; }); },
  };
}

async function montar(rol = "Técnico", { vista = "tabla" } = {}) {
  const nodos = new Map(IDS.map((id) => [id, nodo(id)]));
  nodos.get("form-filtros").campos = nodos;
  const pedidos = [];
  const store = new Map([["vista_listado", vista]]);
  const equipo = [nodos.get("assigned")];
  const sandbox = {
    document: {
      title: "",
      getElementById: (id) => nodos.get(id) || null,
      querySelector: () => null,
      querySelectorAll: (sel) => (sel === '[data-vista="equipo"]' ? equipo : []),
      createElement: nodo,
      addEventListener() {},
    },
    window: { location: { href: "", search: "" } },
    localStorage: {
      getItem: (k) => (k === "user" ? JSON.stringify({ id: 9, name: "José", role: rol })
        : k === "access_token" ? "t" : store.get(k) ?? null),
      setItem: (k, v) => store.set(k, v), removeItem: (k) => store.delete(k),
    },
    fetch: async (url) => {
      pedidos.push(url);
      const body = url.startsWith("/api/users") ? USUARIOS : TICKETS;
      return { ok: true, status: 200, headers: { get: () => String(TICKETS.length) }, json: async () => body };
    },
    console: { error() {}, log() {} },
    URLSearchParams, Map, Number, Object, String, Boolean, Date,
  };
  vm.createContext(sandbox);
  vm.runInContext(leer("js/auth.js"), sandbox);
  vm.runInContext(leer("js/app.js"), sandbox);
  sandbox.init();
  await esperar();
  return { nodos, pedidos, sandbox, ultimo: () => new URL(pedidos[pedidos.length - 1], "http://x").searchParams };
}

const esperar = async () => { for (let i = 0; i < 10; i += 1) await new Promise((r) => setImmediate(r)); };
const enviar = async (n) => { n.listeners.submit.forEach((fn) => fn({ preventDefault() {} })); await esperar(); };
const clic = async (n) => { n.listeners.click.forEach((fn) => fn()); await esperar(); };

async function filtrar(h, valores) {
  Object.entries(valores).forEach(([id, valor]) => { h.nodos.get(id).value = valor; });
  await enviar(h.nodos.get("form-filtros"));
  return h.ultimo();
}

/* ---------------- HTML ---------------- */

test("index.html: «Fecha de creación» es un solo campo, al lado de «Asignado a» y antes de los botones", () => {
  const form = indexHtml.slice(indexHtml.indexOf('id="form-filtros"'), indexHtml.indexOf("</form>"));
  assert.match(form, /<label class="campo" data-vista="equipo">\s*<span>Asignado a<\/span>\s*<select id="assigned" name="assigned">\s*<option value="">Todos<\/option>\s*<option value="sin">Sin asignar<\/option>/);
  assert.match(form, /<\/select>\s*<\/label>\s*(<!--[^>]*-->\s*)?<label class="campo">\s*<span>Fecha de creación<\/span>\s*<input type="date" id="fecha" name="fecha">\s*<\/label>\s*<div class="acciones">\s*<button type="submit" id="buscar">Buscar<\/button>\s*<button type="button" id="limpiar"/);
  /* Mismo campo que los demás: en celular pasa a otra fila con la regla de .campo. */
  assert.equal((form.match(/type="date"/g) || []).length, 1);
});

test("index.html y app.js: sin «Desde», «Hasta» ni selector «Fecha de»", () => {
  assert.doesNotMatch(indexHtml, /id="desde"|id="hasta"|<span>Desde<|<span>Hasta<|fecha-campo|campo-fechas/);
  assert.doesNotMatch(leer("js/app.js"), /fecha-campo|params\.set\("fecha_campo"|getElementById\("(desde|hasta)"\)/);
  assert.doesNotMatch(leer("css/estilos.css"), /campo-fechas|campo-fecha\b/, "sin estilos propios: usa los de .campo");
});

/* ---------------- «Asignado a» ---------------- */

test("«Asignado a»: Todos, Sin asignar y los usuarios activos por nombre", async () => {
  const h = await montar();
  const opciones = h.nodos.get("assigned").children.map((o) => [o.value, o.textContent]);
  assert.deepEqual(opciones, [["2", "Ana Solís"], ["4", "Luis Mora"]], "se agregan después de las dos fijas del HTML");
});

test("«Asignado a» solo: un usuario → assigned_to; «Sin asignar» → sin_asignar", async () => {
  const h = await montar();
  let q = await filtrar(h, { assigned: "4" });
  assert.equal(q.get("assigned_to"), "4");
  assert.equal(q.has("sin_asignar"), false);

  q = await filtrar(h, { assigned: "sin" });
  assert.equal(q.get("sin_asignar"), "true");
  assert.equal(q.has("assigned_to"), false);

  q = await filtrar(h, { assigned: "" });
  assert.equal(q.has("assigned_to") || q.has("sin_asignar"), false, "«Todos» no filtra");
});

test("Solicitante: no ve «Asignado a» ni lo envía, y no se cargan opciones", async () => {
  const h = await montar("Solicitante");
  assert.equal(h.nodos.get("assigned").hidden, true);
  assert.equal(h.nodos.get("assigned").children.length, 0);
  const q = await filtrar(h, { assigned: "4" });
  assert.equal(q.has("assigned_to"), false);
});

/* ---------------- Fechas ---------------- */

test("Fecha de creación: manda desde = hasta = ese día y nada de fecha_campo", async () => {
  const h = await montar();
  const q = await filtrar(h, { fecha: "2026-10-15" });
  assert.deepEqual([q.get("desde"), q.get("hasta"), q.has("fecha_campo")], ["2026-10-15", "2026-10-15", false]);
});

test("Fecha de creación vacía: sin filtro de fecha", async () => {
  const h = await montar();
  await filtrar(h, { fecha: "2026-10-15" });
  const q = await filtrar(h, { fecha: "" });
  assert.equal(q.has("desde") || q.has("hasta") || q.has("fecha_campo"), false);
});

test("Fecha de creación: el primer y el último día del mes se mandan tal cual (sin correr por zona horaria)", async () => {
  const h = await montar();
  for (const dia of ["2026-10-01", "2026-10-31", "2026-12-31"]) {
    const q = await filtrar(h, { fecha: dia });
    assert.deepEqual([q.get("desde"), q.get("hasta")], [dia, dia]);
  }
});

/* ---------------- Combinados, Limpiar y Tablero ---------------- */

test("Combinados con búsqueda, categoría, prioridad, estado y Mis tickets", async () => {
  const h = await montar();
  await clic(h.nodos.get("vista-mios"));
  const q = await filtrar(h, {
    search: "vpn", category: "Red", priority: "Alta", state: "Cerrado",
    assigned: "4", fecha: "2026-10-15",
  });
  assert.deepEqual(Object.fromEntries([...q].filter(([k]) => !["limit", "offset"].includes(k))), {
    search: "vpn", category: "Red", priority: "Alta", state: "Cerrado", mios: "true",
    assigned_to: "4", desde: "2026-10-15", hasta: "2026-10-15",
  });
});

test("«Limpiar filtros» borra también «Asignado a» y la fecha", async () => {
  const h = await montar();
  await filtrar(h, { state: "Resuelto", assigned: "sin", fecha: "2026-10-15" });
  await clic(h.nodos.get("limpiar"));
  assert.deepEqual(CAMPOS.map((id) => h.nodos.get(id).value), ["", "", "", "", "", ""]);
  assert.deepEqual([...h.ultimo().keys()], ["limit"]);
});

test("Tablero: usa la misma consulta con los filtros nuevos", async () => {
  const h = await montar("Administrador", { vista: "tablero" });
  const q = await filtrar(h, { assigned: "4", fecha: "2026-10-15" });
  assert.deepEqual([q.get("assigned_to"), q.get("desde"), q.get("hasta")], ["4", "2026-10-15", "2026-10-15"]);
  assert.ok(h.nodos.get("tablero").children.length > 0, "el tablero se dibuja con lo que llegó");
});

test("Sin resultados con los filtros nuevos: «No hay tickets que coincidan con los filtros.»", async () => {
  const h = await montar();
  const filtros = h.sandbox.getFilters();
  assert.equal(h.sandbox.hayFiltros({ ...filtros, asignado: "sin" }), true);
  assert.equal(h.sandbox.hayFiltros({ ...filtros, fecha: "2026-10-15" }), true);
  assert.equal(h.sandbox.hayFiltros(filtros), false);
});
