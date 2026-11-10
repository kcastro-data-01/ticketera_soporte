/* Recuadro de filtros del listado (app.js + index.html): siempre visible,
   con «Buscar» y «Limpiar filtros», y sin las tarjetas de resumen arriba.
   Ejecutar con: node --test frontend/tests/filtros_listado.test.js */

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
  "total-tickets", "tabla-tickets", "tablero",
];

function nodo(tag) {
  const clases = new Set();
  return {
    tag, value: "", textContent: "", children: [], dataset: {}, atributos: {}, listeners: {}, hidden: false,
    classList: {
      add: (c) => clases.add(c), remove: (c) => clases.delete(c), contains: (c) => clases.has(c),
      toggle: (c, si) => ((si ?? !clases.has(c)) ? clases.add(c) : clases.delete(c)),
    },
    setAttribute(k, v) { this.atributos[k] = String(v); },
    addEventListener(t, fn) { (this.listeners[t] = this.listeners[t] || []).push(fn); },
    appendChild(h) { this.children.push(h); return h; },
    append(...hs) { hs.forEach((h) => this.appendChild(h)); },
    replaceChildren(...hs) { this.children = hs; },
    reset() { ["search", "category", "priority", "state"].forEach((id) => { this.campos.get(id).value = ""; }); },
  };
}

async function montar() {
  return montarCon(new Map(IDS.map((id) => [id, nodo(id)])));
}

async function montarCon(nodos) {
  nodos.get("form-filtros").campos = nodos;
  const store = new Map();
  const pedidos = [];
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
      getItem: (k) => (k === "user" ? JSON.stringify({ id: 9, name: "José", role: "Técnico" })
        : k === "access_token" ? "t" : store.get(k) ?? null),
      setItem: (k, v) => store.set(k, v), removeItem: (k) => store.delete(k),
    },
    fetch: async (url) => {
      pedidos.push(url);
      return { ok: true, status: 200, headers: { get: () => "0" }, json: async () => (url.includes("summary") ? {} : []) };
    },
    console: { error() {}, log() {} },
    URLSearchParams, Map, Number, Object, String, Boolean, Date,
  };
  vm.createContext(sandbox);
  vm.runInContext(leer("js/auth.js"), sandbox);
  vm.runInContext(leer("js/app.js"), sandbox);
  sandbox.init();
  await esperar();
  return { nodos, store, pedidos };
}

const esperar = async () => { for (let i = 0; i < 10; i += 1) await new Promise((r) => setImmediate(r)); };
const clic = (n) => n.listeners.click.forEach((fn) => fn());
const enviar = (n) => n.listeners.submit.forEach((fn) => fn({ preventDefault() {} }));

