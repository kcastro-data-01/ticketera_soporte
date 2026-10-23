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

test("tarjetas de métricas: franja de 3 px con su color y número de 28 px en negrita", () => {
  assert.match(regla(".tarjeta-resumen"), /border-left: 3px solid var\(--color-primario\);/);
  const numero = regla(".tarjeta-numero");
  assert.match(numero, /font-size: 28px;/);
  assert.match(numero, /font-weight: 700;/);
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

test("fondo: puntos de 1 px cada 20 px con el color de borde, muy suaves", () => {
  const body = regla("body");
  assert.match(body, /background-color: var\(--color-fondo\);/);
  assert.match(body, /background-image: radial-gradient\(\s*circle,\s*color-mix\(in srgb, var\(--color-borde\) 55%, transparent\) 0\.5px,\s*transparent 1px\s*\);/);
  assert.match(body, /background-size: 20px 20px;/);
  /* Solo en el fondo general: ningún otro radial-gradient en la hoja. */
  assert.equal(css.match(/radial-gradient/g).length, 1);
  /* Tarjetas, tablas y el chat tapan el patrón con su propio fondo. */
  assert.match(regla(".tarjeta-resumen"), /background: var\(--color-superficie-alta\);/);
  assert.match(regla(".listado"), /background: var\(--color-superficie-alta\);/);
  assert.match(regla(".chat-panel"), /background: var\(--color-superficie\);/);
  /* Modo oscuro: el mismo patrón con el borde oscuro (misma variable). */
  const oscuro = css.slice(css.indexOf(':root[data-tema="oscuro"] {'));
  assert.match(oscuro.slice(0, oscuro.indexOf("\n}")), /--color-borde: #[0-9a-f]{6};/);
});

const detalleHtml = fs.readFileSync(path.join(__dirname, "..", "detalle.html"), "utf8");

test("detalle: la descripción con título y en un recuadro neutro de lectura cómoda", () => {
  assert.match(detalleHtml, /<h3 class="tarjeta-ticket-subtitulo">Descripción<\/h3>\s*<p id="ver-description"/);
  const recuadro = regla(".tarjeta-ticket-descripcion");
  assert.match(recuadro, /background: var\(--color-fondo-neutro\);/);
  assert.match(recuadro, /border: 1px solid var\(--color-borde\);/);
  assert.match(recuadro, /line-height: 1\.7;/);
  assert.match(recuadro, /max-width: 72ch;/);
  assert.match(recuadro, /min-height: 3rem;/, "una descripción corta igual se ve");
});

test("detalle: «Detalles» arriba del panel derecho, fijo al bajar y debajo en pantallas angostas", () => {
  const inicio = detalleHtml.indexOf('<aside class="detalle-lateral"');
  const lateral = detalleHtml.slice(inicio, detalleHtml.indexOf("</aside>", inicio));
  const secciones = [...lateral.matchAll(/<section[^>]*aria-label="([^"]+)"/g)].map((m) => m[1]);
  assert.deepEqual(secciones, ["Detalles del ticket", "Asignación del ticket", "Cambio de estado del ticket"]);
  const datos = [...lateral.matchAll(/<dt>([^<]+)<\/dt>\s*<dd id="(ver-[a-z]+)">/g)].map((m) => [m[1], m[2]]);
  assert.deepEqual(datos, [
    ["Categoría", "ver-category"], ["Asignado a", "ver-assigned"], ["Solicitante", "ver-creator"],
    ["Fecha de creación", "ver-created"], ["Fecha de actualización", "ver-updated"],
  ]);
  const tarjeta = detalleHtml.slice(detalleHtml.indexOf('id="panel-ticket"'), detalleHtml.indexOf("</section>", detalleHtml.indexOf('id="panel-ticket"')));
  assert.doesNotMatch(tarjeta, /<dl/, "la grilla ya no está en la tarjeta");
  assert.match(regla(".detalle-datos-lista"), /flex-direction: column;/);
  assert.match(regla(".detalle-lateral"), /position: sticky;/);
  assert.match(css, /@media \(max-width: 1100px\) \{\s*\.detalle-layout \{\s*grid-template-columns: minmax\(0, 1fr\);/);
  const impresion = css.slice(css.indexOf("@media print"));
  assert.match(impresion, /\.detalle-lateral > \.seccion:not\(#panel-datos\),/, "al imprimir se ven los datos, no las acciones");
});
