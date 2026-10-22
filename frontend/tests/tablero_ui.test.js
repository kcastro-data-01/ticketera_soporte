/* Vista de tablero y densidad del listado (app.js + index.html): botones
   Tabla/Tablero y Compacta/Cómoda recordados en localStorage, una columna
   por estado con los tickets ya cargados y, en el celular, columnas una
   debajo de la otra.
   Ejecutar con: node --test frontend/tests/tablero_ui.test.js */

"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const leer = (archivo) => fs.readFileSync(path.join(__dirname, "..", archivo), "utf8");
const indexHtml = leer("index.html");
const css = leer("css/estilos.css");

const IDS = [
  "form-filtros", "search", "category", "priority", "state", "limpiar", "estado-carga", "lista-tickets",
  "paginacion", "pagina-anterior", "pagina-siguiente", "pagina-info", "tabla-tickets", "tablero",
  "ver-tabla", "ver-tablero", "sin-solicitudes", "densidad", "densidad-compacta", "densidad-comoda",
];

const TICKETS = [
  { id: 7, title: "VPN", category: "Red", priority: "Alta", state: "En proceso", assigned_to_id: 2, created_at: "2026-10-20T15:00:00Z" },
  { id: 8, title: "Monitor", category: "Hardware", priority: "Media", state: "Nuevo", assigned_to_id: null, created_at: "2026-10-21T15:00:00Z" },
  { id: 9, title: "Correo", category: "Software", priority: "Crítica", state: "Nuevo", assigned_to_id: 2, created_at: "2026-10-22T15:00:00Z" },
];

function nodo(tag) {
  const clases = new Set();
  const n = {
    tag, value: "", textContent: "", children: [], dataset: {}, atributos: {}, listeners: {}, hidden: false, href: "",
    get className() { return [...clases].join(" "); },
    set className(v) { clases.clear(); String(v).split(/\s+/).filter(Boolean).forEach((c) => clases.add(c)); },
    classList: {
      add: (c) => clases.add(c), remove: (c) => clases.delete(c), contains: (c) => clases.has(c),
      toggle: (c, si) => ((si ?? !clases.has(c)) ? clases.add(c) : clases.delete(c)),
    },
    setAttribute(k, v) { this.atributos[k] = String(v); },
    addEventListener(t, fn) { (this.listeners[t] = this.listeners[t] || []).push(fn); },
    appendChild(h) { this.children.push(h); return h; },
    append(...hs) { hs.forEach((h) => this.appendChild(h)); },
    replaceChildren(...hs) { this.children = hs; },
    reset() {},
  };
  return n;
}

async function montar({ rol = "Técnico", guardado = null, densidadGuardada = null } = {}) {
  const nodos = new Map(IDS.map((id) => [id, nodo(id)]));
  nodos.get("tablero").hidden = true;
  const store = new Map(guardado ? [["vista_listado", guardado]] : []);
  if (densidadGuardada) store.set("densidad_listado", densidadGuardada);
  const user = { id: 9, name: "Andrea Castillo", role: rol };
  const sandbox = {
    document: {
      title: "",
      getElementById: (id) => nodos.get(id) || null,
      querySelector: () => null,
      querySelectorAll: () => [],
      createElement: nodo,
      addEventListener() {},
    },
    window: { location: { href: "", search: "" } },
    localStorage: {
      getItem: (k) => (k === "user" ? JSON.stringify(user) : k === "access_token" ? "t" : store.get(k) ?? null),
      setItem: (k, v) => store.set(k, v), removeItem: (k) => store.delete(k),
    },
    fetch: async (url) => ({
      ok: true, status: 200, headers: { get: () => String(TICKETS.length) },
      json: async () => {
        if (url.includes("summary")) return { total: 3, nuevos: 2, en_proceso: 1, resueltos: 0, cerrados: 0, criticos_abiertos: 1, mios_abiertos: 1 };
        if (url.includes("/api/users")) return [{ id: 2, name: "José Solano" }];
        return TICKETS;
      },
    }),
    console: { error() {}, log() {} },
    URLSearchParams, Map, Number, Object, String, Boolean, Date,
  };
  vm.createContext(sandbox);
  vm.runInContext(leer("js/auth.js"), sandbox);
  vm.runInContext(leer("js/app.js"), sandbox);
  sandbox.init();
  for (let i = 0; i < 10; i += 1) await new Promise((r) => setImmediate(r));
  return { nodos, store, sandbox };
}

const columnas = (nodos) => nodos.get("tablero").children;
const tarjetas = (columna) => columna.children[1].children.filter((t) => t.tag === "a");

test("index.html: botones Tabla y Tablero junto a los filtros, ocultos para el Solicitante", () => {
  assert.match(indexHtml, /<\/form>\s*<!--[\s\S]*?-->\s*<div class="listado-opciones">\s*<div class="vista-tabs" role="group" aria-label="Cómo ver los tickets" data-vista="equipo">/);
  assert.match(indexHtml, /<button type="button" id="ver-tabla" class="vista-tab activa" aria-pressed="true">Tabla<\/button>/);
  assert.match(indexHtml, /<button type="button" id="ver-tablero" class="vista-tab" aria-pressed="false">Tablero<\/button>/);
  assert.match(indexHtml, /<div id="tablero" class="tablero" aria-label="Tickets por estado" hidden><\/div>/);
});

