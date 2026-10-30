/* Listado (frontend/js/app.js + index.html): vista simple solo para el
   Solicitante; Técnico y Administrador ven la vista completa.
   Ejecutar con: node --test frontend/tests/listado_solicitante.test.js */

"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const leer = (archivo) => fs.readFileSync(path.join(__dirname, "..", archivo), "utf8");
const authSource = leer("js/auth.js");
const appSource = leer("js/app.js");
const indexHtml = leer("index.html");

const IDS = [
  "form-filtros", "search", "category", "priority", "state", "limpiar", "estado-carga", "lista-tickets",
  "paginacion", "pagina-anterior", "pagina-siguiente", "pagina-info",
  "titulo-listado", "subtitulo-listado",
  "th-asignado", "nuevo-ticket-solicitante", "sin-solicitudes", "tabla-tickets",
];

const TEXTOS_INICIALES = {
  "titulo-listado": "Tickets",
  "subtitulo-listado": "Consulta y gestión de los tickets de soporte",
  "th-asignado": "Asignado a",
};

const TICKETS = [
  { id: 7, title: "VPN", category: "Red", priority: "Alta", state: "En proceso", assigned_to_id: 2, created_at: "2026-10-20T15:00:00Z" },
  { id: 8, title: "Monitor", category: "Hardware", priority: "Media", state: "Nuevo", assigned_to_id: null, created_at: "2026-10-21T15:00:00Z" },
];

function nodo(id) {
  return {
    id, tag: id, value: "", textContent: TEXTOS_INICIALES[id] || "", className: "", children: [],
    dataset: {}, atributos: {}, listeners: {},
    hidden: ["nuevo-ticket-solicitante", "sin-solicitudes", "estado-carga"].includes(id),
    classList: { add() {}, remove() {}, toggle() {}, contains: () => false },
    setAttribute(k, v) { this.atributos[k] = String(v); },
    addEventListener(t, fn) { (this.listeners[t] = this.listeners[t] || []).push(fn); },
    appendChild(h) { this.children.push(h); return h; },
    replaceChildren(...h) { this.children = h; },
    reset() {},
  };
}

/* Monta el listado con el rol indicado y espera a que cargue. */
async function montar(rol, tickets = TICKETS) {
  const nodos = new Map(IDS.map((id) => [id, nodo(id)]));
  const equipo = ["t-nuevos", "t-en-proceso", "t-criticos", "f-categoria", "f-prioridad", "th-categoria", "th-prioridad"].map(nodo);
  const user = { id: 9, name: "Andrea Castillo", role: rol };
  const doc = {
    title: "Tickets · American Data Networks",
    getElementById: (id) => nodos.get(id) || null,
    querySelector: () => null,
    querySelectorAll: (sel) => (sel === '[data-vista="equipo"]' ? equipo : []),
    createElement: (tag) => nodo(tag),
    addEventListener() {},
  };
  const sandbox = {
    document: doc,
    window: { location: { href: "", search: "" } },
    localStorage: {
      getItem: (k) => ({ access_token: "t", user: JSON.stringify(user) })[k] ?? null,
      setItem() {}, removeItem() {},
    },
    fetch: async (url) => ({
      ok: true, status: 200, headers: { get: () => String(tickets.length) },
      json: async () => {
        if (url.includes("/api/users")) return [{ id: 2, name: "José Solano" }];
        return tickets;
      },
    }),
    console: { error() {}, log() {} },
    URLSearchParams, Map, Number, Object, String, Boolean, Date,
  };
  vm.createContext(sandbox);
  vm.runInContext(authSource, sandbox);
  vm.runInContext(appSource, sandbox);
  sandbox.init();
  for (let i = 0; i < 10; i += 1) await new Promise((r) => setImmediate(r));
  const filas = nodos.get("lista-tickets").children;
  return { nodos, equipo, doc, filas };
}

const textos = (fila) => fila.children.map((c) => String(c.textContent || (c.children[0] && c.children[0].textContent) || ""));

test("Solicitante: títulos, botón «Nuevo ticket» y sin lo del equipo", async () => {
  const { nodos, equipo, doc } = await montar("Solicitante");
  assert.equal(nodos.get("titulo-listado").textContent, "Mis solicitudes");
  assert.equal(nodos.get("subtitulo-listado").textContent, "Consulte el estado de sus tickets de soporte");
  assert.equal(nodos.get("nuevo-ticket-solicitante").hidden, false);
  assert.ok(equipo.every((el) => el.hidden), "filtros, columnas y Tabla/Tablero del equipo ocultos");
  assert.equal(nodos.get("th-asignado").textContent, "Atendido por");
  assert.match(doc.title, /^Mis solicitudes/);
});

