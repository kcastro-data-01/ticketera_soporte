/* Accesibilidad: contraste AA de los textos (modo claro y oscuro), foco
   visible, tamaños táctiles en el celular y nombres en los botones de
   solo ícono.
   Ejecutar con: node --test frontend/tests/accesibilidad.test.js */

"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const leer = (archivo) => fs.readFileSync(path.join(__dirname, "..", archivo), "utf8");
const css = leer("css/estilos.css");

function tokens(selector) {
  const inicio = css.indexOf(`${selector} {`);
  const bloque = css.slice(inicio, css.indexOf("\n}", inicio));
  return Object.fromEntries([...bloque.matchAll(/--([\w-]+):\s*(#[0-9a-fA-F]{6})\s*;/g)].map((m) => [m[1], m[2]]));
}

function luminancia(hex) {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
    .map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contraste(a, b) {
  const [x, y] = [luminancia(a), luminancia(b)].sort((m, n) => n - m);
  return (x + 0.05) / (y + 0.05);
}

const claro = tokens(":root");
const temas = { claro, oscuro: { ...claro, ...tokens(':root[data-tema="oscuro"]') } };

const PARES = [
  ["color-texto", "color-fondo"],
  ["color-tenue", "color-superficie-alta"],
  ["color-tenue", "color-fondo"],
  ["color-tenue", "color-fondo-neutro"],
  ["color-tenue-fuerte", "color-superficie-alta"],
  ["color-enlace", "color-superficie-alta"],
  ["color-error", "color-superficie-alta"],
  ["color-error", "color-error-fondo"],
  ["color-menu-tenue", "color-marino"],
  ...["rojo", "naranja", "amarillo", "gris", "azul", "violeta", "verde"].map((c) => [`etiqueta-${c}-texto`, `etiqueta-${c}-fondo`]),
];

for (const [nombre, t] of Object.entries(temas)) {
  test(`contraste AA (4.5:1) de textos y etiquetas en modo ${nombre}`, () => {
    for (const [texto, fondo] of PARES) {
      const r = contraste(t[texto], t[fondo]);
      assert.ok(r >= 4.5, `${texto} sobre ${fondo}: ${r.toFixed(2)}`);
    }
  });
}

test("el gris claro (sin contraste AA) ya no se usa para textos", () => {
  const usos = [...css.matchAll(/^\s*color: var\(--color-texto-suave\)/gm)];
  assert.equal(usos.length, 0);
});

test("foco visible en botones, enlaces y campos", () => {
  assert.match(css, /:focus-visible \{\s*outline: 3px solid var\(--color-primario\);/);
  assert.match(css, /\.campo :is\(input, select, textarea\):focus-visible,[\s\S]*?outline: 2px solid var\(--color-primario\);/);
});

test("en el celular los botones y campos miden al menos 40 x 40 px", () => {
  const bloque = css.slice(css.indexOf("/* Tamaños táctiles"));
  assert.match(bloque, /@media \(max-width: 700px\) \{\s*button,[\s\S]*?min-width: 40px;\s*min-height: 40px;/);
});

test("los botones de solo ícono tienen nombre (aria-label)", () => {
  const login = leer("login.html");
  const ojos = login.match(/<button type="button" class="toggle-password" aria-label="Mostrar contraseña" aria-pressed="false"/g) || [];
  assert.equal(ojos.length, 1, "mostrar contraseña (solo LOGIN_LOCAL) es un botón con nombre");
  const chat = leer("js/asistente.js");
  for (const nombre of ["Abrir asistente virtual", "Cerrar asistente", "Nueva conversación", "Enviar"]) {
    assert.ok(chat.includes(`"${nombre}"`), nombre);
  }
  const auth = leer("js/auth.js");
  assert.match(auth, /"Activar modo claro" : "Activar modo oscuro"/);
  assert.match(leer("detalle.html"), /id="imprimir"[^>]*>Imprimir<\/button>/, "Imprimir tiene texto visible");
});