test("por defecto se ve la tabla; al pulsar Tablero se muestra y se recuerda", async () => {
  const { nodos, store } = await montar();
  assert.equal(nodos.get("tabla-tickets").hidden, false);
  assert.equal(nodos.get("tablero").hidden, true);
  assert.equal(columnas(nodos).length, 0, "el tablero no se arma si no se usa");

  nodos.get("ver-tablero").listeners.click[0]();
  assert.equal(store.get("vista_listado"), "tablero");
  assert.equal(nodos.get("tabla-tickets").hidden, true);
  assert.equal(nodos.get("tablero").hidden, false);
  assert.equal(nodos.get("ver-tablero").atributos["aria-pressed"], "true");
  assert.equal(nodos.get("ver-tabla").atributos["aria-pressed"], "false");
  assert.ok(nodos.get("ver-tablero").classList.contains("activa"));
  assert.equal(nodos.get("densidad").hidden, true, "la densidad es solo de la tabla");

  nodos.get("ver-tabla").listeners.click[0]();
  assert.equal(store.get("vista_listado"), "tabla");
  assert.equal(nodos.get("tabla-tickets").hidden, false);
  assert.equal(nodos.get("tablero").hidden, true);
  assert.equal(nodos.get("densidad").hidden, false);
});

test("tablero: 4 columnas por estado con ID, título, prioridad y asignado", async () => {
  const { nodos } = await montar({ guardado: "tablero" });
  assert.equal(nodos.get("tablero").hidden, false, "la elección guardada se usa al volver");
  const cols = columnas(nodos);
  assert.deepEqual(cols.map((c) => c.children[0].children[0].textContent), ["Nuevo", "En proceso", "Resuelto", "Cerrado"]);
  assert.deepEqual(cols.map((c) => c.children[0].children[1].textContent), ["2", "1", "0", "0"]);
  assert.equal(cols[2].children[1].children[0].textContent, "Sin tickets");

  const [monitor, critico] = tarjetas(cols[0]); // orden de la API, como en la tabla
  assert.equal(critico.href, "detalle.html?id=9", "clic en la tarjeta abre el detalle");
  const [cabeza, titulo, asignado] = critico.children;
  assert.equal(cabeza.children[0].textContent, "#9");
  assert.equal(cabeza.children[1].textContent, "Crítica");
  assert.equal(cabeza.children[1].className, "badge prioridad-critica");
  assert.equal(titulo.textContent, "Correo");
  assert.equal(asignado.textContent, "José Solano");
  assert.ok(critico.classList.contains("fila-critica"));
  assert.equal(monitor.children[2].textContent, "Sin asignar");
  assert.ok(monitor.children[2].classList.contains("sin-asignar"));
});

test("el tablero usa los mismos tickets filtrados que la tabla", async () => {
  const { nodos } = await montar({ guardado: "tablero" });
  const enTablero = columnas(nodos).flatMap(tarjetas).length;
  assert.equal(enTablero, nodos.get("lista-tickets").children.length);
});

test("Solicitante: siempre tabla, aunque haya quedado guardado el tablero", async () => {
  const { nodos } = await montar({ rol: "Solicitante", guardado: "tablero" });
  assert.equal(nodos.get("tabla-tickets").hidden, false);
  assert.equal(nodos.get("tablero").hidden, true);
  assert.equal(columnas(nodos).length, 0);
});

test("densidad: Cómoda por defecto; Compacta achica las filas y se recuerda", async () => {
  const { nodos, store } = await montar();
  const tabla = nodos.get("tabla-tickets");
  assert.equal(tabla.classList.contains("densidad-compacta"), false);
  assert.equal(nodos.get("densidad-comoda").atributos["aria-pressed"], "true");

  nodos.get("densidad-compacta").listeners.click[0]();
  assert.equal(store.get("densidad_listado"), "compacta");
  assert.ok(tabla.classList.contains("densidad-compacta"));
  assert.equal(nodos.get("densidad-compacta").atributos["aria-pressed"], "true");
  assert.equal(nodos.get("densidad-comoda").atributos["aria-pressed"], "false");

  const otraVez = await montar({ densidadGuardada: "compacta" });
  assert.ok(otraVez.nodos.get("tabla-tickets").classList.contains("densidad-compacta"), "se usa al volver");

  nodos.get("densidad-comoda").listeners.click[0]();
  assert.equal(store.get("densidad_listado"), "comoda");
  assert.equal(tabla.classList.contains("densidad-compacta"), false);
});

test("densidad: botón junto a Tabla/Tablero, también para el Solicitante; CSS con menos espacio", async () => {
  assert.match(indexHtml, /aria-label="Cómo ver los tickets" data-vista="equipo">[\s\S]*?<\/div>\s*<div class="vista-tabs" id="densidad" role="group" aria-label="Densidad de la tabla">/);
  assert.match(indexHtml, /id="densidad-compacta" class="vista-tab" aria-pressed="false">Compacta<\/button>\s*<button type="button" id="densidad-comoda" class="vista-tab activa" aria-pressed="true">Cómoda<\/button>/);
  assert.doesNotMatch(indexHtml, /id="densidad"[^>]*data-vista/);
  const { nodos } = await montar({ rol: "Solicitante" });
  assert.equal(nodos.get("densidad").hidden, false);
  assert.match(css, /#tabla-tickets\.densidad-compacta \.listado th,\n#tabla-tickets\.densidad-compacta \.listado td \{\s*padding-top: 0\.3rem;\s*padding-bottom: 0\.3rem;/);
});

test("CSS: 4 columnas y, en el celular, una debajo de la otra; sin degradados", () => {
  assert.match(css, /\.tablero \{[^}]*grid-template-columns: repeat\(4, minmax\(0, 1fr\)\);/);
  assert.match(css, /@media \(max-width: 700px\) \{\s*\.tablero \{\s*grid-template-columns: 1fr;/);
  const bloque = css.slice(css.indexOf("/* ===== Tablero por estado"), css.indexOf("/* ===== Fin del tablero"));
  assert.ok(bloque.length > 0);
  assert.doesNotMatch(bloque, /gradient/);
});
