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
  const enlaces = [...html.matchAll(/<li><a class="ayuda-tema-boton" href="#([a-z]+)">([^<]+)<\/a><\/li>/g)].map((m) => [m[1], m[2]]);
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
  assert.match(tema("areas"), /Soporte IT<\/strong>: computadoras, impresoras, programas/);
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

test("«Temas» es una cuadrícula de botones sin números: 5, 3 y 2 columnas", () => {
  const indice = html.slice(html.indexOf('<nav class="ayuda-indice"'), html.indexOf("</nav>", html.indexOf('<nav class="ayuda-indice"')));
  assert.match(indice, /<ul class="ayuda-temas">/);
  assert.doesNotMatch(indice, /<ol\b/, "sin lista numerada");
  assert.equal((indice.match(/class="ayuda-tema-boton"/g) || []).length, 10);
  const css = leer("css/estilos.css");
  assert.match(css, /\.ayuda-temas \{[^}]*display: grid;[^}]*grid-template-columns: repeat\(5, minmax\(0, 1fr\)\);[^}]*grid-auto-rows: 1fr;[^}]*list-style: none;/);
  assert.match(css, /@media \(max-width: 900px\) \{\s*\.ayuda-temas \{\s*grid-template-columns: repeat\(3, minmax\(0, 1fr\)\);/);
  assert.match(css, /@media \(max-width: 480px\) \{\s*\.ayuda-temas \{\s*grid-template-columns: repeat\(2, minmax\(0, 1fr\)\);/);
  // Como los botones secundarios: borde suave, fondo claro y se marca al pasar.
  const boton = css.slice(css.indexOf(".ayuda-tema-boton {"), css.indexOf("}", css.indexOf(".ayuda-tema-boton {")));
  assert.match(boton, /border: 1px solid var\(--color-borde-fuerte\);/);
  assert.match(boton, /background: var\(--color-superficie-alta\);/);
  assert.match(boton, /text-align: center;/);
  assert.match(boton, /overflow-wrap: normal;\s*word-break: normal;/, "corta solo entre palabras");
  assert.match(css, /\.ayuda-tema-boton:hover \{\s*background: var\(--color-primario-tenue\);\s*border-color: var\(--color-primario-suave\);/);
  assert.match(css, /\.ayuda-tema-boton:focus-visible \{/);
  assert.doesNotMatch(css, /\.ayuda-indice ol/);
});

test("ayuda.html sin código inline (CSP)", () => {
  const sinComentarios = html.replace(/<!--[\s\S]*?-->/g, "");
  for (const script of sinComentarios.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/g)) {
    assert.match(script[1], /\bsrc="/, "script con src");
    assert.equal(script[2].trim(), "", "script sin contenido");
  }
  assert.doesNotMatch(sinComentarios, /<style\b/);
  assert.doesNotMatch(sinComentarios, /\sstyle="/);
  assert.doesNotMatch(sinComentarios, /\son[a-z]+="/);
  assert.doesNotMatch(sinComentarios, /href="javascript:/);
});

test("tocar un tema baja hasta él y lo abre si está cerrado", () => {
  const temas = {};
  const doc = { getElementById: (id) => temas[id] || null, querySelectorAll: () => [] };
  for (const [id] of TEMAS) {
    temas[id] = { open: id === "crear", classList: { contains: (c) => c === "ayuda-tema" },
      scrollIntoView(opciones) { this.visto = opciones; } };
  }
  const reemplazos = [];
  const sandbox = { window: { location: { hash: "" }, history: { replaceState: (_e, _t, url) => reemplazos.push(url) } }, document: doc };
  vm.runInNewContext(leer("js/ayuda.js"), sandbox);
  const enlace = (id) => ({ getAttribute: () => `#${id}` });
  let prevenido = 0;
  const evento = { preventDefault: () => { prevenido += 1; } };

  sandbox.irATema(evento, enlace("faq"), doc);
  assert.equal(temas.faq.open, true, "se abre");
  assert.equal(temas.faq.visto.block, "start", "baja hasta él");
  assert.equal(prevenido, 1);
  assert.deepEqual(reemplazos, ["#faq"]);

  sandbox.irATema(evento, enlace("crear"), doc);
  assert.equal(temas.crear.open, true, "uno abierto sigue abierto");
  assert.ok(temas.crear.visto);

  assert.equal(sandbox.irATema(evento, enlace("no-existe"), doc), null);
  assert.equal(prevenido, 2, "un enlace que no es un tema no se toca");
});
