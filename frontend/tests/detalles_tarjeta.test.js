/* «Detalles» del detalle del ticket en una tarjeta moderna: filas con ícono y
   etiqueta tenue a la izquierda y el valor a la derecha, nombres con «…» y el
   completo en el title, fechas relativas con la exacta al pasar el mouse y al
   imprimir, y debajo de la descripción en pantallas angostas.
   Ejecutar con: node --test frontend/tests/detalles_tarjeta.test.js */

"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const leer = (archivo) => fs.readFileSync(path.join(__dirname, "..", archivo), "utf8");
const html = leer("detalle.html");
const css = leer("css/estilos.css");

function regla(selector, desde = 0) {
  const inicio = css.indexOf(`${selector} {`, desde);
  assert.ok(inicio >= 0, selector);
  return css.slice(inicio, css.indexOf("}", inicio));
}

test("«Detalles» es una tarjeta con el mismo estilo que la del ticket", () => {
  assert.match(html, /<section id="panel-datos" class="seccion detalle-datos tarjeta-datos" aria-label="Detalles del ticket">\s*<h2>Detalles<\/h2>/);
  const tarjeta = regla(".tarjeta-datos");
  const izquierda = regla(".tarjeta-ticket");
  for (const propiedad of ["border: 1px solid var(--color-borde);", "border-radius: var(--radio-medio);",
    "background: var(--color-superficie);", "box-shadow: var(--sombra-tarjeta);"]) {
    assert.ok(tarjeta.includes(propiedad), propiedad);
    assert.ok(izquierda.includes(propiedad), `la de la izquierda también: ${propiedad}`);
  }
  // Alineada arriba con la tarjeta del ticket (debajo de la barra de acciones).
  assert.match(regla(".detalle-lateral"), /margin-top: calc\(var\(--alto-control\) \+ var\(--espaciado-md\)\);/);
  assert.match(regla(".acciones-principales"), /margin-bottom: var\(--espaciado-md\);/);
});

test("cada dato en una fila: etiqueta tenue sin mayúsculas a la izquierda, valor a la derecha, línea fina entre filas", () => {
  const fila = regla(".detalle-datos-lista .dato");
  assert.match(fila, /display: flex;/);
  assert.match(fila, /justify-content: space-between;/);
  assert.match(regla(".detalle-datos-lista .dato + .dato"), /border-top: 1px solid var\(--color-borde\);/);
  const etiqueta = regla(".detalle-datos-lista dt");
  assert.match(etiqueta, /color: var\(--color-tenue\);/);
  assert.doesNotMatch(etiqueta, /text-transform/, "«Categoría», no «CATEGORÍA»");
  assert.match(regla(".detalle-datos-lista dd"), /text-align: right;/);
});

test("íconos de línea finos al lado de cada etiqueta, del mismo trazo que el menú", () => {
  const icono = regla(".dato-icono");
  assert.match(icono, /background: var\(--color-tenue\);/);
  assert.match(icono, /mask: var\(--icono-dato\) center \/ contain no-repeat;/);
  for (const nombre of ["categoria", "departamento", "persona", "calendario"]) {
    const r = regla(`.icono-${nombre}`);
    assert.match(r, /stroke-width='1\.8'/, `${nombre}: trazo 1.8 como .icono del menú`);
    assert.match(r, /fill='none'/);
  }
  assert.match(css, /\n\.icono \{[^}]*stroke-width: 1\.8;/, "los del menú también tienen trazo 1.8");
  assert.equal((html.match(/class="dato-icono icono-[a-z]+" aria-hidden="true"/g) || []).length, 6);
});

test("nombres largos se cortan con «…»", () => {
  const nombre = regla(".detalle-datos-lista dd.con-avatar");
  assert.match(nombre, /overflow: hidden;/);
  assert.match(nombre, /text-overflow: ellipsis;/);
  assert.match(nombre, /white-space: nowrap;/);
});

