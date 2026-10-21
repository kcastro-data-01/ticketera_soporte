/* Versión para imprimir un ticket (detalle.js + estilos.css).
   Ejecutar con: node --test frontend/tests/impresion_ui.test.js */

"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const leer = (archivo) => fs.readFileSync(path.join(__dirname, "..", archivo), "utf8");

function cargar(tema) {
  const atributos = {};
  const fecha = { textContent: "" };
  const impresiones = [];
  const sandbox = {
    console,
    document: {
      documentElement: {
        getAttribute: (k) => atributos[k] ?? null,
        setAttribute: (k, v) => { atributos[k] = v; },
        removeAttribute: (k) => { delete atributos[k]; },
      },
      getElementById: (id) => (id === "impresion-fecha" ? fecha : null),
      addEventListener() {},
    },
    window: { location: { search: "" }, print: () => impresiones.push(true) },
    localStorage: { getItem: () => null, setItem() {}, removeItem() {} },
    URLSearchParams, Date,
  };
  vm.createContext(sandbox);
  vm.runInContext(leer("js/auth.js"), sandbox);
  vm.runInContext(leer("js/detalle.js"), sandbox);
  /* auth.js ya aplicó el tema guardado; se fija el de la prueba. */
  if (tema) atributos["data-tema"] = tema;
  return { sandbox, atributos, fecha, impresiones };
}

test("el botón Imprimir abre el diálogo del navegador", () => {
  const { sandbox, impresiones } = cargar();
  sandbox.imprimirTicket();
  assert.equal(impresiones.length, 1);
  assert.match(leer("detalle.html"), /<button type="button" id="imprimir" class="secundario">Imprimir<\/button>/);
});

test("al imprimir en modo oscuro pasa a claro y después vuelve", () => {
  const { sandbox, atributos, fecha } = cargar("oscuro");
  sandbox.prepararImpresion();
  assert.equal(atributos["data-tema"], undefined, "la hoja sale en negro sobre blanco");
  assert.match(fecha.textContent, /^Impreso el \d{2}\/\d{2}\/\d{4}/);
  sandbox.terminarImpresion();
  assert.equal(atributos["data-tema"], "oscuro");
});

test("la hoja impresa no tiene menú, botones, formularios ni el asistente", () => {
  const css = leer("css/estilos.css");
  const bloque = css.slice(css.indexOf("@media print"));
  for (const sel of [".barra-lateral", ".cabecera", ".acciones-principales", ".detalle-lateral", "#form-comentario", ".chat-asistente", "button"]) {
    assert.ok(bloque.includes(sel), sel);
  }
  assert.match(bloque, /\.impresion-cabecera \{\s*display: flex;/);
  assert.match(leer("detalle.html"), /<div class="impresion-cabecera" aria-hidden="true">[\s\S]*?American Data Networks/);
});
