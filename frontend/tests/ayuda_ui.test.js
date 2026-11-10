/* Ayuda (ayuda.html + ayuda.js): «Temas» como pestañas y solo el tema
   elegido debajo, sin títulos desplegables.
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

const tema = (id) => html.slice(html.indexOf(`<section class="ayuda-tema" id="tema-${id}"`), html.indexOf("</section>", html.indexOf(`<section class="ayuda-tema" id="tema-${id}"`)));
// Lo que se ve (sin comentarios ni etiquetas).
const visible = html.replace(/<!--[\s\S]*?-->/g, "").replace(/<[^>]+>/g, " ");

test("«Temas» son diez pestañas en orden, cada una con su panel; sin títulos desplegables", () => {
  const indice = html.slice(html.indexOf('<nav class="ayuda-indice"'), html.indexOf("</nav>", html.indexOf('<nav class="ayuda-indice"')));
  assert.match(indice, /<h2 id="ayuda-temas-titulo">Temas<\/h2>\s*<div class="ayuda-temas" role="tablist" aria-labelledby="ayuda-temas-titulo">/);
  const pestanas = [...indice.matchAll(/<button type="button" role="tab" class="ayuda-tema-boton" id="pestana-([a-z]+)" data-tema="([a-z]+)" aria-controls="tema-([a-z]+)" aria-selected="(true|false)"( tabindex="-1")?>([^<]+)<\/button>/g)]
    .map((m) => [m[1], m[2], m[3], m[4], m[5], m[6]]);
  assert.deepEqual(pestanas.map((m) => [m[0], m[5]]), TEMAS);
  pestanas.forEach((m) => assert.ok(m[0] === m[1] && m[1] === m[2], "cada pestaña controla su tema"));
  assert.deepEqual(pestanas.map((m) => m[3]), TEMAS.map(([id]) => String(id === "crear")), "al entrar: «Crear un ticket»");
  assert.deepEqual(pestanas.map((m) => Boolean(m[4])), TEMAS.map(([id]) => id !== "crear"), "solo la elegida en el orden de tabulación");
  for (const [id] of TEMAS) {
    assert.doesNotMatch(html, new RegExp(`id="${id}"`), `ningún elemento se llama «${id}»: #${id} no hace saltar la página`);
  }
  assert.doesNotMatch(indice, /<li\b|<a\b|<ol\b/, "botones directos dentro del tablist");

  const paneles = [...html.matchAll(/<section class="ayuda-tema" id="tema-([a-z]+)" role="tabpanel" aria-labelledby="pestana-\1" tabindex="0"( hidden)?>\s*<div class="ayuda-cuerpo">/g)];
  assert.deepEqual(paneles.map((m) => m[1]), TEMAS.map(([id]) => id));
  assert.deepEqual(paneles.map((m) => Boolean(m[2])), TEMAS.map(([id]) => id !== "crear"), "los demás empiezan ocultos");
  assert.doesNotMatch(html, /<details\b|<summary\b/, "sin títulos desplegables");
  const contenido = html.slice(html.indexOf('<section class="ayuda-contenido">'), html.indexOf("</main>"));
  for (const [, titulo] of TEMAS) {
    assert.equal(contenido.split(`>${titulo}<`).length - 1, 1, `«${titulo}» una sola vez (en su pestaña)`);
  }
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

test("«Temas» es una cuadrícula de pestañas sin números: 5, 3 y 2 columnas (celular)", () => {
  const indice = html.slice(html.indexOf('<nav class="ayuda-indice"'), html.indexOf("</nav>", html.indexOf('<nav class="ayuda-indice"')));
  assert.doesNotMatch(indice, /<ol\b/, "sin lista numerada");
  assert.equal((indice.match(/class="ayuda-tema-boton"/g) || []).length, 10);
  const css = leer("css/estilos.css");
  assert.match(css, /\.ayuda-temas \{[^}]*display: grid;[^}]*grid-template-columns: repeat\(5, minmax\(0, 1fr\)\);[^}]*grid-auto-rows: 1fr;[^}]*list-style: none;/);
  assert.match(css, /@media \(max-width: 900px\) \{\s*\.ayuda-temas \{\s*grid-template-columns: repeat\(3, minmax\(0, 1fr\)\);/);
  assert.match(css, /@media \(max-width: 600px\) \{\s*\.ayuda-temas \{\s*grid-template-columns: repeat\(2, minmax\(0, 1fr\)\);/);
  // Como los botones secundarios: borde suave, fondo claro y se marca al pasar.
  const boton = css.slice(css.indexOf(".ayuda-tema-boton {"), css.indexOf("}", css.indexOf(".ayuda-tema-boton {")));
  assert.match(boton, /border: 1px solid var\(--color-borde-fuerte\);/);
  assert.match(boton, /background: var\(--color-superficie-alta\);/);
  assert.match(boton, /text-align: center;/);
  assert.match(boton, /overflow-wrap: normal;\s*word-break: normal;/, "corta solo entre palabras");
  assert.match(css, /\.ayuda-tema-boton:hover,\n\.ayuda-tema-boton:active \{\s*background: var\(--color-primario-tenue\);\s*border-color: var\(--color-primario-suave\);/);
  // La elegida, como la selección del resto de la app («Tabla / Tablero»).
  assert.match(css, /\.vista-tabs \.vista-tab\.activa \{\s*background: var\(--color-primario\);\s*color: var\(--color-texto-inverso\);/);
  assert.match(css, /\.ayuda-tema-boton\[aria-selected="true"\],\n\.ayuda-tema-boton\[aria-selected="true"\]:hover,\n\.ayuda-tema-boton\[aria-selected="true"\]:active \{\s*background: var\(--color-primario\);\s*border-color: var\(--color-primario\);\s*color: var\(--color-texto-inverso\);/);
  // El tema: directo, sin flecha ni título que se abra o cierre.
  assert.match(css, /\.ayuda-tema\[hidden\] \{\s*display: none;/);
  assert.match(css, /\.ayuda-tema:focus-visible \{/);
  assert.doesNotMatch(css, /\.ayuda-tema(\[open\])? > summary|\.ayuda-temas li/);
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

// --- ayuda.js con un DOM de mentira ------------------------------------------------

function montar(hash = "") {
  const paneles = {};
  const oyentes = {};
  let enfocada = null;
  const pestanas = TEMAS.map(([id]) => {
    const atributos = { "data-tema": id, "aria-controls": `tema-${id}`, "aria-selected": String(id === "crear") };
    const eventos = {};
    return {
      atributos, eventos, tabIndex: id === "crear" ? 0 : -1,
      getAttribute: (nombre) => atributos[nombre],
      setAttribute(nombre, valor) { atributos[nombre] = valor; },
      addEventListener(tipo, fn) { eventos[tipo] = fn; },
      focus() { enfocada = this; },
    };
  });
  for (const [id] of TEMAS) paneles[id] = { hidden: id !== "crear" };
  const doc = {
    querySelectorAll: (sel) => (sel === '.ayuda-temas [role="tab"]' ? pestanas : []),
    getElementById: (id) => (id.startsWith("tema-") ? paneles[id.slice(5)] : null) || null,
  };
  const reemplazos = [];
  const window = {
    location: { hash },
    history: { replaceState: (_e, _t, url) => { reemplazos.push(url); } },
    addEventListener: (tipo, fn) => { oyentes[tipo] = fn; },
  };
  const sandbox = { window, document: doc };
  vm.runInNewContext(leer("js/ayuda.js"), sandbox);
  const abierto = () => TEMAS.map(([id]) => id).filter((id) => !paneles[id].hidden);
  const elegida = () => pestanas.filter((p) => p.atributos["aria-selected"] === "true").map((p) => p.atributos["data-tema"]);
  const pestana = (id) => pestanas.find((p) => p.atributos["data-tema"] === id);
  return { sandbox, doc, window, paneles, pestanas, pestana, reemplazos, oyentes, abierto, elegida, enfocada: () => enfocada };
}

test("al entrar se ve «Crear un ticket»; con #tema en la dirección, ese tema", () => {
  const sin = montar("");
  sin.sandbox.iniciarAyuda(sin.doc);
  assert.deepEqual(sin.abierto(), ["crear"]);
  assert.deepEqual(sin.elegida(), ["crear"]);
  assert.deepEqual(sin.reemplazos, [], "entrar no cambia la dirección");

  const correo = montar("#correo");
  correo.sandbox.iniciarAyuda(correo.doc);
  assert.deepEqual(correo.abierto(), ["correo"]);
  assert.deepEqual(correo.elegida(), ["correo"]);
  assert.equal(correo.pestana("correo").tabIndex, 0);
  assert.equal(correo.pestana("crear").tabIndex, -1);

  const raro = montar("#no-existe");
  raro.sandbox.iniciarAyuda(raro.doc);
  assert.deepEqual(raro.abierto(), ["crear"], "un tema que no existe abre el inicial");
});

test("tocar una pestaña muestra solo ese tema, la marca y actualiza la dirección", () => {
  const m = montar("");
  m.sandbox.iniciarAyuda(m.doc);
  m.pestana("faq").eventos.click();
  assert.deepEqual(m.abierto(), ["faq"], "se ocultan los demás");
  assert.deepEqual(m.elegida(), ["faq"]);
  assert.equal(m.pestana("faq").tabIndex, 0);
  assert.ok(m.pestanas.filter((p) => p !== m.pestana("faq")).every((p) => p.tabIndex === -1));
  m.pestana("roles").eventos.click();
  assert.deepEqual(m.abierto(), ["roles"]);
  assert.deepEqual(m.reemplazos, ["#faq", "#roles"]);
});

test("un enlace a otro tema estando en la ayuda (hashchange) lo abre", () => {
  const m = montar("");
  m.sandbox.iniciarAyuda(m.doc);
  m.window.location.hash = "#adjuntos";
  m.oyentes.hashchange();
  assert.deepEqual(m.abierto(), ["adjuntos"]);
  assert.deepEqual(m.reemplazos, [], "no vuelve a escribir la dirección");
});

test("teclado: flechas pasan a la vecina (en círculo), Inicio y Fin a los extremos", () => {
  const m = montar("");
  m.sandbox.iniciarAyuda(m.doc);
  let prevenidas = 0;
  const tecla = (id, key) => m.pestana(id).eventos.keydown({ key, preventDefault: () => { prevenidas += 1; } });
  tecla("crear", "ArrowRight");
  assert.deepEqual(m.abierto(), ["lista"]);
  assert.equal(m.enfocada(), m.pestana("lista"), "el foco pasa a la pestaña");
  tecla("lista", "ArrowDown");
  assert.deepEqual(m.abierto(), ["seguimiento"]);
  tecla("seguimiento", "ArrowUp");
  tecla("lista", "ArrowLeft");
  assert.deepEqual(m.abierto(), ["crear"]);
  tecla("crear", "ArrowLeft");
  assert.deepEqual(m.abierto(), ["faq"], "de la primera a la última");
  tecla("faq", "Home");
  assert.deepEqual(m.abierto(), ["crear"]);
  tecla("crear", "End");
  assert.deepEqual(m.abierto(), ["faq"]);
  assert.equal(prevenidas, 7);
  assert.equal(tecla("faq", "a"), null, "otras teclas no hacen nada");
  assert.equal(prevenidas, 7);
  assert.equal(m.reemplazos.at(-1), "#faq");
});

test("sin pestañas (otra página) no hace nada", () => {
  const sandbox = { window: { location: { hash: "" } }, document: { querySelectorAll: () => [], getElementById: () => null } };
  vm.runInNewContext(leer("js/ayuda.js"), sandbox);
  assert.equal(sandbox.mostrarTema("crear", sandbox.document), null);
});
