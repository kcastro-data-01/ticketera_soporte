/* Ruta de navegación arriba del título (detalle y nuevo ticket).
   Ejecutar con: node --test frontend/tests/migas_ui.test.js */

"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const leer = (archivo) => fs.readFileSync(path.join(__dirname, "..", archivo), "utf8");

function auth(rol) {
  const inicio = { textContent: "Tickets" };
  const sandbox = {
    console,
    localStorage: { getItem: (k) => (k === "user" ? JSON.stringify({ name: "Ana", role: rol }) : null), setItem() {}, removeItem() {} },
  };
  vm.runInNewContext(leer("js/auth.js"), sandbox);
  sandbox.pintarMigas({ querySelector: (sel) => (sel === ".migas-inicio" ? inicio : null) });
  return inicio.textContent;
}

test("detalle y nuevo ticket muestran «Tickets › …» arriba del título", () => {
  const detalle = leer("detalle.html");
  assert.match(detalle, /<nav class="migas" aria-label="Ruta de navegación">[\s\S]*?<a href="index\.html" class="migas-inicio">Tickets<\/a>[\s\S]*?<li aria-current="page" id="migas-actual">Ticket<\/li>[\s\S]*?<h1>Detalle del ticket<\/h1>/);
  assert.match(leer("crear.html"), /class="migas-inicio">Tickets<\/a><\/li>\s*<li aria-current="page">Nuevo ticket<\/li>/);
  assert.match(leer("js/detalle.js"), /migaActual\.textContent = `Ticket #\$\{ticketId\}`/);
});

test("para el Solicitante el primer paso es «Mis solicitudes»", () => {
  assert.equal(auth("Solicitante"), "Mis solicitudes");
  assert.equal(auth("Técnico"), "Tickets");
});
