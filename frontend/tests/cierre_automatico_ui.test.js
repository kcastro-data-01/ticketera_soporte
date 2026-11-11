/* Cierre automático en el detalle (detalle.js: «Se cerrará automáticamente
   el … si no hay respuesta») y en el historial (auth.js: describirHistorial).
   Ejecutar con: node --test frontend/tests/cierre_automatico_ui.test.js */

"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const leer = (archivo) => fs.readFileSync(path.join(__dirname, "..", archivo), "utf8");

function cargar() {
  const nota = { id: "cierre-automatico", hidden: true, textContent: "" };
  const sandbox = {
    console, Intl, Date,
    document: { getElementById: (id) => (id === "cierre-automatico" ? nota : null), addEventListener() {} },
    window: { location: { search: "" } },
    localStorage: { getItem: () => null, setItem() {}, removeItem() {} },
    URLSearchParams,
  };
  vm.createContext(sandbox);
  vm.runInContext(leer("js/auth.js"), sandbox);
  vm.runInContext(leer("js/detalle.js"), sandbox);
  return { sandbox, nota };
}

test("en Resuelto muestra el día y la hora del cierre, en la hora de Costa Rica", () => {
  const { sandbox, nota } = cargar();
  // Martes 17 de noviembre de 2026, 16:00 en Costa Rica (22:00 UTC).
  sandbox.pintarCierreAutomatico({ state: "Resuelto", cierre_automatico_en: "2026-11-17T22:00:00+00:00" });
  assert.equal(nota.hidden, false);
  assert.match(nota.textContent, /^Se cerrará automáticamente el martes, 17 de noviembre a las 4:00\s?p\.\s?m\. si no hay respuesta\.$/);
});

test("fuera de Resuelto o sin la función no se muestra", () => {
  const { sandbox, nota } = cargar();
  sandbox.pintarCierreAutomatico({ state: "Resuelto", cierre_automatico_en: "2026-11-17T22:00:00+00:00" });
  sandbox.pintarCierreAutomatico({ state: "En proceso", cierre_automatico_en: null });
  assert.equal(nota.hidden, true);
  assert.equal(nota.textContent, "");
  sandbox.pintarCierreAutomatico({ state: "Resuelto", cierre_automatico_en: null });
  assert.equal(nota.hidden, true, "con CIERRE_AUTOMATICO apagada la API manda null");
  sandbox.pintarCierreAutomatico({ state: "Resuelto", cierre_automatico_en: "no es una fecha" });
  assert.equal(nota.hidden, true);
});

test("el historial dice «Cerrado automáticamente por falta de respuesta» y la reapertura", () => {
  const { sandbox } = cargar();
  assert.deepEqual(
    JSON.parse(JSON.stringify(sandbox.describirHistorial({ action: "Cierre automático", field: "state",
      old_value: "Resuelto", new_value: "Cerrado" }))),
    { accion: "Cerrado automáticamente por falta de respuesta", detalle: "Resuelto → Cerrado" });
  assert.deepEqual(
    JSON.parse(JSON.stringify(sandbox.describirHistorial({ action: "Reabierto por respuesta", field: "state",
      old_value: "Resuelto", new_value: "En proceso" }))),
    { accion: "Reabierto por respuesta del solicitante", detalle: "Resuelto → En proceso" });
});

test("detalle.html tiene la nota (sin estilos inline) y el CSS la pinta en claro y oscuro", () => {
  const html = leer("detalle.html");
  assert.match(html, /<p id="cierre-automatico" class="pasos-nota cierre-automatico" hidden><\/p>/);
  const css = leer("css/estilos.css");
  const regla = css.slice(css.indexOf(".cierre-automatico {"), css.indexOf("}", css.indexOf(".cierre-automatico {")));
  assert.match(regla, /var\(--color-vacio\)/);
  assert.match(regla, /var\(--color-vacio-fondo\)/);
  // Las dos variables existen en el tema claro y en el oscuro.
  assert.ok((css.match(/--color-vacio-fondo:/g) || []).length >= 2);
});

test("la ayuda explica el cierre automático", () => {
  const html = leer("ayuda.html");
  assert.match(html, /<h3>Cierre automático<\/h3>/);
  assert.match(html, /el domingo no cuenta/);
  assert.match(html, /Reabierto por respuesta del solicitante/);
  assert.match(html, /Cerrado automáticamente por falta de respuesta/);
});
