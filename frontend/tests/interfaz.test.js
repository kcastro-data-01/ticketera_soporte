/* Pruebas de la interfaz común (frontend/js/auth.js): menú plegable.
   Ejecutar con: node --test frontend/tests/interfaz.test.js */

"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const authSource = fs.readFileSync(path.join(__dirname, "..", "js", "auth.js"), "utf8");

function nodo(tag, extra = {}) {
  const clases = new Set();
  const n = {
    tag, children: [], atributos: {}, listeners: {}, title: "", textContent: "", innerHTML: "",
    classList: {
      add: (c) => clases.add(c), remove: (c) => clases.delete(c), contains: (c) => clases.has(c),
      toggle: (c, si) => { const v = si === undefined ? !clases.has(c) : si; v ? clases.add(c) : clases.delete(c); return v; },
    },
    setAttribute(k, v) { this.atributos[k] = String(v); },
    getAttribute(k) { return this.atributos[k] ?? null; },
    removeAttribute(k) { delete this.atributos[k]; if (k === "title") this.title = ""; },
    addEventListener(t, fn) { (this.listeners[t] = this.listeners[t] || []).push(fn); },
    appendChild(h) { this.children.push(h); return h; },
    insertBefore(h, ref) { const i = this.children.indexOf(ref); this.children.splice(i < 0 ? this.children.length : i, 0, h); return h; },
    ...extra,
  };
  return n;
}

function montar(guardado) {
  const store = new Map(guardado ? [["menu_plegado", guardado]] : []);
  const enlaces = [nodo("a", { textContent: " Tickets " }), nodo("a", { textContent: "Ayuda" })];
  const marca = nodo("a");
  const despues = nodo("nav");
  marca.nextSibling = despues;
  const barra = nodo("aside");
  barra.children.push(marca, despues);
  barra.querySelector = (sel) => (sel === ".marca" ? marca : barra.children.find((c) => c.className === "boton-plegar") || null);
  barra.querySelectorAll = () => enlaces;
  const body = nodo("body");
  const doc = {
    body,
    querySelector: (sel) => (sel === ".barra-lateral" ? barra : null),
    createElement: (tag) => nodo(tag),
  };
  const ctx = {
    localStorage: { getItem: (k) => store.get(k) ?? null, setItem: (k, v) => store.set(k, String(v)), removeItem: (k) => store.delete(k) },
    window: { location: { href: "" } },
  };
  vm.createContext(ctx);
  vm.runInContext(authSource, ctx);
  const boton = ctx.iniciarMenuPlegable(doc);
  return { boton, body, barra, enlaces, store };
}

const clic = (n) => n.listeners.click.forEach((fn) => fn());

test("menú plegable: botón después de la marca, empieza expandido", () => {
  const m = montar();
  assert.equal(m.barra.children[1], m.boton);
  assert.equal(m.body.classList.contains("menu-plegado"), false);
  assert.equal(m.boton.atributos["aria-label"], "Achicar menú");
  assert.equal(m.boton.atributos["aria-expanded"], "true");
});

test("menú plegable: se pliega, deja tooltips y lo recuerda", () => {
  const m = montar();
  clic(m.boton);
  assert.equal(m.body.classList.contains("menu-plegado"), true);
  assert.equal(m.store.get("menu_plegado"), "1");
  assert.equal(m.enlaces[0].title, "Tickets");
  assert.equal(m.boton.atributos["aria-label"], "Expandir menú");
  clic(m.boton);
  assert.equal(m.body.classList.contains("menu-plegado"), false);
  assert.equal(m.store.get("menu_plegado"), "0");
  assert.equal(m.enlaces[0].title, "");
});

test("menú plegable: al abrir otra página se aplica lo guardado", () => {
  const m = montar("1");
  assert.equal(m.body.classList.contains("menu-plegado"), true);
});
