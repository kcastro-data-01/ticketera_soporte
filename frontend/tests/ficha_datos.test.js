/* «Detalles» del detalle del ticket como ficha agrupada: un recuadro sin
   sombra, tres bloques (Clasificación, Personas y Fechas) y una fila por
   dato con la etiqueta a la izquierda y el valor a la derecha.
   Ejecutar con: node --test frontend/tests/ficha_datos.test.js */

"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const leer = (archivo) => fs.readFileSync(path.join(__dirname, "..", archivo), "utf8");
const html = leer("detalle.html");
const css = leer("css/estilos.css");

function regla(selector) {
  const inicio = css.indexOf(`${selector} {`);
  assert.ok(inicio >= 0, selector);
  return css.slice(inicio, css.indexOf("}", inicio));
}

const inicioDatos = html.indexOf('<section id="panel-datos"');
const datos = html.slice(inicioDatos, html.indexOf("</section>", inicioDatos));

test("«Detalles» en un recuadro casi blanco, borde fino, esquinas de 8 px y sin sombra", () => {
  assert.match(datos, /<h2>Detalles<\/h2>\s*<div class="ficha-datos">/);
  const recuadro = regla(".ficha-datos");
  assert.match(recuadro, /background: var\(--color-superficie\);/);
  assert.match(recuadro, /border: 1px solid var\(--color-borde\);/);
  assert.match(recuadro, /border-radius: var\(--radio-ventana\);/);
  assert.match(css, /--radio-ventana: 8px;/);
  assert.doesNotMatch(recuadro, /box-shadow/);
});

test("tres bloques con su título chico en mayúsculas, gris tenue y letras separadas", () => {
  const grupos = [...datos.matchAll(/<div class="ficha-grupo" role="group" aria-labelledby="(ficha-[a-z]+)">\s*<h3 id="\1" class="ficha-titulo">([^<]+)<\/h3>([\s\S]*?)<\/dl>/g)]
    .map((m) => [m[2], [...m[3].matchAll(/<dt>([^<]+)<\/dt>\s*<dd id="(ver-[a-z]+)">/g)].map((f) => [f[1], f[2]])]);
  assert.deepEqual(grupos, [
    ["Clasificación", [["Categoría", "ver-category"], ["Departamento", "ver-area"]]],
    ["Personas", [["Asignado a", "ver-assigned"], ["Solicitante", "ver-creator"]]],
    ["Fechas", [["Creado", "ver-created"], ["Actualizado", "ver-updated"]]],
  ]);
  const titulo = regla(".ficha-titulo");
  assert.match(titulo, /text-transform: uppercase;/, "en el HTML con mayúscula inicial; el lector de pantalla no deletrea");
  assert.match(titulo, /letter-spacing: 0\.08em;/);
  assert.match(titulo, /color: var\(--color-tenue\);/);
  assert.match(titulo, /font-size: 0\.7rem;/);
});

test("cada dato en una fila: etiqueta a la izquierda, valor a la derecha en negrita media", () => {
  const fila = regla(".detalle-datos-lista .dato");
  assert.match(fila, /display: flex;/);
  assert.match(fila, /justify-content: space-between;/);
  const dt = regla(".detalle-datos-lista dt");
  assert.doesNotMatch(dt, /text-transform/, "«Categoría», no «CATEGORÍA»");
  assert.match(dt, /font-size: var\(--texto-sm\);/);
  assert.match(dt, /color: var\(--color-tenue\);/);
  const dd = regla(".detalle-datos-lista dd");
  assert.match(dd, /text-align: right;/);
  assert.match(dd, /font-weight: 500;/);
  assert.match(dd, /color: var\(--color-texto\);/);
});

