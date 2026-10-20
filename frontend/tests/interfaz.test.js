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

/* --- Modo oscuro --- */

function montarTema(guardado, { conAcciones = true } = {}) {
  const store = new Map(guardado ? [["tema", guardado]] : []);
  const html = nodo("html");
  const acciones = nodo("div");
  const cabecera = nodo("header");
  cabecera.querySelector = (sel) => (sel === ".cabecera-acciones" && conAcciones ? acciones : null);
  const eventos = [];
  const doc = {
    documentElement: html,
    body: nodo("body"),
    querySelector: (sel) => (sel === ".cabecera" ? cabecera : sel === ".boton-tema" ? null : null),
    createElement: (tag) => nodo(tag),
    dispatchEvent: (e) => eventos.push(e),
    addEventListener() {},
  };
  class CustomEventFalso { constructor(tipo, init) { this.type = tipo; this.detail = init && init.detail; } }
  const ctx = {
    localStorage: { getItem: (k) => store.get(k) ?? null, setItem: (k, v) => store.set(k, String(v)), removeItem: (k) => store.delete(k) },
    window: { location: { href: "" } },
    CustomEvent: CustomEventFalso,
  };
  vm.createContext(ctx);
  vm.runInContext(authSource, ctx);
  ctx.aplicarTema(ctx.temaGuardado(), doc);
  const boton = ctx.iniciarBotonTema(doc);
  return { boton, html, acciones, cabecera, store, eventos };
}

test("tema: sin preferencia empieza claro, con el ícono de luna", () => {
  const t = montarTema();
  assert.equal(t.html.getAttribute("data-tema"), null);
  assert.equal(t.acciones.children[0], t.boton, "va en la barra superior");
  assert.equal(t.boton.atributos["aria-label"], "Activar modo oscuro");
  assert.match(t.boton.innerHTML, /M21 12\.8A9 9/, "luna");
});

test("tema: el botón cambia a oscuro, lo guarda y avisa a las gráficas", () => {
  const t = montarTema();
  clic(t.boton);
  assert.equal(t.html.getAttribute("data-tema"), "oscuro");
  assert.equal(t.store.get("tema"), "oscuro");
  assert.equal(t.boton.atributos["aria-pressed"], "true");
  assert.match(t.boton.innerHTML, /circle cx="12" cy="12" r="4"/, "sol");
  assert.deepEqual(t.eventos.map((e) => [e.type, e.detail.tema]), [["tema-cambiado", "oscuro"]]);
  clic(t.boton);
  assert.equal(t.html.getAttribute("data-tema"), null);
  assert.equal(t.store.get("tema"), "claro");
});

test("tema: se aplica lo guardado al abrir otra página", () => {
  const t = montarTema("oscuro");
  assert.equal(t.html.getAttribute("data-tema"), "oscuro");
  assert.equal(t.boton.atributos["aria-label"], "Activar modo claro");
});

test("tema: si la cabecera no tiene zona de acciones, se crea", () => {
  const t = montarTema(null, { conAcciones: false });
  const creada = t.cabecera.children[0];
  assert.equal(creada.className, "cabecera-acciones");
  assert.equal(creada.children[0], t.boton);
});

test("todas las páginas aplican el tema guardado en el <head>", () => {
  const dir = path.join(__dirname, "..");
  for (const f of fs.readdirSync(dir).filter((n) => n.endsWith(".html"))) {
    const html = fs.readFileSync(path.join(dir, f), "utf8");
    const cabeza = html.slice(0, html.indexOf("</head>"));
    assert.match(cabeza, /localStorage\.getItem\("tema"\)==="oscuro"/, f);
  }
});
