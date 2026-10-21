/* Usuario abajo del menú lateral (auth.js): iniciales, nombre, rol y menú
   que se abre hacia arriba con «Mi cuenta» y «Cerrar sesión».
   Ejecutar con: node --test frontend/tests/menu_usuario.test.js */

"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const authSource = fs.readFileSync(path.join(__dirname, "..", "js", "auth.js"), "utf8");
const leer = (archivo) => fs.readFileSync(path.join(__dirname, "..", archivo), "utf8");
const css = leer("css/estilos.css");
const PAGINAS_CON_MENU = fs.readdirSync(path.join(__dirname, ".."))
  .filter((f) => f.endsWith(".html") && leer(f).includes('<aside class="barra-lateral">'));

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
  const barra = el("aside");
  const docListeners = {};
  const doc = {
    createElement: el,
    querySelector: (sel) => ({ ".cabecera": cabecera, ".barra-lateral": conMenuLateral ? barra : null })[sel] || null,
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
  return { sandbox, menu, cabecera, barra, docListeners };
}

const buscar = (n, clase) => (n.className.split(" ").includes(clase) ? n : n.children.map((h) => buscar(h, clase)).find(Boolean));

test("muestra iniciales, nombre y rol abajo del menú lateral, no en la barra superior", () => {
  const { menu, cabecera, barra } = montar();
  assert.equal(barra.children.at(-1), menu, "último elemento del menú lateral");
  assert.equal(cabecera.children.length, 0, "arriba no se agrega nada");
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
  assert.equal(lista.children.length, 2);
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

test("las pantallas con menú lateral no tienen otro «Cerrar sesión» ni el bloque viejo", () => {
  assert.ok(PAGINAS_CON_MENU.length >= 8, PAGINAS_CON_MENU.join(", "));
  for (const pagina of PAGINAS_CON_MENU) {
    const html = leer(pagina);
    assert.doesNotMatch(html, /btn-logout|barra-salir|barra-usuario|Cerrar sesión/, pagina);
    assert.match(html, /<script src="js\/auth\.js" defer><\/script>/, `${pagina}: carga auth.js, que crea el menú`);
  }
});

test("CSS: colores claros sobre el azul, menú hacia arriba, plegado y celular", () => {
  const regla = (sel) => css.slice(css.indexOf(`\n${sel} {`), css.indexOf("\n}", css.indexOf(`\n${sel} {`) + 1));
  assert.match(regla(".menu-usuario-nombre"), /color: var\(--color-texto-inverso\);/);
  assert.match(regla(".menu-usuario-rol"), /color: var\(--color-menu-tenue\);/);
  assert.match(regla(".menu-usuario-flecha"), /stroke: var\(--color-menu-tenue\);/, "flecha del tono del rol");
  assert.match(regla(".menu-usuario-lista"), /bottom: calc\(100% \+ 4px\);/, "se abre hacia arriba");
  assert.match(css, /body\.menu-plegado \.menu-usuario-datos,\n  body\.menu-plegado \.menu-usuario-flecha \{\n    display: none;/, "plegado: solo las iniciales");
  assert.match(css, /\.barra-lateral:has\(\.menu-usuario-lista:not\(\[hidden\]\)\) \{\s*z-index: 50;\s*overflow: visible;/, "abierto no se recorta");
  assert.match(css, /\.barra-lateral \.menu-usuario-lista \{\s*top: calc\(100% \+ 4px\);\s*bottom: auto;/, "celular: el menú va arriba y se abre hacia abajo");
  assert.doesNotMatch(css, /barra-salir|boton-cerrar-sesion/);
});

test("sin sesión o sin menú lateral (login) no se agrega", () => {
  assert.equal(montar({ conMenuLateral: false }).menu, null);
  assert.equal(montar({ user: null }).menu, null);
});
