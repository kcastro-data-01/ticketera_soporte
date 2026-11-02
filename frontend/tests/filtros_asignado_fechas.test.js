/* Filtros «Asignado a» y «Desde / Hasta» del listado (app.js + index.html):
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

const CAMPOS = ["search", "category", "priority", "state", "assigned", "fecha-campo", "desde", "hasta"];
const INICIAL = { "fecha-campo": "creacion" };
const IDS = [
  "form-filtros", ...CAMPOS, "limpiar", "estado-carga", "lista-tickets", "paginacion",
  "pagina-anterior", "pagina-siguiente", "pagina-info", "tabla-tickets", "tablero",
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
  /* La vista que se recuerda se lee con su clave real. */
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

test("index.html: «Asignado a» (solo equipo), «Fecha de», «Desde» y «Hasta» antes de los botones", () => {
  const form = indexHtml.slice(indexHtml.indexOf('id="form-filtros"'), indexHtml.indexOf("</form>"));
  assert.match(form, /<label class="campo" data-vista="equipo">\s*<span>Asignado a<\/span>\s*<select id="assigned" name="assigned">\s*<option value="">Todos<\/option>\s*<option value="sin">Sin asignar<\/option>/);
  assert.match(form, /<select id="fecha-campo" name="fecha_campo">\s*<option value="creacion">Creación<\/option>\s*<option value="en_proceso">En proceso<\/option>\s*<option value="resuelto">Resuelto<\/option>\s*<option value="cerrado">Cerrado<\/option>/);
  assert.match(form, /<label class="campo campo-fecha">\s*<span>Desde<\/span>\s*<input type="date" id="desde"/);
  assert.match(form, /<label class="campo campo-fecha">\s*<span>Hasta<\/span>\s*<input type="date" id="hasta"/);
  assert.ok(form.indexOf('id="hasta"') < form.indexOf('id="limpiar"'), "los botones quedan al final");
});

test("estilos: en celular «Desde» y «Hasta» van de a dos, sin colores nuevos", () => {
  const css = leer("css/estilos.css");
  const movil = css.slice(css.indexOf("@media (max-width: 768px)"));
  assert.match(movil, /\.campo\.campo-fecha \{\s*flex: 1 1 calc\(50% - 0\.3rem\);\s*min-width: 0;\s*\}/);
  const regla = movil.slice(movil.indexOf(".campo.campo-fecha"), movil.indexOf("}", movil.indexOf(".campo.campo-fecha")));
  assert.doesNotMatch(regla, /#|rgb|color/);
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

test("Fechas: solo «Desde», solo «Hasta» o los dos; con Creación no se manda fecha_campo", async () => {
  const h = await montar();
  let q = await filtrar(h, { desde: "2026-10-01" });
  assert.deepEqual([q.get("desde"), q.has("hasta"), q.has("fecha_campo")], ["2026-10-01", false, false]);

  q = await filtrar(h, { desde: "", hasta: "2026-10-31" });
  assert.deepEqual([q.has("desde"), q.get("hasta")], [false, "2026-10-31"]);

  q = await filtrar(h, { desde: "2026-10-01", hasta: "2026-10-31", "fecha-campo": "cerrado" });
  assert.deepEqual([q.get("desde"), q.get("hasta"), q.get("fecha_campo")], ["2026-10-01", "2026-10-31", "cerrado"]);
});

test("Fechas: el mismo día en «Desde» y «Hasta» es válido (los dos extremos incluidos)", async () => {
  const h = await montar();
  const q = await filtrar(h, { desde: "2026-10-15", hasta: "2026-10-15" });
  assert.deepEqual([q.get("desde"), q.get("hasta")], ["2026-10-15", "2026-10-15"]);
});

test("Fechas: «Fecha de» sin días no filtra", async () => {
  const h = await montar();
  const q = await filtrar(h, { "fecha-campo": "resuelto" });
  assert.equal(q.has("fecha_campo") || q.has("desde") || q.has("hasta"), false);
});

test("Fechas: «Desde» posterior a «Hasta» avisa sin pedirle nada a la API", async () => {
  const h = await montar();
  const antes = h.pedidos.length;
  h.nodos.get("desde").value = "2026-10-31";
  h.nodos.get("hasta").value = "2026-10-01";
  await enviar(h.nodos.get("form-filtros"));
  assert.equal(h.pedidos.length, antes);
  assert.equal(h.nodos.get("estado-carga").textContent, "La fecha «Desde» no puede ser posterior a «Hasta».");
  assert.equal(h.nodos.get("estado-carga").className, "estado error");
});

/* ---------------- Combinados, Limpiar y Tablero ---------------- */

test("Combinados con búsqueda, categoría, prioridad, estado y Mis tickets", async () => {
  const h = await montar();
  await clic(h.nodos.get("vista-mios"));
  const q = await filtrar(h, {
    search: "vpn", category: "Red", priority: "Alta", state: "Cerrado",
    assigned: "4", "fecha-campo": "en_proceso", desde: "2026-10-01", hasta: "2026-10-31",
  });
  assert.deepEqual(Object.fromEntries([...q].filter(([k]) => !["limit", "offset"].includes(k))), {
    search: "vpn", category: "Red", priority: "Alta", state: "Cerrado", mios: "true",
    assigned_to: "4", fecha_campo: "en_proceso", desde: "2026-10-01", hasta: "2026-10-31",
  });
});

test("«Limpiar filtros» borra también «Asignado a», «Fecha de» y las fechas", async () => {
  const h = await montar();
  await filtrar(h, { assigned: "sin", "fecha-campo": "cerrado", desde: "2026-10-01", hasta: "2026-10-31" });
  await clic(h.nodos.get("limpiar"));
  assert.deepEqual(CAMPOS.map((id) => h.nodos.get(id).value), ["", "", "", "", "", "creacion", "", ""]);
  assert.deepEqual([...h.ultimo().keys()], ["limit"]);
});

test("Tablero: usa la misma consulta con los filtros nuevos", async () => {
  const h = await montar("Administrador", { vista: "tablero" });
  const q = await filtrar(h, { assigned: "4", desde: "2026-10-01" });
  assert.deepEqual([q.get("assigned_to"), q.get("desde")], ["4", "2026-10-01"]);
  assert.ok(h.nodos.get("tablero").children.length > 0, "el tablero se dibuja con lo que llegó");
});

test("Sin resultados con los filtros nuevos: «No hay tickets que coincidan con los filtros.»", async () => {
  const h = await montar();
  const filtros = h.sandbox.getFilters();
  assert.equal(h.sandbox.hayFiltros({ ...filtros, asignado: "sin" }), true);
  assert.equal(h.sandbox.hayFiltros({ ...filtros, hasta: "2026-10-31" }), true);
  assert.equal(h.sandbox.hayFiltros(filtros), false);
});
