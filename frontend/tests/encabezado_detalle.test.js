/* Encabezado del detalle del ticket (detalle.html + detalle.js + estilos.css):
   franja a todo el ancho con número y título; etiquetas de estado, prioridad,
   departamento y asignado; los avisos del ticket justo debajo; solicitante y
   fechas en una línea tenue; y el recorrido de estados al final.
   Ejecutar con: node --test frontend/tests/encabezado_detalle.test.js */

"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const leer = (archivo) => fs.readFileSync(path.join(__dirname, "..", archivo), "utf8");
const html = leer("detalle.html");
const css = leer("css/estilos.css");

const encabezado = html.slice(html.indexOf('<section id="encabezado-ticket"'), html.indexOf("</section>", html.indexOf('<section id="encabezado-ticket"')));

function regla(selector) {
  const inicio = css.indexOf(`${selector} {`);
  assert.ok(inicio >= 0, selector);
  return css.slice(inicio, css.indexOf("}", inicio));
}

test("el encabezado va arriba, a todo el ancho, antes de la descripción y el panel derecho", () => {
  assert.ok(encabezado.length > 0);
  const layout = html.indexOf('id="detalle-layout"');
  const enc = html.indexOf('id="encabezado-ticket"');
  assert.ok(layout < enc && enc < html.indexOf('class="detalle-principal"'));
  assert.ok(enc < html.indexOf('<aside class="detalle-lateral"'));
  assert.match(css, /\.detalle-layout > \.acciones-principales,\s*\.detalle-layout > \.encabezado-ticket \{\s*grid-column: 1 \/ -1;/);
});

test("orden: título, etiquetas, avisos, solicitante y fechas, recorrido de estados", () => {
  const orden = ['id="ver-id"', 'id="ver-title"', 'class="encabezado-ticket-etiquetas"', 'id="encabezado-avisos"',
    'class="encabezado-ticket-meta"', 'id="pasos-estado"', 'id="pasos-nota"'].map((marca) => {
    const i = encabezado.indexOf(marca);
    assert.ok(i >= 0, marca);
    return i;
  });
  assert.deepEqual(orden, [...orden].sort((a, b) => a - b));
});

test("las etiquetas: estado, prioridad, departamento y asignado", () => {
  const etiquetas = encabezado.slice(encabezado.indexOf("<ul"), encabezado.indexOf("</ul>"));
  const ids = [...etiquetas.matchAll(/id="(ver-[a-z]+)"/g)].map((m) => m[1]);
  assert.deepEqual(ids, ["ver-state", "ver-priority", "ver-area", "ver-assigned"]);
  assert.match(etiquetas, /etiqueta-dato-nombre">Departamento</);
  assert.match(etiquetas, /etiqueta-dato-nombre">Asignado</);
});

test("los avisos del ticket (cierre automático y Cerrado) están dentro del encabezado", () => {
  const avisos = encabezado.slice(encabezado.indexOf('id="encabezado-avisos"'), encabezado.indexOf('class="encabezado-ticket-meta"'));
  assert.match(avisos, /<p id="cierre-automatico" class="pasos-nota cierre-automatico" hidden><\/p>/);
  assert.match(avisos, /id="estado-final"/);
  assert.match(css, /\.encabezado-ticket-avisos:not\(:has\(> :not\(\[hidden\]\)\)\) \{\s*display: none;/, "sin avisos no ocupa lugar");
});

test("tercera línea: solicitante, creación y última actualización", () => {
  const meta = encabezado.slice(encabezado.indexOf('class="encabezado-ticket-meta"'), encabezado.indexOf("</p>", encabezado.indexOf('class="encabezado-ticket-meta"')));
  assert.match(meta, /Solicitante: <b id="ver-creator">/);
  assert.match(meta, /Creado: <b id="ver-created">/);
  assert.match(meta, /Actualizado: <b id="ver-updated">/);
  assert.match(regla(".encabezado-ticket-meta"), /font-size: var\(--texto-sm\);[\s\S]*color: var\(--color-tenue\);/);
});

test("sin código inline (CSP): ni style= ni onclick= ni <script> sin src", () => {
  assert.doesNotMatch(html, /\sstyle="/);
  assert.doesNotMatch(html, /\son[a-z]+="/);
  assert.doesNotMatch(html, /<script(?![^>]*\ssrc=)[^>]*>/);
});

test("estilo: colores solo con las variables de la app (claro y oscuro)", () => {
  const inicio = css.indexOf("/* ===== Detalle: encabezado del ticket");
  const bloque = css.slice(inicio, css.indexOf("/* Descripción: título chico en gris", inicio));
  assert.ok(bloque.length > 0);
  assert.doesNotMatch(bloque, /#[0-9a-fA-F]{3,6}\b|rgba?\(/, "sin colores fijos");
  assert.match(regla(".encabezado-ticket"), /background: var\(--color-superficie\);/);
  assert.match(regla(".encabezado-ticket"), /border-top: 3px solid var\(--color-primario\);/);
  assert.match(regla(".encabezado-ticket-titulo"), /color: var\(--color-titulo\);/);
});

test("en el celular las etiquetas bajan a varias líneas sin scroll horizontal", () => {
  assert.match(regla(".encabezado-ticket-etiquetas"), /flex-wrap: wrap;/);
  assert.match(regla(".encabezado-ticket-etiquetas > li"), /max-width: 100%;/);
  assert.match(regla(".etiqueta-dato-valor"), /overflow-wrap: anywhere;/);
  assert.match(regla(".encabezado-ticket-titulo"), /overflow-wrap: anywhere;/);
  assert.match(css, /@media \(max-width: 600px\) \{\s*\.encabezado-ticket \{/);
});

test("el esqueleto de carga cubre el encabezado y la descripción", () => {
  assert.match(leer("js/detalle.js"), /const panel = document\.getElementById\("detalle-layout"\);\s*if \(!silencioso\) marcarCargando\(panel, true\);/);
  assert.match(css, /#detalle-layout\.esqueleto-activo :is\(\.encabezado-ticket-titulo,/);
});

function cargar() {
  const sandbox = {
    console, Intl, Date, URLSearchParams,
    document: { getElementById: () => null, addEventListener() {} },
    window: { location: { search: "" } },
    localStorage: { getItem: () => null, setItem() {}, removeItem() {} },
  };
  vm.createContext(sandbox);
  vm.runInContext(leer("js/auth.js"), sandbox);
  vm.runInContext(leer("js/detalle.js"), sandbox);
  return sandbox;
}

test("«Asignado»: nombre con el círculo de iniciales; sin nadie, «Sin asignar» en gris", () => {
  const sandbox = cargar();
  const el = { className: "etiqueta-dato-valor", textContent: "", dataset: {} };
  sandbox.pintarAsignadoEncabezado(el, "Karla Sánchez");
  assert.equal(el.textContent, "Karla Sánchez");
  assert.match(el.className, /^etiqueta-dato-valor con-avatar tono-avatar-\d$/);
  assert.equal(el.dataset.iniciales, "KS");

  sandbox.pintarAsignadoEncabezado(el, "—");
  assert.equal(el.textContent, "Sin asignar");
  assert.equal(el.className, "etiqueta-dato-valor sin-asignar");
  assert.equal(el.dataset.iniciales, undefined);

  sandbox.pintarAsignadoEncabezado(el, "Andrés Mora");
  assert.match(el.className, /^etiqueta-dato-valor con-avatar tono-avatar-\d$/, "vuelve a tener avatar y deja de estar en gris");
});