test("index.html: sin tarjetas de resumen ni botón Filtros; el recuadro de filtros siempre visible", () => {
  assert.doesNotMatch(indexHtml, /class="resumen|tarjeta-resumen|id="res-|id="etq-/);
  assert.doesNotMatch(indexHtml, /filtros-boton|filtros-texto/);
  assert.match(indexHtml, /<form id="form-filtros" class="filtros">/, "sin hidden");
  const app = leer("js/app.js");
  assert.doesNotMatch(app, /\/api\/tickets\/summary|tarjeta-resumen|filtros_abiertos/, "el listado ya no pide el resumen");
  assert.doesNotMatch(css, /filtros-boton|tarjeta-icono|\.resumen \.tarjeta-resumen/);
  // «Buscar» (primario, el de siempre) junto a «Limpiar filtros», dentro del recuadro.
  const form = indexHtml.slice(indexHtml.indexOf('<form id="form-filtros"'), indexHtml.indexOf("</form>"));
  assert.match(form, /<button type="submit" id="buscar">Buscar<\/button>\s*<button type="button" id="limpiar" class="secundario">Limpiar filtros<\/button>/);
  // Enter en «Buscar» envía el formulario: el campo está dentro y hay un botón submit.
  assert.match(form, /<input\s+type="search"\s+id="search"/);
});

test("Buscar (o Enter en el campo) envía el formulario y pide el listado filtrado", async () => {
  const { nodos, pedidos } = await montar();
  const antes = pedidos.length;
  nodos.get("search").value = "impresora";
  enviar(nodos.get("form-filtros"));
  await esperar();
  assert.equal(pedidos.length, antes + 1);
  assert.match(pedidos.at(-1), /search=impresora/);
});

test("index.html: el filtro «Estado» tiene Todos, Abiertos y los cuatro estados", () => {
  const select = indexHtml.slice(indexHtml.indexOf('<select id="state"'), indexHtml.indexOf("</select>", indexHtml.indexOf('<select id="state"')));
  const opciones = [...select.matchAll(/<option value="([^"]*)"[^>]*>([^<]*)<\/option>/g)].map((m) => [m[1], m[2]]);
  assert.deepEqual(opciones, [
    ["", "Todos"], ["abiertos", "Abiertos"], ["Nuevo", "Nuevo"], ["En proceso", "En proceso"],
    ["Resuelto", "Resuelto"], ["Cerrado", "Cerrado"],
  ]);
  assert.doesNotMatch(indexHtml, /Pendientes|Resueltos y cerrados|opt-pendientes|opt-resueltos/);
  assert.doesNotMatch(leer("js/app.js"), /opt-pendientes|opt-resueltos|Abiertas|Resueltas/);
});

test("un filtro viejo («Pendientes», «Resueltos y cerrados») restaurado vuelve a «Todos» sin error", async () => {
  for (const viejo of ["Nuevo,En proceso", "Resuelto,Cerrado"]) {
    const nodos = new Map(IDS.map((id) => [id, nodo(id)]));
    nodos.get("state").value = viejo;
    const { pedidos } = await montarCon(nodos);
    assert.equal(nodos.get("state").value, "", viejo);
    const listado = pedidos.filter((u) => u.startsWith("/api/tickets"));
    assert.ok(listado.length > 0);
    listado.forEach((u) => assert.doesNotMatch(u, /state=/, u));
  }
});

test("elegir un estado pide solo ese estado", async () => {
  const { nodos, pedidos } = await montar();
  nodos.get("state").value = "Resuelto";
  enviar(nodos.get("form-filtros"));
  await esperar();
  assert.match(pedidos.at(-1), /^\/api\/tickets\?state=Resuelto&limit=1000$/);
});

test("ayuda.html describe el filtro «Estado» sin los grupos viejos", () => {
  const ayuda = leer("ayuda.html");
  assert.match(ayuda, /El filtro «Estado» ofrece Todos, Abiertos \(Nuevo y En proceso\), Nuevo, En proceso, Resuelto o Cerrado/);
  assert.doesNotMatch(ayuda, /Resueltos y cerrados|«Pendientes»/);
});

test("filtros en escritorio: solo «Buscar» se estira, Estado ajustado y los botones al final, dentro de la caja", () => {
  const css = leer("css/estilos.css");
  const ini = css.indexOf("/* ---------- Filtros del listado (index.html)");
  const bloque = css.slice(ini, css.indexOf("/* «Nuevo ticket»", ini));
  const escritorio = bloque.slice(bloque.indexOf("@media (min-width: 769px)"));
  assert.ok(escritorio.length > 0, "regla de escritorio desde 769 px");
  // La fila se parte si no entra (nunca nowrap): así nada se sale de la caja.
  assert.match(escritorio, /#form-filtros \{\s*flex-wrap: wrap;/);
  assert.doesNotMatch(bloque, /#form-filtros \{[^}]*flex-wrap: nowrap/);
  // Los campos van a su ancho justo; «Buscar» es el único que crece, con mínimo.
  assert.match(escritorio, /#form-filtros > \.campo \{\s*flex: none;/);
  assert.match(escritorio, /#form-filtros > \.campo-busqueda \{\s*flex: 1 1 9rem;\s*min-width: 9rem;/);
  assert.equal((escritorio.match(/flex: 1 1/g) || []).length, 1, "solo «Buscar» se estira");
  // Botones al final de la fila (o, si bajan, a la derecha) y sin partirse.
  assert.match(escritorio, /#form-filtros > \.acciones \{[^}]*flex: none;[^}]*margin-left: auto;/);
  // Mismo alto en campos y botones.
  assert.match(bloque, /#form-filtros \.campo :is\(input, select\),\s*#form-filtros \.acciones button \{[^}]*height: var\(--alto-control\);/);
  // «Estado» corto: su opción más larga ya no es «Abiertos (Nuevo y En proceso)».
  assert.match(indexHtml, /<option value="abiertos" title="Nuevo y En proceso">Abiertos<\/option>/);
});
