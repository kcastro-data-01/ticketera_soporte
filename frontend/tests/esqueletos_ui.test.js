/* Esqueletos de carga: marcarCargando() (auth.js) y las filas grises del
   listado mientras llega la respuesta.
   Ejecutar con: node --test frontend/tests/esqueletos_ui.test.js */

"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const leer = (archivo) => fs.readFileSync(path.join(__dirname, "..", archivo), "utf8");

function cargarAuth() {
  const sandbox = { console, localStorage: { getItem: () => null, setItem() {}, removeItem() {} } };
  vm.runInNewContext(leer("js/auth.js"), sandbox, { filename: "auth.js" });
  return sandbox;
}

test("marcarCargando pone y quita la clase y aria-busy", () => {
  const { marcarCargando } = cargarAuth();
  const clases = new Set();
  const el = {
    atributos: {},
    classList: { toggle: (c, si) => (si ? clases.add(c) : clases.delete(c)) },
    setAttribute(k, v) { this.atributos[k] = v; },
  };
  marcarCargando(el, true);
  assert.ok(clases.has("esqueleto-activo"));
  assert.equal(el.atributos["aria-busy"], "true");
  marcarCargando(el, false);
  assert.equal(clases.has("esqueleto-activo"), false);
  assert.equal(el.atributos["aria-busy"], "false");
  assert.doesNotThrow(() => marcarCargando(null, true));
});

test("el listado muestra filas grises mientras carga y las quita al llegar los datos", async () => {
  let resolver;
  const nodos = new Map();
  const nodo = (id) => {
    if (!nodos.has(id)) {
      nodos.set(id, {
        id, textContent: "", className: "", hidden: true, value: "", children: [], dataset: {},
        addEventListener() {}, appendChild(h) { this.children.push(h); return h; },
        replaceChildren(...h) { this.children = h; }, reset() {},
      });
    }
    return nodos.get(id);
  };
  const sandbox = {
    console, URLSearchParams,
    localStorage: { getItem: (k) => (k === "access_token" ? "t" : null), setItem() {}, removeItem() {} },
    window: { location: { href: "", search: "" } },
    document: {
      getElementById: nodo,
      querySelector: () => null,
      querySelectorAll: () => [],
      addEventListener() {},
      createElement: (tag) => ({ tag, className: "", textContent: "", children: [], dataset: {},
        appendChild(h) { this.children.push(h); return h; }, addEventListener() {}, setAttribute() {} }),
    },
    fetch: () => new Promise((ok) => { resolver = ok; }),
  };
  vm.runInNewContext(leer("js/auth.js") + "\n" + leer("js/app.js"), sandbox, { filename: "app.js" });
  const carga = sandbox.fetchTickets();
  const tbody = nodo("lista-tickets");
  assert.equal(tbody.children.length, 6);
  assert.ok(tbody.children.every((fila) => fila.className === "fila-esqueleto"));
  assert.equal(tbody.children[0].children.length, 8, "una celda por columna");

  resolver({ ok: true, status: 200, headers: { get: () => "0" }, json: async () => [] });
  await carga;
  assert.ok(tbody.children.every((fila) => fila.className !== "fila-esqueleto"));
});

test("detalle y métricas usan el esqueleto", () => {
  assert.match(leer("js/detalle.js"), /marcarCargando\(panel, true\)/);
  assert.match(leer("js/metricas.js"), /marcarCargando\(zona, true\)/);
  // Bloques grises fijos, sin brillo animado (estilo sobrio).
  const css = leer("css/estilos.css");
  assert.match(css, /\.esqueleto-barra,/);
  assert.doesNotMatch(css, /esqueleto-brillo/);
});
