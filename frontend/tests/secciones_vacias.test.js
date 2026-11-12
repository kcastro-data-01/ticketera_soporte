/* Detalle del ticket: Adjuntos, Comentarios, Historial y Explicación IA
   compactos cuando están vacíos (una línea chica en lugar de cajas grandes)
   y el cuadro «Nuevo comentario» de 3 líneas que crece al escribir.
   Ejecutar con: node --test frontend/tests/secciones_vacias.test.js */

"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const leer = (archivo) => fs.readFileSync(path.join(__dirname, "..", archivo), "utf8");
const html = leer("detalle.html");
const css = leer("css/estilos.css");

function seccion(id) {
  const inicio = html.indexOf(`<section id="${id}"`);
  assert.ok(inicio >= 0, id);
  return html.slice(inicio, html.indexOf("</section>", inicio));
}

function regla(selector) {
  const inicio = css.indexOf(`${selector} {`);
  assert.ok(inicio >= 0, selector);
  return css.slice(inicio, css.indexOf("}", inicio));
}

test("Adjuntos: «Sin adjuntos» al lado del botón y los tipos en texto chico debajo", () => {
  const adj = seccion("seccion-adjuntos");
  const barra = adj.slice(adj.indexOf('<div class="adj-barra">'), adj.indexOf('id="adj-nota"'));
  assert.ok(barra.indexOf('id="adj-subir"') < barra.indexOf('id="adj-vacio"'), "la línea va después del botón, en la misma fila");
  assert.match(barra, /<span id="adj-vacio" class="linea-vacia" hidden>Sin adjuntos<\/span>/);
  assert.match(adj, /<p id="adj-nota" class="nota-chica"><\/p>/, "ya no es la nota azul");
  assert.match(regla(".adj-barra"), /display: flex;\s*flex-wrap: wrap;\s*align-items: center;/);
});

test("Comentarios: sin la nota azul del orden y el vacío es una línea chica", () => {
  const com = seccion("seccion-comentarios");
  assert.doesNotMatch(com, /más antiguo a más reciente/);
  assert.doesNotMatch(com, /class="nota"/);
});

test("Historial y Explicación IA: sin cajas alrededor del botón ni nota azul", () => {
  const hist = seccion("seccion-historial");
  assert.doesNotMatch(hist, /filtros formulario/, "el botón «Ver historial» sin recuadro");
  const ia = seccion("seccion-ia");
  assert.doesNotMatch(ia, /class="nota"/);
  assert.match(ia, /<p class="nota-chica">\s*Interpreta el ticket/);
});

test("CSS: el vacío de comentarios e historial es texto chico y tenue, sin borde punteado ni ícono", () => {
  const inicio = css.indexOf("/* ===== Detalle: secciones vacías compactas");
  const bloque = css.slice(inicio, css.indexOf("/* Nuevo ticket: archivos elegidos", inicio));
  assert.ok(bloque.length > 0);
  const linea = bloque.slice(bloque.indexOf(".linea-vacia,"), bloque.indexOf("}", bloque.indexOf(".linea-vacia,")));
  assert.match(linea, /#comentarios-estado\.vacio:not\(\[hidden\]\),\s*#historial-estado\.vacio:not\(\[hidden\]\) \{/);
  assert.match(linea, /border: 0;/);
  assert.match(linea, /background: transparent;/);
  assert.match(linea, /font-size: var\(--texto-sm\);/);
  assert.match(linea, /color: var\(--color-tenue\);/);
  assert.match(bloque, /#comentarios-estado\.vacio::before,\s*#historial-estado\.vacio::before \{\s*display: none;/);
  assert.match(regla(".nota-chica"), /color: var\(--color-tenue\);/);
  assert.match(regla(".nota-chica"), /overflow-wrap: anywhere;/, "en el celular el texto baja de línea");
  // Claro y oscuro por las variables: sin colores fijos en el bloque.
  assert.doesNotMatch(bloque, /#[0-9a-fA-F]{3,6}\b|rgba?\(/);
  // Las cajas grandes siguen para las demás pantallas (listado, usuarios).
  assert.match(regla(".estado.vacio"), /border: 1px dashed var\(--color-borde-fuerte\);/);
});

test("«Nuevo comentario» arranca con 3 líneas y se agranda al enfocarlo", () => {
  assert.match(seccion("seccion-comentarios"), /<textarea\s+id="contenido"\s+name="content"\s+rows="3"/);
  assert.match(regla(".campo #contenido"), /min-height: calc\(4\.5em \+ 0\.9rem \+ 2px\);/);
  assert.match(regla(".campo #contenido"), /line-height: 1\.5;/);
  assert.match(regla(".campo #contenido:focus"), /min-height: 130px;/);
});

test("sin código inline (CSP) en detalle.html", () => {
  assert.doesNotMatch(html, /\sstyle="/);
  assert.doesNotMatch(html, /\son[a-z]+="/);
  assert.doesNotMatch(html, /<script(?![^>]*\ssrc=)[^>]*>/);
});

function cargar(campo) {
  const sandbox = {
    console, Intl, Date, URLSearchParams,
    document: { getElementById: (id) => (id === "contenido" ? campo : null), addEventListener() {} },
    window: { location: { search: "" } },
    localStorage: { getItem: () => null, setItem() {}, removeItem() {} },
  };
  vm.createContext(sandbox);
  vm.runInContext(leer("js/auth.js"), sandbox);
  vm.runInContext(leer("js/detalle.js"), sandbox);
  return sandbox;
}

test("al escribir, el cuadro crece con el texto hasta 320 px; vacío vuelve al alto del CSS", () => {
  const campo = { value: "", scrollHeight: 0, style: { height: "" } };
  const sandbox = cargar(campo);

  campo.value = "Una línea";
  campo.scrollHeight = 130;
  sandbox.ajustarAltoComentario();
  assert.equal(campo.style.height, "132px");

  campo.value = "x\n".repeat(20);
  campo.scrollHeight = 500;
  sandbox.ajustarAltoComentario();
  assert.equal(campo.style.height, "320px", "con tope");

  campo.value = "";
  sandbox.ajustarAltoComentario();
  assert.equal(campo.style.height, "", "al enviar (o borrar todo) vuelve a 3 líneas");
});

test("el cuadro escucha «input» y se achica después de agregar el comentario", () => {
  const detalle = leer("js/detalle.js");
  assert.match(detalle, /elements\.contenido\.addEventListener\("input", ajustarAltoComentario\)/);
  assert.match(detalle, /elements\.contenido\.value = "";\s*ajustarAltoComentario\(\);/);
});
