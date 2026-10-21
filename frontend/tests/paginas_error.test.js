/* Páginas «no encontrado» y «sin permiso», y el bloque «Ticket no
   encontrado» del detalle.
   Ejecutar con: node --test frontend/tests/paginas_error.test.js */

"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const leer = (archivo) => fs.readFileSync(path.join(__dirname, "..", archivo), "utf8");

test("404.html y sin-permiso.html tienen marca, mensaje y botón para volver", () => {
  for (const [archivo, titulo] of [["404.html", "Página no encontrada"], ["sin-permiso.html", "Acceso restringido"]]) {
    const html = leer(archivo);
    assert.match(html, new RegExp(`<h1>${titulo}</h1>`), archivo);
    assert.match(html, /<a href="\/index\.html" class="enlace-boton">Volver al inicio<\/a>/, archivo);
    assert.match(html, /<body class="pagina-error">/, archivo);
    assert.match(html, /href="\/css\/estilos\.css"/, "rutas absolutas: funciona en cualquier dirección");
  }
});

function detalle({ search = "?id=5", estado = 404 } = {}) {
  const nodos = new Map();
  const nodo = (id) => {
    if (!nodos.has(id)) {
      nodos.set(id, {
        id, textContent: "", className: "", hidden: ["ticket-no-encontrado"].includes(id), disabled: false, value: "",
        children: [], dataset: {}, listeners: {},
        addEventListener(t, fn) { (this.listeners[t] = this.listeners[t] || []).push(fn); },
        appendChild(h) { this.children.push(h); return h; }, replaceChildren() {}, setAttribute() {}, removeAttribute() {},
        focus() {}, querySelectorAll: () => [],
      });
    }
    return nodos.get(id);
  };
  const sandbox = {
    console: { error() {}, log() {} },
    document: { getElementById: nodo, createElement: () => nodo(`x${Math.random()}`), querySelector: () => null, querySelectorAll: () => [], addEventListener() {} },
    window: { location: { search, href: "" }, addEventListener() {} },
    localStorage: { getItem: (k) => ({ access_token: "t", user: JSON.stringify({ name: "Ana", role: "Técnico" }) })[k] ?? null, setItem() {}, removeItem() {} },
    fetch: async (url) => ({
      ok: !/\/api\/tickets\/\d+$/.test(url) || estado === 200, status: /\/api\/tickets\/\d+$/.test(url) ? estado : 200,
      headers: { get: () => null }, json: async () => [],
    }),
    URLSearchParams, Date, Map,
  };
  vm.createContext(sandbox);
  vm.runInContext(leer("js/auth.js"), sandbox);
  vm.runInContext(leer("js/detalle.js"), sandbox);
  return { sandbox, nodo };
}

test("un ticket que no existe muestra el bloque con «Volver al listado»", async () => {
  const { sandbox, nodo } = detalle();
  await sandbox.init();
  assert.equal(nodo("ticket-no-encontrado").hidden, false);
  assert.equal(nodo("detalle-layout").hidden, true);
  assert.equal(nodo("ticket-no-encontrado-mensaje").textContent, "No existe el ticket #5 o no tiene acceso a él.");
  assert.match(leer("detalle.html"), /<section id="ticket-no-encontrado"[\s\S]*?<a href="index\.html" class="enlace-boton">Volver al listado<\/a>/);
});

test("un identificador inválido también muestra el bloque", async () => {
  const { sandbox, nodo } = detalle({ search: "?id=abc" });
  await sandbox.init();
  assert.equal(nodo("ticket-no-encontrado").hidden, false);
  assert.match(nodo("ticket-no-encontrado-mensaje").textContent, /no es válido/);
});
