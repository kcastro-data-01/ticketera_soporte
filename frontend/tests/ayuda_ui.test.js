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
  ["lista", "La lista de tickets"],
  ["seguimiento", "Seguimiento"],
  ["areas", "Departamentos"],
  ["roles", "Roles y permisos"],
  ["adjuntos", "Adjuntos"],
  ["correo", "Tickets por correo"],
  ["avisos", "Avisos por correo"],
  ["asistente", "Asistente virtual"],
  ["faq", "Preguntas frecuentes"],
];

const tema = (id) => html.slice(html.indexOf(`id="${id}"`), html.indexOf("</details>", html.indexOf(`id="${id}"`)));
// Lo que se ve (sin comentarios ni etiquetas).
const visible = html.replace(/<!--[\s\S]*?-->/g, "").replace(/<[^>]+>/g, " ");

test("el índice enlaza los diez temas en orden y cada tema es plegable", () => {
  const enlaces = [...html.matchAll(/<li><a href="#([a-z]+)">([^<]+)<\/a><\/li>/g)].map((m) => [m[1], m[2]]);
  assert.deepEqual(enlaces, TEMAS);
  const temas = [...html.matchAll(/<details class="ayuda-tema" id="([a-z]+)"[^>]*>\s*<summary>([^<]+)<\/summary>/g)].map((m) => [m[1], m[2]]);
  assert.deepEqual(temas, TEMAS);
  assert.match(html, /<details class="ayuda-tema" id="crear" open>/, "el primero empieza abierto");
});

test("cada tema tiene lo suyo", () => {
  assert.match(tema("crear"), /¿Qué es la ticketera\?[\s\S]*Cómo crear un ticket/);
  assert.match(tema("seguimiento"), /Estados de los tickets[\s\S]*Cambiar el estado[\s\S]*Cómo leer el historial/);
  assert.match(tema("roles"), /Roles del sistema[\s\S]*<td>Administrar usuarios<\/td>/);
});

test("lo que ya no existe no aparece", () => {
  // La pantalla «Áreas de IT» y administrar áreas, la paginación, reabrir un
  // Cerrado, avanzar de a un paso, asignarle tickets a un Solicitante y los
  // roles que ya no existen.
  for (const viejo of [/Áreas de IT/, /[Áá]rea de IT/, /renombr\w+ (un |las )?áreas?/i, /Anterior|Siguiente|Página \d/,
    /reapertura/, /se reabre \(de Resuelto/, /de a un paso/, /los asignados a él/, /supervis/i, /Soporte técnico/,
    /\bcid\b|Graph|\bAPI\b|index\.html|crear\.html/]) {
    assert.doesNotMatch(visible, viejo, String(viejo));
  }
});

test("lo que funciona hoy está explicado", () => {
  assert.match(tema("areas"), /Soporte<\/strong>: computadoras, impresoras, programas/);
  assert.match(tema("areas"), /Redes e Infraestructura<\/strong>: internet, wifi, servidores, VPN/);
  assert.match(tema("areas"), /Ciberseguridad<\/strong>: accesos, contraseñas, cuentas, incidentes de seguridad/);
  assert.match(tema("areas"), /Programación<\/strong>: sistemas internos, Odoo, desarrollos y reportes/);
  assert.match(tema("areas"), /menos tickets abiertos/);
  assert.match(tema("areas"), /«Cambiar departamento»/);
  assert.match(tema("areas"), /Nadie los crea, renombra, desactiva ni borra, tampoco el Administrador/);
  assert.match(tema("roles"), /IT solo recibe tickets/);
  assert.match(tema("lista"), /todos los tickets que cumplen los filtros, sin páginas/);
  assert.match(tema("lista"), /Todos \/ Mis tickets[\s\S]*Tabla \/ Tablero[\s\S]*Compacta \/ Cómoda/);
  assert.match(tema("lista"), /<strong>Departamento<\/strong>: Todos, Sin departamento/);
  assert.match(tema("seguimiento"), /se puede saltar pasos/);
  assert.match(tema("seguimiento"), /solo se puede volver de <code>Resuelto<\/code> a <code>En proceso<\/code>/);
  assert.match(tema("seguimiento"), /<code>Cerrado<\/code> es un estado <strong>final<\/strong>: no se reabre/);
  assert.match(tema("correo"), /quien escribe el correo es el solicitante y quien lo recibe, el asignado/);
  assert.match(tema("correo"), /problemas de seguridad/);
  assert.match(tema("correo"), /IT solo recibe<\/strong>: si ese destinatario es Solicitante o no tiene cuenta, no se crea ticket/);
  assert.match(tema("correo"), /imágenes copiadas de una página de internet/);
  assert.match(tema("correo"), /imágenes de la firma/);
  assert.match(tema("adjuntos"), /jpg, png, pdf, docx, xlsx y txt, hasta 4 MB cada uno y 10 por ticket/);
  for (const aviso of ["Confirmación", "Asignación", "Comentarios", "Cambios de estado"]) {
    assert.match(tema("avisos"), new RegExp(`<strong>${aviso}</strong>`), aviso);
  }
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
