/* Pestañas del detalle del ticket (frontend/js/detalle.js y detalle.html):
   Comentarios, Historial y Explicación IA, solo las del rol, y la última
   abierta se recuerda en localStorage.
   Ejecutar con: node --test frontend/tests/pestanas_detalle.test.js */

"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const leer = (archivo) => fs.readFileSync(path.join(__dirname, "..", archivo), "utf8");
const authSource = leer("js/auth.js");
const detalleSource = leer("js/detalle.js");
const html = leer("detalle.html");
const css = leer("css/estilos.css");

const PESTANAS = [
  ["comentarios", "seccion-comentarios", null],
  ["historial", "seccion-historial", null],
  ["ia", "seccion-ia", "explicar_ia"],
];

function montar({ rol = "Técnico", guardada = null } = {}) {
  const store = new Map([["access_token", "t"], ["user", JSON.stringify({ name: "Ana", role: rol })]]);
  if (guardada) store.set("detalle_pestana", guardada);
  const nodo = (id) => ({
    id, hidden: false, tabIndex: 0, focused: false, dataset: {}, atributos: {}, listeners: {},
    setAttribute(k, v) { this.atributos[k] = String(v); },
    getAttribute(k) { return this.atributos[k] ?? null; },
    addEventListener(t, fn) { (this.listeners[t] = this.listeners[t] || []).push(fn); },
    focus() { this.focused = true; },
  });
  const paneles = {};
  const pestanas = PESTANAS.map(([nombre, panel, permiso]) => {
    const p = nodo(`pestana-${nombre}`);
    p.dataset.pestana = nombre;
    if (permiso) p.dataset.permiso = permiso;
    p.atributos["aria-controls"] = panel;
    paneles[panel] = nodo(panel);
    if (permiso) paneles[panel].dataset.permiso = permiso;
    return p;
  });
  const sandbox = {
    document: {
      getElementById: (id) => paneles[id] || null,
      querySelectorAll: (sel) => (sel === "#pestanas-detalle [role=tab]" ? pestanas : []),
      addEventListener() {},
    },
    window: { location: { search: "?id=1", href: "" } },
    localStorage: { getItem: (k) => store.get(k) ?? null, setItem: (k, v) => store.set(k, String(v)), removeItem: (k) => store.delete(k) },
    console: { error() {} },
    URLSearchParams, Date, Number,
  };
  vm.createContext(sandbox);
  vm.runInContext(authSource, sandbox);
  vm.runInContext(detalleSource, sandbox);
  /* Como en la página: aplicarPermisos (auth.js) corre antes que el detalle
     y solo mira los elementos con data-permiso. */
  const conPermiso = [...pestanas, ...Object.values(paneles)].filter((n) => n.dataset.permiso);
  sandbox.aplicarPermisos({ querySelectorAll: () => conPermiso });
  sandbox.iniciarPestanas();
  const activa = () => pestanas.find((p) => p.atributos["aria-selected"] === "true").dataset.pestana;
  const visibles = () => Object.values(paneles).filter((p) => !p.hidden).map((p) => p.id);
  return { pestanas, paneles, store, activa, visibles };
}

test("html: tres pestañas con su panel, en orden, debajo de la descripción", () => {
  const lista = [...html.matchAll(/role="tab"[^>]*data-pestana="([a-z]+)"[^>]*aria-controls="([a-z-]+)"[^>]*>([^<]+)</g)]
    .map((m) => [m[1], m[2], m[3]]);
  assert.deepEqual(lista, [
    ["comentarios", "seccion-comentarios", "Comentarios"],
    ["historial", "seccion-historial", "Historial"],
    ["ia", "seccion-ia", "Explicación IA"],
  ]);
  assert.match(html, /id="pestana-ia"[^>]*data-permiso="explicar_ia"/, "la de IA con el mismo permiso que su sección");
  for (const [, panel] of PESTANAS) assert.match(html, new RegExp(`id="${panel}"[^>]*role="tabpanel"`));
  assert.ok(html.indexOf('id="ver-description"') < html.indexOf('id="pestanas-detalle"'));
  assert.match(css, /\.pestanas-lista \.pestana\[aria-selected="true"\] \{\s*border-bottom-color: var\(--color-primario\);/);
});

test("abre Comentarios por defecto y muestra solo su panel", () => {
  const d = montar();
  assert.equal(d.activa(), "comentarios");
  assert.deepEqual(d.visibles(), ["seccion-comentarios"]);
  assert.equal(d.pestanas[0].tabIndex, 0);
  assert.equal(d.pestanas[1].tabIndex, -1);
});

test("al cambiar de pestaña se recuerda y se vuelve a abrir esa", () => {
  const d = montar();
  d.pestanas[1].listeners.click[0]();
  assert.deepEqual(d.visibles(), ["seccion-historial"]);
  assert.equal(d.store.get("detalle_pestana"), "historial");
  const otra = montar({ guardada: "ia" });
  assert.equal(otra.activa(), "ia");
  assert.deepEqual(otra.visibles(), ["seccion-ia"]);
});

test("flechas izquierda y derecha pasan a la pestaña vecina", () => {
  const d = montar();
  const tecla = (p, key) => p.listeners.keydown[0]({ key, preventDefault() {} });
  tecla(d.pestanas[0], "ArrowLeft");
  assert.equal(d.activa(), "ia");
  assert.equal(d.pestanas[2].focused, true);
  tecla(d.pestanas[2], "ArrowRight");
  assert.equal(d.activa(), "comentarios");
});

test("el Solicitante no ve la pestaña de IA aunque fuera la última abierta", () => {
  const d = montar({ rol: "Solicitante", guardada: "ia" });
  assert.equal(d.pestanas[2].hidden, true);
  assert.equal(d.activa(), "comentarios");
  assert.deepEqual(d.visibles(), ["seccion-comentarios"], "el panel de IA no se abre");
  assert.equal(d.store.get("detalle_pestana"), "comentarios");
});
