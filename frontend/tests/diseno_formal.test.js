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