test("línea muy fina entre filas, sin línea en la última de cada bloque", () => {
  assert.match(regla(".detalle-datos-lista .dato"), /border-bottom: 1px solid var\(--color-borde\);/);
  assert.match(regla(".detalle-datos-lista .dato:last-child"), /border-bottom: 0;/);
  // Cada bloque tiene su propia lista, así que «la última» es la de cada bloque.
  assert.equal((datos.match(/<dl class="detalle-datos-lista">/g) || []).length, 3);
});

test("nombres largos cortados con «…»", () => {
  const nombre = regla(".detalle-datos-lista dd.con-avatar");
  assert.match(nombre, /overflow: hidden;/);
  assert.match(nombre, /text-overflow: ellipsis;/);
  assert.match(nombre, /white-space: nowrap;/);
});

test("sin íconos, fechas relativas, sombras ni código inline; Asignación y Cambiar departamento debajo", () => {
  const bloque = css.slice(css.indexOf("/* Panel derecho del detalle: «Detalles» como ficha agrupada."),
    css.indexOf("/* ---------- Listas de constantes"));
  assert.ok(bloque.length > 0);
  assert.doesNotMatch(bloque, /box-shadow|mask|url\(/);
  assert.doesNotMatch(bloque, /#[0-9a-fA-F]{3,6}\b|rgba?\(/, "colores solo con variables (claro y oscuro)");
  assert.doesNotMatch(leer("js/detalle.js"), /fechaRelativa|Hace \$\{/);
  assert.doesNotMatch(html, /\sstyle="|\son[a-z]+="/);
  const lateral = html.slice(html.indexOf('<aside class="detalle-lateral"'));
  const orden = ['id="panel-datos"', 'id="seccion-asignacion"', 'id="seccion-area"'].map((m) => lateral.indexOf(m));
  assert.ok(orden.every((i) => i >= 0) && orden[0] < orden[1] && orden[1] < orden[2]);
});

test("celular: la ficha va debajo de la descripción, a todo el ancho y sin scroll horizontal", () => {
  const angosta = css.slice(css.indexOf("@media (max-width: 1100px) {\n  .detalle-layout {"));
  const bloque = angosta.slice(0, angosta.indexOf("\n}\n"));
  assert.match(bloque, /\.detalle-principal \{\s*display: contents;/);
  assert.match(bloque, /\.detalle-principal > \.acciones-principales,\s*\.detalle-principal > #panel-ticket \{\s*order: 1;/);
  assert.match(bloque, /\.detalle-lateral \{\s*order: 2;\s*min-width: 0;/);
  assert.match(bloque, /align-items: stretch;/);
});

test("al imprimir salen todos los datos (sin el recuadro doble)", () => {
  const impresion = css.slice(css.indexOf("@media print"));
  assert.match(impresion, /\.detalle-lateral > \.seccion:not\(#panel-datos\),/, "solo se ocultan las acciones");
  assert.match(impresion, /#panel-datos \.ficha-datos \{\s*padding: 0;\s*border: 0;/);
  assert.doesNotMatch(impresion, /ficha-grupo[^{]*\{[^}]*display: none/);
});

test("el nombre completo de Asignado y Solicitante queda al pasar el mouse", () => {
  const sandbox = {
    console, Intl, Date, URLSearchParams,
    document: { getElementById: () => null, addEventListener() {} },
    window: { location: { search: "" } },
    localStorage: { getItem: () => null, setItem() {}, removeItem() {} },
  };
  vm.createContext(sandbox);
  vm.runInContext(leer("js/auth.js"), sandbox);
  vm.runInContext(leer("js/detalle.js"), sandbox);
  const el = { textContent: "", title: "", className: "", dataset: {} };
  sandbox.pintarPersonaFicha(el, "María Fernanda Rodríguez Villalobos");
  assert.equal(el.title, "María Fernanda Rodríguez Villalobos");
  assert.match(el.className, /\bcon-avatar\b/, "con su círculo de iniciales");
  sandbox.pintarPersonaFicha(el, "—");
  assert.equal(el.title, "");
});
