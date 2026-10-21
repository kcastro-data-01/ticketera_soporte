/* Tarjetas de resumen del listado (frontend/js/app.js): Pendientes y la
   tarjeta del filtro aplicado resaltada.
   Ejecutar con: node --test frontend/tests/resumen_ui.test.js */

"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const authSource = fs.readFileSync(path.join(__dirname, "..", "js", "auth.js"), "utf8");
const appSource = fs.readFileSync(path.join(__dirname, "..", "js", "app.js"), "utf8");

function nodo(id, dataset = {}) {
  const clases = new Set();
  return {
    id, dataset, value: "", textContent: "", children: [], atributos: {}, listeners: {},
    classList: {
      toggle: (c, si) => (si ? clases.add(c) : clases.delete(c)),
      contains: (c) => clases.has(c),
      add: (c) => clases.add(c), remove: (c) => clases.delete(c),
    },
    setAttribute(k, v) { this.atributos[k] = String(v); },
    addEventListener(t, fn) { (this.listeners[t] = this.listeners[t] || []).push(fn); },
    appendChild(h) { this.children.push(h); return h; },
    replaceChildren(...h) { this.children = h; },
    reset() { ["search", "category", "priority", "state"].forEach((k) => { nodos.get(k).value = ""; }); },
  };
}

let nodos;

function montar() {
  nodos = new Map(
    ["search", "category", "priority", "state", "form-filtros", "estado-carga", "lista-tickets",
     "res-nuevos", "res-en-proceso", "res-pendientes", "res-resueltos", "res-criticos", "res-mios"]
      .map((id) => [id, nodo(id)])
  );
  const tarjetas = [
    nodo("t-nuevos", { estado: "Nuevo" }),
    nodo("t-pendientes", { estado: "Nuevo,En proceso" }),
    nodo("t-criticos", { prioridad: "Crítica" }),
    nodo("t-mios", { mios: "true" }),
  ];
  const sandbox = {
    document: {
      getElementById: (id) => nodos.get(id) || null,
      querySelectorAll: (sel) => (sel === ".tarjeta-resumen" ? tarjetas : []),
      createElement: (tag) => nodo(tag),
      addEventListener() {},
    },
    window: { location: {} },
    localStorage: { getItem: (k) => (k === "access_token" ? "t" : null), setItem() {}, removeItem() {} },
    fetch: async (url) => ({
      ok: true, status: 200, headers: { get: () => "0" },
      json: async () => (url.includes("summary")
        ? { total: 9, nuevos: 3, en_proceso: 2, resueltos: 4, cerrados: 1, criticos_abiertos: 1, mios_abiertos: 0 }
        : []),
    }),
    console: { error() {}, log() {} },
    URLSearchParams, Map, Number,
  };
  vm.createContext(sandbox);
  vm.runInContext(authSource, sandbox);
  vm.runInContext(appSource, sandbox);
  return { sandbox, tarjetas };
}

test("Pendientes = Nuevos + En proceso", async () => {
  const { sandbox } = montar();
  await sandbox.cargarResumen();
  assert.equal(nodos.get("res-pendientes").textContent, "5");
  assert.equal(nodos.get("res-nuevos").textContent, "3");
});

test("al pulsar una tarjeta filtra por su estado y queda resaltada", () => {
  const { sandbox, tarjetas } = montar();
  sandbox.aplicarTarjeta(tarjetas[1]);
  assert.equal(nodos.get("state").value, "Nuevo,En proceso");
  assert.deepEqual(tarjetas.map((t) => t.classList.contains("activa")), [false, true, false, false]);
  assert.equal(tarjetas[1].atributos["aria-pressed"], "true");

  sandbox.aplicarTarjeta(tarjetas[2]);
  assert.equal(nodos.get("priority").value, "Crítica");
  assert.deepEqual(tarjetas.map((t) => t.classList.contains("activa")), [false, false, true, false]);
});

test("con otros filtros o sin filtro no queda ninguna resaltada", () => {
  const { sandbox, tarjetas } = montar();
  sandbox.aplicarTarjeta(tarjetas[0]);
  nodos.get("search").value = "impresora";
  sandbox.irAPagina(0);
  assert.ok(tarjetas.every((t) => !t.classList.contains("activa")));
  nodos.get("search").value = "";
  nodos.get("state").value = "";
  sandbox.irAPagina(0);
  assert.ok(tarjetas.every((t) => !t.classList.contains("activa")));
});