test("Solicitante: tabla con ID, Título, Estado, Atendido por, Fecha y Ver", async () => {
  const { filas } = await montar("Solicitante");
  assert.equal(filas.length, 2);
  assert.equal(filas[0].children.length, 6, "sin Categoría ni Prioridad");
  const [id, titulo, estado, atendido, , accion] = textos(filas[0]);
  assert.deepEqual([id, titulo, estado, atendido, accion], ["7", "VPN", "En proceso", "José Solano", "Ver"]);
  assert.equal(textos(filas[1])[3], "Pendiente de asignar");
  assert.equal(filas[1].children[3].className, "celda-pendiente celda-asignado", "sin círculo de iniciales");
  assert.ok(!textos(filas[0]).includes("Red") && !textos(filas[0]).includes("Alta"));
});

test("Solicitante sin tickets: «Todavía no ha creado solicitudes» con «Nuevo ticket»", async () => {
  const { nodos, filas } = await montar("Solicitante", []);
  assert.equal(nodos.get("sin-solicitudes").hidden, false);
  assert.equal(nodos.get("tabla-tickets").hidden, true);
  assert.equal(nodos.get("estado-carga").hidden, true);
  assert.equal(filas.length, 0);
  assert.match(indexHtml, /<div id="sin-solicitudes"[^>]*>\s*<p>Todavía no ha creado solicitudes\.<\/p>\s*<a href="crear\.html" class="enlace-boton">Nuevo ticket<\/a>/);
});

for (const rol of ["Técnico", "Administrador"]) {
  test(`${rol}: vista completa sin cambios`, async () => {
    const { nodos, equipo, filas } = await montar(rol);
    assert.equal(nodos.get("titulo-listado").textContent, "Tickets");
    assert.equal(nodos.get("th-asignado").textContent, "Asignado a");
    assert.equal(nodos.get("nuevo-ticket-solicitante").hidden, true);
    assert.ok(equipo.every((el) => !el.hidden));
    assert.equal(filas[0].children.length, 8, "con Categoría y Prioridad");
    assert.deepEqual(textos(filas[0]).slice(0, 5), ["7", "VPN", "Red", "Alta", "En proceso"]);
    assert.equal(textos(filas[1])[5], "—", "sin asignar se ve como siempre");
  });

  test(`${rol} sin tickets: el aviso de siempre, sin la invitación del Solicitante`, async () => {
    const { nodos } = await montar(rol, []);
    assert.equal(nodos.get("sin-solicitudes").hidden, true);
    assert.equal(nodos.get("estado-carga").textContent, "No hay tickets para mostrar.");
  });
}

test("Solicitante: los tickets asignados a él dicen «Asignado a usted»", async () => {
  const asignado = { ...TICKETS[0], id: 9, title: "Impresora", assigned_to_id: 9 };
  const { filas } = await montar("Solicitante", [asignado, ...TICKETS]);
  assert.equal(textos(filas[0])[3], "Asignado a usted");
  assert.equal(textos(filas[1])[3], "José Solano");
});

test("index.html marca como «equipo» Categoría, Prioridad y Tabla/Tablero", () => {
  const marcados = [...indexHtml.matchAll(/<[^>]*data-vista="equipo"[^>]*>(?:\s*<[^>]*>)*\s*([^<]*)/g)].map((m) => m[0]);
  assert.equal(marcados.length, 5);
  for (const texto of [">Categoría", ">Prioridad", 'aria-label="Cómo ver los tickets"']) {
    assert.ok(marcados.some((m) => m.includes(texto)), texto);
  }
});

test("la categoría lleva su ícono (clase por categoría)", async () => {
  const { filas } = await montar("Técnico");
  assert.equal(filas[0].children[2].className, "celda-categoria cat-red");
  assert.equal(filas[1].children[2].className, "celda-categoria cat-hardware");
  assert.equal(String(filas[0].children[2].textContent), "Red", "el texto se mantiene");
  const css = leer("css/estilos.css");
  for (const cat of ["hardware", "software", "red", "accesos"]) assert.match(css, new RegExp(`\\.cat-${cat} \\{ --icono-categoria`));
});

test("filas Críticas y Altas destacadas solo en la vista del equipo", async () => {
  const conCritica = [...TICKETS, { ...TICKETS[1], id: 9, priority: "Crítica" }];
  const equipo = await montar("Técnico", conCritica);
  assert.deepEqual(equipo.filas.map((f) => f.className), ["fila-alta", "", "fila-critica"]);
  const solicitante = await montar("Solicitante", conCritica);
  assert.ok(solicitante.filas.every((f) => !f.className), "el Solicitante no ve la prioridad");
});

test("cada celda lleva su clase para la tarjeta del celular", async () => {
  const equipo = await montar("Técnico");
  assert.deepEqual(equipo.filas[0].children.map((c) => c.className.split(" ")[0]),
    ["celda-id", "celda-titulo", "celda-categoria", "celda-prioridad", "celda-estado", "celda-asignado", "celda-fecha", "celda-accion"]);
  const solicitante = await montar("Solicitante");
  assert.deepEqual(solicitante.filas[0].children.map((c) => c.className.split(" ")[0]),
    ["celda-id", "celda-titulo", "celda-estado", "celda-asignado", "celda-fecha", "celda-accion"]);
});
