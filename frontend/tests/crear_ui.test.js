/* Formulario de nuevo ticket (frontend/js/crear.js): la prioridad elegida
   con los botones es la que se envía.
   Ejecutar con: node --test frontend/tests/crear_ui.test.js */

"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const authSource = fs.readFileSync(path.join(__dirname, "..", "js", "auth.js"), "utf8");
const crearSource = fs.readFileSync(path.join(__dirname, "..", "js", "crear.js"), "utf8");

function nodo(extra = {}) {
  return {
    value: "", textContent: "", className: "", hidden: false, disabled: false, listeners: {},
    addEventListener(t, fn) { (this.listeners[t] = this.listeners[t] || []).push(fn); },
    ...extra,
  };
}

function montar() {
  const ids = {
    "form-crear": nodo(), title: nodo({ value: "Impresora" }), description: nodo({ value: "No imprime" }),
    category: nodo({ value: "Hardware" }), priority: nodo({ value: "Media" }), guardar: nodo(), "estado-carga": nodo(),
  };
  const opciones = ["Baja", "Media", "Alta", "Crítica"].map((v) => nodo({ value: v, checked: v === "Media" }));
  const enviados = [];
  const sandbox = {
    document: {
      getElementById: (id) => ids[id] || null,
      querySelectorAll: (sel) => (sel.includes("opcion-prioridad") ? opciones : []),
      addEventListener() {},
    },
    window: { location: { href: "" } },
    localStorage: { getItem: (k) => (k === "access_token" ? "t" : null), setItem() {}, removeItem() {} },
    fetch: async (url, o) => { enviados.push(JSON.parse(o.body)); return { ok: true, status: 201, json: async () => ({ id: 7 }) }; },
    setTimeout() {}, console: { error() {} },
  };
  vm.createContext(sandbox);
  vm.runInContext(authSource, sandbox);
  vm.runInContext(crearSource, sandbox);
  sandbox.init();
  return { sandbox, ids, opciones, enviados };
}

const elegir = (opcion, todas) => {
  todas.forEach((o) => { o.checked = o === opcion; });
  opcion.listeners.change.forEach((fn) => fn());
};

test("la prioridad empieza en Media y cambia con los botones", async () => {
  const f = montar();
  assert.equal(f.ids.priority.value, "Media");
  elegir(f.opciones[3], f.opciones);
  assert.equal(f.ids.priority.value, "Crítica");
  await f.sandbox.createTicket();
  assert.equal(f.enviados[0].priority, "Crítica");
  assert.equal(f.enviados[0].title, "Impresora");
});

test("el formulario tiene texto de ayuda y botones en lugar de la lista", () => {
  const html = fs.readFileSync(path.join(__dirname, "..", "crear.html"), "utf8");
  assert.doesNotMatch(html, /<select id="priority"/);
  assert.match(html, /<input type="hidden" id="priority" name="priority" value="Media">/);
  for (const v of ["Baja", "Media", "Alta", "Crítica"]) {
    assert.match(html, new RegExp(`name="opcion-prioridad" value="${v}"`));
  }
  assert.equal((html.match(/class="ayuda-campo"/g) || []).length, 4);
});
