/* Barra de pasos del estado en el detalle (frontend/js/detalle.js).
   Ejecutar con: node --test frontend/tests/pasos_estado.test.js */

"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const leer = (archivo) => fs.readFileSync(path.join(__dirname, "..", archivo), "utf8");

function cargar() {
  const pasos = ["Nuevo", "En proceso", "Resuelto", "Cerrado"].map((paso) => ({
    dataset: { paso }, className: "", atributos: {},
    setAttribute(k, v) { this.atributos[k] = v; },
    removeAttribute(k) { delete this.atributos[k]; },
  }));
  const lista = { querySelectorAll: (sel) => (sel === "li" ? pasos : []) };
  const sandbox = {
    console,
    document: { getElementById: (id) => (id === "pasos-estado" ? lista : null), addEventListener() {} },
    window: { location: { search: "" } },
    localStorage: { getItem: () => null, setItem() {}, removeItem() {} },
    URLSearchParams,
  };
  vm.createContext(sandbox);
  vm.runInContext(leer("js/auth.js"), sandbox);
  vm.runInContext(leer("js/detalle.js"), sandbox);
  return { sandbox, pasos };
}

test("los estados anteriores quedan hechos y el actual marcado", () => {
  const { sandbox, pasos } = cargar();
  sandbox.pintarPasos("Resuelto");
  assert.deepEqual(pasos.map((p) => p.className), ["hecho", "hecho", "actual", ""]);
  assert.equal(pasos[2].atributos["aria-current"], "step");
  assert.equal(pasos[0].atributos["aria-current"], undefined);

  sandbox.pintarPasos("Nuevo");
  assert.deepEqual(pasos.map((p) => p.className), ["actual", "", "", ""]);
  assert.equal(pasos[2].atributos["aria-current"], undefined, "se quita al cambiar de estado");

  sandbox.pintarPasos("Cerrado");
  assert.deepEqual(pasos.map((p) => p.className), ["hecho", "hecho", "hecho", "actual"]);
});

test("detalle.html tiene los cuatro pasos en orden", () => {
  const html = leer("detalle.html");
  const pasos = [...html.matchAll(/<li data-paso="([^"]+)">/g)].map((m) => m[1]);
  assert.deepEqual(pasos, ["Nuevo", "En proceso", "Resuelto", "Cerrado"]);
});
