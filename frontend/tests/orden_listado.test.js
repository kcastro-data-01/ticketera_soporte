/* Orden de columnas del listado (app.js): prioridad y estado con su orden
   propio, ascendente/descendente y recordado en localStorage.
   Ejecutar con: node --test frontend/tests/orden_listado.test.js */

"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const leer = (archivo) => fs.readFileSync(path.join(__dirname, "..", archivo), "utf8");

const TICKETS = [
  { id: 3, title: "monitor", priority: "Media", state: "Resuelto", created_at: "2026-10-03T10:00:00Z" },
  { id: 1, title: "Correo", priority: "Baja", state: "Nuevo", created_at: "2026-10-01T10:00:00Z" },
  { id: 4, title: "VPN", priority: "Crítica", state: "Cerrado", created_at: "2026-10-04T10:00:00Z" },
  { id: 2, title: "Acceso", priority: "Alta", state: "En proceso", created_at: "2026-10-02T10:00:00Z" },
];

function cargar(guardado = null) {
  const store = new Map(guardado ? [["orden_listado", JSON.stringify(guardado)]] : []);
  const th = (campo) => {
    const t = { atributos: {}, setAttribute(k, v) { this.atributos[k] = v; } };
    t.boton = { dataset: { orden: campo }, parentElement: t, listeners: {}, addEventListener(e, fn) { this.listeners[e] = fn; } };
    return t;
  };
  const columnas = ["id", "title", "priority", "state", "created_at"].map(th);
  const sandbox = {
    console,
    document: {
      getElementById: () => null,
      querySelectorAll: (sel) => (sel === ".orden-columna" ? columnas.map((c) => c.boton) : []),
      addEventListener() {},
    },
    window: { location: {} },
    localStorage: { getItem: (k) => store.get(k) ?? null, setItem: (k, v) => store.set(k, v), removeItem: (k) => store.delete(k) },
    URLSearchParams, Map, Date,
  };
  vm.createContext(sandbox);
  vm.runInContext(leer("js/auth.js"), sandbox);
  vm.runInContext(leer("js/app.js"), sandbox);
  return { sandbox, store, columnas };
}

const ids = (lista) => lista.map((t) => t.id);

test("prioridad: Crítica > Alta > Media > Baja, no alfabético", () => {
  const { sandbox } = cargar();
  assert.deepEqual(ids(sandbox.ordenarTickets(TICKETS, { campo: "priority", dir: "asc" })), [4, 2, 3, 1]);
  assert.deepEqual(ids(sandbox.ordenarTickets(TICKETS, { campo: "priority", dir: "desc" })), [1, 3, 2, 4]);
});

test("estado sigue el flujo; ID, título y fecha en los dos sentidos", () => {
  const { sandbox } = cargar();
  assert.deepEqual(ids(sandbox.ordenarTickets(TICKETS, { campo: "state", dir: "asc" })), [1, 2, 3, 4]);
  assert.deepEqual(ids(sandbox.ordenarTickets(TICKETS, { campo: "id", dir: "desc" })), [4, 3, 2, 1]);
  assert.deepEqual(ids(sandbox.ordenarTickets(TICKETS, { campo: "title", dir: "asc" })), [2, 1, 3, 4], "sin distinguir mayúsculas");
  assert.deepEqual(ids(sandbox.ordenarTickets(TICKETS, { campo: "created_at", dir: "asc" })), [1, 2, 3, 4]);
  assert.deepEqual(ids(sandbox.ordenarTickets(TICKETS, null)), [3, 1, 4, 2], "sin orden elegido queda el de la API");
});

test("clic alterna ascendente/descendente, marca la flechita y se recuerda", () => {
  const { sandbox, store, columnas } = cargar();
  sandbox.cambiarOrden("priority");
  assert.deepEqual(JSON.parse(store.get("orden_listado")), { campo: "priority", dir: "asc" });
  assert.equal(columnas[2].atributos["aria-sort"], "ascending");
  assert.equal(columnas[0].atributos["aria-sort"], "none");
  sandbox.cambiarOrden("priority");
  assert.equal(columnas[2].atributos["aria-sort"], "descending");
  sandbox.cambiarOrden("id");
  assert.deepEqual(JSON.parse(store.get("orden_listado")), { campo: "id", dir: "asc" });
});

test("el orden guardado se usa al volver a abrir el listado", () => {
  const { sandbox } = cargar({ campo: "state", dir: "desc" });
  assert.deepEqual(ids(sandbox.ordenarTickets(TICKETS)), [4, 3, 2, 1]);
  const invalido = cargar({ campo: "category", dir: "asc" });
  assert.deepEqual(ids(invalido.sandbox.ordenarTickets(TICKETS)), [3, 1, 4, 2]);
});

test("encabezados ordenables en index.html y encabezado fijo en el CSS", () => {
  const html = leer("index.html");
  const campos = [...html.matchAll(/class="orden-columna" data-orden="([^"]+)"/g)].map((m) => m[1]);
  assert.deepEqual(campos, ["id", "title", "priority", "state", "created_at"]);
  assert.match(leer("css/estilos.css"), /#tabla-tickets \.listado thead th \{\s*position: sticky;/);
});
