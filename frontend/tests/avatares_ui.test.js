/* Avatares con iniciales (auth.js): iniciales, color estable por persona
   y sin avatar cuando no hay una persona real.
   Ejecutar con: node --test frontend/tests/avatares_ui.test.js */

"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const authSource = fs.readFileSync(path.join(__dirname, "..", "js", "auth.js"), "utf8");

function cargar() {
  const sandbox = { console, localStorage: { getItem: () => null, setItem() {}, removeItem() {} } };
  vm.runInNewContext(authSource, sandbox, { filename: "auth.js" });
  return sandbox;
}

function nodo() {
  return { textContent: "", className: "comentario-autor", dataset: {} };
}

test("iniciales de una o dos palabras", () => {
  const { inicialesDe } = cargar();
  assert.equal(inicialesDe("Carlos Solano"), "CS");
  assert.equal(inicialesDe("  josé  solano mora "), "JS");
  assert.equal(inicialesDe("Laura"), "L");
});

test("la misma persona tiene siempre el mismo tono", () => {
  const { tonoAvatar } = cargar();
  assert.equal(tonoAvatar("José Solano"), tonoAvatar("José Solano"));
  assert.equal(tonoAvatar("José Solano"), tonoAvatar(" josé solano"));
  const tonos = new Set(["Laura Méndez", "José Solano", "Andrea Castillo", "Carlos Rojas", "Ana Pérez"].map(tonoAvatar));
  assert.ok(tonos.size > 1, "personas distintas no salen todas del mismo color");
  tonos.forEach((t) => assert.ok(t >= 0 && t < 6));
});

test("pintarPersona agrega el avatar y lo quita si no hay persona", () => {
  const { pintarPersona, tonoAvatar } = cargar();
  const el = nodo();
  pintarPersona(el, "Andrea Castillo");
  assert.equal(el.textContent, "Andrea Castillo");
  assert.equal(el.dataset.iniciales, "AC");
  assert.equal(el.className, `comentario-autor con-avatar tono-avatar-${tonoAvatar("Andrea Castillo")}`);

  pintarPersona(el, "Laura Méndez");
  assert.equal(el.className.match(/tono-avatar-/g).length, 1, "no acumula clases al repintar");

  for (const vacio of ["—", "Usuario #7", ""]) {
    pintarPersona(el, vacio);
    assert.equal(el.className, "comentario-autor");
    assert.equal(el.dataset.iniciales, undefined);
  }
});
