/* «Detalles» del detalle del ticket, modernizado sin adornos: misma
   estructura, lugar y orden; etiquetas chicas y tenues con mayúscula
   inicial, valores en peso medio, Departamento como pastilla y las fechas
   al final después de una línea fina. Sin tarjeta, íconos ni fechas relativas.
   Ejecutar con: node --test frontend/tests/detalles_sutil.test.js */

"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const leer = (archivo) => fs.readFileSync(path.join(__dirname, "..", archivo), "utf8");
const html = leer("detalle.html");
const css = leer("css/estilos.css");
const detalleJs = leer("js/detalle.js");

function regla(selector, desde = 0) {
  const inicio = css.indexOf(`${selector} {`, desde);
  assert.ok(inicio >= 0, selector);
  return css.slice(inicio, css.indexOf("}", inicio));
}

const inicioLateral = html.indexOf('<aside class="detalle-lateral"');
const lateral = html.slice(inicioLateral, html.indexOf("</aside>", inicioLateral));
const datos = lateral.slice(lateral.indexOf('<section id="panel-datos"'), lateral.indexOf("</section>"));

test("misma estructura, lugar y orden que el original; sin tarjeta, íconos ni fechas relativas", () => {
  assert.match(datos, /^<section id="panel-datos" class="seccion detalle-datos" aria-label="Detalles del ticket">\s*<h2>Detalles<\/h2>/);
  const filas = [...datos.matchAll(/<div class="dato[^"]*">\s*<dt>([^<]+)<\/dt>\s*<dd id="(ver-[a-z]+)">/g)].map((m) => [m[1], m[2]]);
  assert.deepEqual(filas, [
    ["Categoría", "ver-category"], ["Departamento", "ver-area"], ["Asignado a", "ver-assigned"],
    ["Solicitante", "ver-creator"], ["Fecha de creación", "ver-created"], ["Fecha de actualización", "ver-updated"],
  ]);
  for (const adorno of ["tarjeta-datos", "dato-icono", "fecha-relativa"]) {
    assert.ok(!html.includes(adorno) && !css.includes(adorno), adorno);
  }
  assert.doesNotMatch(detalleJs, /fechaRelativa|Hace \$\{/);
});

test("etiquetas con mayúscula inicial, más chicas y en gris tenue", () => {
  const dt = regla(".detalle-datos-lista dt");
  assert.doesNotMatch(dt, /text-transform|letter-spacing/, "«Categoría», no «CATEGORÍA»");
  assert.match(dt, /font-size: 0\.75rem;/);
  assert.match(dt, /font-weight: 400;/);
  assert.match(dt, /color: var\(--color-tenue\);/);
});

test("valores en peso medio y en el color de texto normal", () => {
  const dd = regla(".detalle-datos-lista dd");
  assert.match(dd, /font-weight: 500;/);
  assert.match(dd, /color: var\(--color-texto\);/);
  assert.match(dd, /overflow-wrap: anywhere;/, "en el celular un valor largo baja de línea");
});

test("espaciado parejo entre los datos, sin cajas ni bordes", () => {
  const lista = regla(".detalle-datos-lista");
  assert.match(lista, /gap: 0\.9rem;/);
  for (const selector of [".detalle-datos-lista", ".detalle-datos-lista .dato", ".detalle-datos-lista dt", ".detalle-datos-lista dd"]) {
    assert.doesNotMatch(regla(selector), /border|background|box-shadow|padding/, selector);
  }
  // La línea de las fechas deja el mismo espacio que hay entre los datos.
  assert.match(regla(".detalle-datos-lista .dato-fechas"), /padding-top: 0\.9rem;/);
});

test("Departamento: pastilla discreta con el mismo estilo que estado y prioridad", () => {
  const pastilla = regla(".detalle-datos-lista #ver-area");
  const badge = regla(".badge,\n.badge-estado,\n.badge-prioridad");
  for (const propiedad of ["padding: 0.1rem 0.45rem;", "border: 1px solid transparent;", "border-radius: 3px;",
    "font-size: 0.72rem;", "font-weight: 600;", "line-height: 1.4;"]) {
    assert.ok(badge.includes(propiedad), `badge: ${propiedad}`);
    assert.ok(pastilla.includes(propiedad), `departamento: ${propiedad}`);
  }
  // Gris neutro, como «Baja» o «Cerrado» (claro y oscuro por las variables).
  assert.match(pastilla, /background: var\(--etiqueta-gris-fondo\);/);
  assert.match(pastilla, /color: var\(--etiqueta-gris-texto\);/);
  assert.match(pastilla, /max-width: 100%;/);
  const impresion = css.slice(css.indexOf("@media print"));
  assert.match(impresion, /\.badge,\s*\.detalle-datos-lista #ver-area \{\s*border: 1px solid currentColor !important;/);
});

test("Creado y Actualizado al final, separados del resto por una línea muy fina", () => {
  assert.match(datos, /<div class="dato dato-fechas">\s*<dt>Fecha de creación<\/dt>/);
  assert.equal((datos.match(/dato-fechas/g) || []).length, 1, "una sola línea, arriba de las dos fechas");
  assert.ok(datos.indexOf("dato-fechas") > datos.indexOf('id="ver-creator"'));
  assert.match(regla(".detalle-datos-lista .dato-fechas"), /border-top: 1px solid var\(--color-borde\);/);
});

test("Asignado y Solicitante siguen con su círculo de iniciales; sin código inline", () => {
  assert.match(detalleJs, /pintarPersona\(elements\.ver\.assigned, nombreAsignado\(ticket\)\);/);
  assert.match(detalleJs, /pintarPersona\(elements\.ver\.creator, nombreSolicitante\(ticket\)\);/);
  assert.doesNotMatch(html, /\sstyle="|\son[a-z]+="/);
});
