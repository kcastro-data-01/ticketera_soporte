/* Consistencia visual: alturas, radios, títulos y espaciado salen de las
   mismas variables CSS en todas las pantallas.
   Ejecutar con: node --test frontend/tests/consistencia.test.js */

"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const leer = (archivo) => fs.readFileSync(path.join(__dirname, "..", archivo), "utf8");
const css = leer("css/estilos.css");
const login = leer("login.html");

const regla = (fuente, selector) => {
  const i = fuente.indexOf(`${selector} {`);
  assert.ok(i >= 0, selector);
  return fuente.slice(i, fuente.indexOf("}", i));
};

test("las variables de alturas, radios y espaciado existen", () => {
  for (const variable of ["--alto-control: 2.25rem", "--alto-control-chico: 1.75rem", "--radio-suave: 6px", "--radio-ventana: 8px", "--espaciado-seccion: 1.75rem"]) {
    assert.ok(css.includes(variable), variable);
  }
});

test("botones y campos usan la misma altura en la app y en el login", () => {
  assert.match(regla(css, "\nbutton"), /min-height: var\(--alto-control\);/);
  assert.match(regla(css, "\n.enlace-boton"), /min-height: var\(--alto-control\);[\s\S]*font-size: var\(--texto-md\);/);
  assert.match(regla(css, ".campo select"), /min-height: var\(--alto-control\);/);
  assert.match(regla(css, "\n.btn-accion"), /min-height: var\(--alto-control-chico\);/);
  assert.match(regla(login, ".auth-container .login-der .campo .form-input"), /min-height: var\(--alto-control\);[\s\S]*font-size: var\(--texto-md\);/);
  assert.match(regla(login, "    .btn-primario"), /min-height: var\(--alto-control\);/);
});

test("ventanas con 8 px, tarjetas con 6 px y títulos con la misma escala", () => {
  for (const selector of ["\n.chat-boton", "\n.chat-panel", "\n.dialogo"]) {
    assert.match(regla(css, selector), /border-radius: var\(--radio-ventana\);/, selector);
  }
  assert.match(regla(css, "\n.pagina-error-tarjeta"), /border-radius: var\(--radio-suave\);/);
  assert.match(css, /\.pagina-error-tarjeta h2 \{\s*margin: 0 0 0\.5rem;\s*color: var\(--color-titulo\);\s*font-size: var\(--texto-titulo\);/);
  assert.match(regla(login, ".auth-container .login-der .login-titulo"), /font-size: var\(--texto-titulo\);/);
  assert.match(regla(css, "\n.seccion"), /margin-top: var\(--espaciado-seccion\);/);
});

test("Mi cuenta trata de usted", () => {
  assert.match(leer("cuenta.html"), /Repita la nueva contraseña \*/);
});
