/* Diseño formal (solo CSS): tarjetas de resumen, tablas, encabezados y
   fondo de las páginas.
   Ejecutar con: node --test frontend/tests/diseno_formal.test.js */

"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const css = fs.readFileSync(path.join(__dirname, "..", "css", "estilos.css"), "utf8");

/* Cuerpo de la primera regla con exactamente ese selector. */
function regla(selector, desde = 0) {
  const inicio = css.indexOf(`\n${selector} {`, desde);
  assert.ok(inicio >= 0, selector);
  return css.slice(inicio, css.indexOf("\n}", inicio));
}

test("tarjetas de resumen: franja de 3 px con su color y número de 28 px en negrita", () => {
  assert.match(regla(".tarjeta-resumen"), /border-left: 3px solid var\(--color-primario\);/);
  const listado = regla(".resumen .tarjeta-resumen:has(.tarjeta-icono)");
  assert.match(listado, /border-left-color: var\(--tono-texto\);/, "cada tarjeta del listado con su tono");
  assert.doesNotMatch(listado, /border-left-width/, "la franja no se achica a 1 px");
  const numero = regla(".tarjeta-numero");
  assert.match(numero, /font-size: 28px;/);
  assert.match(numero, /font-weight: 700;/);
  assert.doesNotMatch(regla(".resumen .tarjeta-resumen:has(.tarjeta-icono) .tarjeta-numero"), /font-size/);
});

test("tablas: filas alternadas con el fondo neutro y encabezados formales", () => {
  assert.match(regla(".listado tbody tr:nth-child(even)"), /background: var\(--color-fondo-neutro\);/);
  assert.ok(css.indexOf("\n.listado tbody tr:nth-child(even) {") < css.indexOf("\n.listado tbody tr:hover {"), "el hover gana sobre la alternancia");
  const th = regla(".listado th");
  assert.match(th, /font-size: 12px;/);
  assert.match(th, /text-transform: uppercase;/);
  assert.match(th, /letter-spacing: 0\.04em;/);
  /* Modo oscuro: la misma variable, con su valor oscuro. */
  const oscuro = css.slice(css.indexOf(':root[data-tema="oscuro"] {'));
  assert.match(oscuro.slice(0, oscuro.indexOf("\n}")), /--color-fondo-neutro: #[0-9a-f]{6};/);
});

test("las tres tablas (listado, historial y usuarios) usan .listado", () => {
  for (const pagina of ["index.html", "historial.html", "usuarios.html"]) {
    const html = fs.readFileSync(path.join(__dirname, "..", pagina), "utf8");
    assert.match(html, /<table[^>]*class="listado"/, pagina);
  }
});

test("encabezado: título de 26 px en 600, subtítulo gris y línea de 1 px", () => {
  const cabecera = regla(".cabecera");
  assert.match(cabecera, /border-bottom: 1px solid var\(--color-borde\);/);
  const h1 = regla(".cabecera h1");
  assert.match(h1, /font-size: 26px;/);
  assert.match(h1, /font-weight: 600;/);
  assert.match(regla(".cabecera p"), /color: var\(--color-tenue\);/);
  for (const pagina of ["index.html", "crear.html", "detalle.html", "historial.html", "metricas.html", "usuarios.html", "ayuda.html", "cuenta.html"]) {
    const html = fs.readFileSync(path.join(__dirname, "..", pagina), "utf8");
    assert.match(html, /<header class="cabecera">[\s\S]*?<h1[^>]*>[^<]+<\/h1>\s*<p[^>]*>[^<]+<\/p>/, `${pagina}: título y subtítulo`);
  }
});
