/* Usuario en la barra superior (auth.js): iniciales, nombre, rol y menú
   con «Mi cuenta» y «Cerrar sesión».
   Ejecutar con: node --test frontend/tests/menu_usuario.test.js */

"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const authSource = fs.readFileSync(path.join(__dirname, "..", "js", "auth.js"), "utf8");

function el(tag) {
  const n = {
    tag, className: "", textContent: "", hidden: false, children: [], atributos: {}, listeners: {}, html: "",
    setAttribute(k, v) { this.atributos[k] = String(v); },
    addEventListener(t, fn) { (this.listeners[t] = this.listeners[t] || []).push(fn); },
    appendChild(h) { this.children.push(h); h.padre = this; return h; },
    append(...hs) { hs.forEach((h) => this.appendChild(h)); },
    insertAdjacentHTML(_, html) { this.html += html; },
    contains(otro) { for (let x = otro; x; x = x.padre) if (x === this) return true; return false; },
    querySelector() { return null; },
    focus() { this.enfocado = true; },
  };
  return n;
}

function montar({ conMenuLateral = true, user = { name: "Laura Méndez", role: "Administrador" } } = {}) {
  const cabecera = el("header");
  const docListeners = {};
  const doc = {
    createElement: el,
    querySelector: (sel) => ({ ".cabecera": cabecera, ".barra-lateral": conMenuLateral ? {} : null })[sel] || null,
    addEventListener: (t, fn) => { (docListeners[t] = docListeners[t] || []).push(fn); },
  };
  const sandbox = {
    console,
    window: { location: { href: "" } },
    localStorage: { getItem: (k) => (k === "user" ? JSON.stringify(user) : null), setItem() {}, removeItem() {} },
    sessionStorage: { removeItem() {} },
  };
  vm.runInNewContext(authSource, sandbox);
  const menu = sandbox.crearMenuUsuario(doc);
  return { sandbox, menu, cabecera, docListeners };
}

const buscar = (n, clase) => (n.className.split(" ").includes(clase) ? n : n.children.map((h) => buscar(h, clase)).find(Boolean));

test("muestra iniciales, nombre y rol en la barra superior", () => {
  const { menu, cabecera } = montar();
  assert.equal(cabecera.children[0].className, "cabecera-acciones");
  assert.equal(cabecera.children[0].children[0], menu);
  assert.equal(buscar(menu, "menu-usuario-avatar").textContent, "LM");
  assert.equal(buscar(menu, "menu-usuario-nombre").textContent, "Laura Méndez");
  assert.equal(buscar(menu, "menu-usuario-rol").textContent, "Administrador");
});

test("el menú se abre y cierra, y tiene Mi cuenta y Cerrar sesión", () => {
  const { sandbox, menu, docListeners } = montar();
  const boton = buscar(menu, "menu-usuario-boton");
  const lista = buscar(menu, "menu-usuario-lista");
  assert.equal(lista.hidden, true);
  assert.equal(boton.atributos["aria-haspopup"], "menu");

  boton.listeners.click[0]({ stopPropagation() {} });
  assert.equal(lista.hidden, false);
  assert.equal(boton.atributos["aria-expanded"], "true");
  const [cuenta, salir] = lista.children;
  assert.equal(cuenta.textContent, "Mi cuenta");
  assert.equal(cuenta.href, "cuenta.html");
  assert.equal(salir.textContent, "Cerrar sesión");

  docListeners.click[0]({ target: {} });
  assert.equal(lista.hidden, true, "un clic afuera lo cierra");

  boton.listeners.click[0]({ stopPropagation() {} });
  docListeners.keydown[0]({ key: "Escape" });
  assert.equal(lista.hidden, true, "Escape lo cierra");
  assert.equal(boton.enfocado, true);

  salir.listeners.click[0]();
  assert.equal(sandbox.window.location.href, "login.html");
});

test("sin sesión o sin menú lateral (login) no se agrega", () => {
  assert.equal(montar({ conMenuLateral: false }).menu, null);
  assert.equal(montar({ user: null }).menu, null);
});
