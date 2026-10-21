/* Listado (frontend/js/app.js + index.html): vista simple solo para el
   Solicitante; Técnico, Supervisor y Administrador ven la vista completa.
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
  "res-nuevos", "res-en-proceso", "res-pendientes", "res-resueltos", "res-criticos", "res-mios",
  "titulo-listado", "subtitulo-listado", "etq-pendientes", "etq-resueltos", "opt-pendientes", "opt-resueltos",
  "th-asignado", "nuevo-ticket-solicitante", "sin-solicitudes", "tabla-tickets",
];

const TEXTOS_INICIALES = {
  "titulo-listado": "Tickets",
  "subtitulo-listado": "Consulta y gestión de los tickets de soporte",
  "etq-pendientes": "Pendientes",
  "etq-resueltos": "Resueltos",
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
        if (url.includes("summary")) return { total: 5, nuevos: 2, en_proceso: 1, resueltos: 2, cerrados: 1, criticos_abiertos: 1, mios_abiertos: 0 };
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

test("Solicitante: títulos, botón «Nuevo ticket» y solo Abiertas y Resueltas", async () => {
  const { nodos, equipo, doc } = await montar("Solicitante");
  assert.equal(nodos.get("titulo-listado").textContent, "Mis solicitudes");
  assert.equal(nodos.get("subtitulo-listado").textContent, "Consulte el estado de sus tickets de soporte");
  assert.equal(nodos.get("nuevo-ticket-solicitante").hidden, false);
  assert.equal(nodos.get("etq-pendientes").textContent, "Abiertas");
  assert.equal(nodos.get("etq-resueltos").textContent, "Resueltas");
  assert.equal(nodos.get("res-pendientes").textContent, "3", "Abiertas = Nuevo + En proceso");
  assert.equal(nodos.get("res-resueltos").textContent, "2", "Resueltas = Resuelto + Cerrado");
  assert.ok(equipo.every((el) => el.hidden), "tarjetas, filtros y columnas del equipo ocultos");
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
  assert.equal(filas[1].children[3].className, "celda-pendiente", "sin círculo de iniciales");
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

for (const rol of ["Técnico", "Supervisor", "Administrador"]) {
  test(`${rol}: vista completa sin cambios`, async () => {
    const { nodos, equipo, filas } = await montar(rol);
    assert.equal(nodos.get("titulo-listado").textContent, "Tickets");
    assert.equal(nodos.get("etq-pendientes").textContent, "Pendientes");
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

test("index.html marca como «equipo» Nuevos, En proceso, Críticos, Categoría y Prioridad", () => {
  const marcados = [...indexHtml.matchAll(/<[^>]*data-vista="equipo"[^>]*>(?:\s*<[^>]*>)*\s*([^<]*)/g)].map((m) => m[0]);
  assert.equal(marcados.length, 7);
  for (const texto of ['data-estado="Nuevo"', 'data-estado="En proceso"', 'data-prioridad="Crítica"', ">Categoría", ">Prioridad"]) {
    assert.ok(marcados.some((m) => m.includes(texto)), texto);
  }
  assert.doesNotMatch(indexHtml, /data-estado="Nuevo,En proceso"[^>]*data-vista="equipo"/, "Pendientes/Abiertas queda");
  assert.doesNotMatch(indexHtml, /data-estado="Resuelto,Cerrado"[^>]*data-vista="equipo"/, "Resueltos/Resueltas queda");
});

test("la categoría lleva su ícono (clase por categoría)", async () => {
  const { filas } = await montar("Técnico");
  assert.equal(filas[0].children[2].className, "celda-categoria cat-red");
  assert.equal(filas[1].children[2].className, "celda-categoria cat-hardware");
  assert.equal(String(filas[0].children[2].textContent), "Red", "el texto se mantiene");
  const css = leer("css/estilos.css");
  for (const cat of ["hardware", "software", "red", "accesos"]) assert.match(css, new RegExp(`\\.cat-${cat} \\{ --icono-categoria`));
});
