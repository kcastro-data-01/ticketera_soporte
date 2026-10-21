/* Ayuda (ayuda.html + ayuda.js): índice arriba y temas plegables.
   Ejecutar con: node --test frontend/tests/ayuda_ui.test.js */

"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const leer = (archivo) => fs.readFileSync(path.join(__dirname, "..", archivo), "utf8");
const html = leer("ayuda.html");

const TEMAS = [
  ["crear", "Crear un ticket"],
  ["seguimiento", "Seguimiento"],
  ["roles", "Roles y permisos"],
  ["asistente", "Asistente virtual"],
  ["correo", "Tickets por correo"],
  ["faq", "Preguntas frecuentes"],
];

test("el índice enlaza los seis temas en orden y cada tema es plegable", () => {
  const enlaces = [...html.matchAll(/<li><a href="#([a-z]+)">([^<]+)<\/a><\/li>/g)].map((m) => [m[1], m[2]]);
  assert.deepEqual(enlaces, TEMAS);
  const temas = [...html.matchAll(/<details class="ayuda-tema" id="([a-z]+)"[^>]*>\s*<summary>([^<]+)<\/summary>/g)].map((m) => [m[1], m[2]]);
  assert.deepEqual(temas, TEMAS);
  assert.match(html, /<details class="ayuda-tema" id="crear" open>/, "el primero empieza abierto");
});

test("el contenido de antes sigue estando, ahora dentro de su tema", () => {
  const tema = (id) => html.slice(html.indexOf(`id="${id}"`), html.indexOf("</details>", html.indexOf(`id="${id}"`)));
  assert.match(tema("crear"), /¿Qué es Ticketera\?[\s\S]*Funcionalidades principales[\s\S]*Flujos principales/);
  assert.match(tema("seguimiento"), /Estados de los tickets[\s\S]*Cómo leer el historial/);
  assert.match(tema("roles"), /Roles del sistema[\s\S]*<td>Administrar usuarios<\/td>/);
});

test("un enlace del índice abre su tema", () => {
  const temas = {};
  const doc = {
    getElementById: (id) => temas[id] || null,
    querySelectorAll: () => [],
  };
  for (const [id] of TEMAS) {
    temas[id] = { open: false, classList: { contains: (c) => c === "ayuda-tema" }, scrollIntoView() { this.visto = true; } };
  }
  const sandbox = { window: { location: { hash: "" } }, document: doc };
  vm.runInNewContext(leer("js/ayuda.js"), sandbox);
  sandbox.abrirTema("correo", doc);
  assert.equal(temas.correo.open, true);
  assert.equal(temas.correo.visto, true);
  assert.equal(sandbox.abrirTema("no-existe", doc), null);
});