test("en pantallas angostas «Detalles» va justo debajo de la tarjeta del ticket, a todo el ancho", () => {
  const angosta = css.slice(css.indexOf("@media (max-width: 1100px) {\n  .detalle-layout {"));
  const bloque = angosta.slice(0, angosta.indexOf("\n}\n"));
  assert.match(bloque, /\.detalle-principal \{\s*display: contents;/);
  assert.match(bloque, /\.detalle-principal > \.acciones-principales,\s*\.detalle-principal > #panel-ticket \{\s*order: 1;/);
  assert.match(bloque, /\.detalle-lateral \{\s*order: 2;/);
  assert.match(bloque, /\.detalle-principal > :not\(\.acciones-principales, #panel-ticket\) \{\s*order: 3;/);
  assert.match(bloque, /grid-template-columns: minmax\(0, 1fr\);/);
  assert.match(bloque, /align-items: stretch;/, "sin scroll horizontal con un nombre largo");
});

test("al imprimir salen las fechas completas y no los íconos", () => {
  assert.match(regla(".fecha-completa"), /display: none;/, "en pantalla, solo la relativa");
  const impresion = css.slice(css.indexOf("@media print"));
  assert.match(impresion, /\.fecha-relativa,\s*\.dato-icono \{\s*display: none !important;/);
  assert.match(impresion, /\.fecha-completa \{\s*display: inline !important;/);
});

test("sin código inline (CSP) y colores solo con variables en la tarjeta", () => {
  assert.doesNotMatch(html, /\sstyle="/);
  assert.doesNotMatch(html, /\son[a-z]+="/);
  const inicio = css.indexOf("/* Panel derecho del detalle: «Detalles» en una tarjeta");
  const bloque = css.slice(inicio, css.indexOf("/* ---------- Listas de constantes", inicio))
    .replace(/url\("data:[^"]*"\)/g, "");
  assert.ok(bloque.length > 0);
  assert.doesNotMatch(bloque, /#[0-9a-fA-F]{3,6}\b|rgba?\(/);
});

/* ---------- detalle.js ---------- */

function nodo() {
  return {
    textContent: "", title: "", className: "", dataset: {}, children: [],
    replaceChildren(...hijos) { this.children = hijos; this.textContent = hijos.map((h) => h.textContent).join(""); },
  };
}

function cargar() {
  const sandbox = {
    console, Intl, Date, URLSearchParams,
    document: { getElementById: () => null, addEventListener() {}, createElement: () => nodo() },
    window: { location: { search: "" } },
    localStorage: { getItem: () => null, setItem() {}, removeItem() {} },
  };
  vm.createContext(sandbox);
  vm.runInContext(leer("js/auth.js"), sandbox);
  vm.runInContext(leer("js/detalle.js"), sandbox);
  return sandbox;
}

// 12/11/2026 15:00 en Costa Rica (UTC-6).
const AHORA = new Date("2026-11-12T21:00:00Z");

test("fechas relativas: momento, minutos, horas del mismo día, ayer con hora y fecha corta", () => {
  const { fechaRelativa } = cargar();
  assert.equal(fechaRelativa("2026-11-12T20:59:40Z", AHORA), "Hace un momento");
  assert.equal(fechaRelativa("2026-11-12T20:55:00Z", AHORA), "Hace 5 min");
  assert.equal(fechaRelativa("2026-11-12T20:00:30Z", AHORA), "Hace 59 min");
  assert.equal(fechaRelativa("2026-11-12T19:00:00Z", AHORA), "Hace 2 h");
  assert.equal(fechaRelativa("2026-11-12T06:30:00Z", AHORA), "Hace 14 h", "00:30 de hoy en Costa Rica");
  assert.equal(fechaRelativa("2026-11-11T17:15:00Z", AHORA), "Ayer, 11:15");
  assert.equal(fechaRelativa("2026-11-12T05:30:00Z", AHORA), "Ayer, 23:30", "en UTC ya es 12, en Costa Rica todavía 11");
  assert.equal(fechaRelativa("2026-11-10T15:14:02Z", AHORA), "10/11/2026");
  assert.equal(fechaRelativa("2026-11-12T21:05:00Z", AHORA), "Hace un momento", "un reloj adelantado no da negativos");
  assert.equal(fechaRelativa("no es fecha", AHORA), "—");
});

test("la fecha exacta queda en el title y en un span oculto que sale al imprimir", () => {
  const sandbox = cargar();
  const el = nodo();
  sandbox.pintarFecha(el, "2026-11-10T15:14:02Z");
  const exacta = sandbox.formatFecha("2026-11-10T15:14:02Z");
  assert.equal(el.title, exacta);
  assert.deepEqual(el.children.map((h) => h.className), ["fecha-relativa", "fecha-completa"]);
  assert.equal(el.children[1].textContent, exacta);
  assert.match(el.children[0].textContent, /^\d{2}\/\d{2}\/\d{4}$|^Hace |^Ayer, /);
});

test("Asignado y Solicitante: círculo de iniciales y el nombre completo al pasar el mouse", () => {
  const sandbox = cargar();
  const el = nodo();
  sandbox.pintarPersonaDato(el, "María Fernanda Rodríguez Villalobos");
  assert.equal(el.textContent, "María Fernanda Rodríguez Villalobos");
  assert.equal(el.title, "María Fernanda Rodríguez Villalobos");
  assert.match(el.className, /\bcon-avatar\b/);
  sandbox.pintarPersonaDato(el, "—");
  assert.equal(el.title, "", "sin nadie, sin tooltip");
  assert.doesNotMatch(el.className, /con-avatar/);
});

test("las fechas relativas se actualizan cada minuto con la página abierta", () => {
  assert.match(leer("js/detalle.js"), /setInterval\(\(\) => pintarFechasDetalle\(ticketActual\), 60000\)/);
});
