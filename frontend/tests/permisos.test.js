/* Pruebas de la tabla de permisos del frontend (frontend/js/auth.js):
   puede() y aplicarPermisos() según el rol de la sesión.
   Ejecutar con: node --test frontend/tests/permisos.test.js */

"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const authSource = fs.readFileSync(path.join(__dirname, "..", "js", "auth.js"), "utf8");

function loadAuth(role) {
  const store = new Map([["access_token", "token"]]);
  if (role) store.set("user", JSON.stringify({ name: "Prueba", role }));
  const context = {
    localStorage: {
      getItem: (key) => (store.has(key) ? store.get(key) : null),
      setItem: (key, value) => store.set(key, String(value)),
      removeItem: (key) => store.delete(key),
    },
    window: { location: { href: "" } },
  };
  vm.createContext(context);
  vm.runInContext(authSource, context);
  return context;
}

const TABLA = {
  Administrador: { editar: true, asignar: true, cambiar_estado: true, historial_global: true, usuarios: true, eliminar: true, explicar_ia: true },
  // El rol Supervisor ya no existe: no tiene ningún permiso.
  Supervisor: { editar: false, asignar: false, cambiar_estado: false, historial_global: false, usuarios: false, eliminar: false, explicar_ia: false },
  Técnico: { editar: false, asignar: false, cambiar_estado: true, historial_global: true, usuarios: false, eliminar: false, explicar_ia: true },
  Solicitante: { editar: false, asignar: false, cambiar_estado: false, historial_global: false, usuarios: false, eliminar: false, explicar_ia: false },
};

for (const [rol, permisos] of Object.entries(TABLA)) {
  test(`puede(): permisos del rol ${rol}`, () => {
    const ctx = loadAuth(rol);
    for (const [permiso, esperado] of Object.entries(permisos)) {
      assert.equal(ctx.puede(permiso), esperado, `${rol} / ${permiso}`);
    }
  });
}

test("puede(): sin rol en la sesión no concede ningún permiso", () => {
  const ctx = loadAuth(null);
  assert.equal(ctx.puede("editar"), false);
  assert.equal(ctx.puede("usuarios"), false);
});

test("aplicarPermisos() oculta solo los elementos no permitidos", () => {
  const ctx = loadAuth("Técnico");
  const elementos = [
    { dataset: { permiso: "editar" }, hidden: false },
    { dataset: { permiso: "cambiar_estado" }, hidden: false },
    { dataset: { permiso: "usuarios" }, hidden: false },
  ];
  ctx.aplicarPermisos({ querySelectorAll: () => elementos });
  assert.deepEqual(
    elementos.map((el) => el.hidden),
    [true, false, true]
  );
});

test("requirePermiso() lleva a «Acceso restringido» sin permiso", () => {
  const ctx = loadAuth("Solicitante");
  assert.equal(ctx.requirePermiso("historial_global"), false);
  assert.equal(ctx.window.location.href, "sin-permiso.html");
});

test("detalle.html: el botón Eliminar solo lo ve el Administrador", () => {
  const html = fs.readFileSync(path.join(__dirname, "..", "detalle.html"), "utf8");
  assert.match(html, /<button[^>]*id="eliminar"[^>]*data-permiso="eliminar"/);
  for (const [rol, visible] of [["Administrador", true], ["Supervisor", false], ["Técnico", false], ["Solicitante", false]]) {
    const ctx = loadAuth(rol);
    const boton = { dataset: { permiso: "eliminar" }, hidden: false };
    ctx.aplicarPermisos({ querySelectorAll: () => [boton] });
    assert.equal(boton.hidden, !visible, rol);
  }
});

test("detalle.html: Editar e Imprimir a la izquierda y Eliminar aparte a la derecha", () => {
  const html = fs.readFileSync(path.join(__dirname, "..", "detalle.html"), "utf8");
  const barra = html.slice(html.indexOf('class="acciones acciones-principales"'), html.indexOf("</div>", html.indexOf("acciones-principales")));
  const orden = [...barra.matchAll(/id="(editar|imprimir|eliminar)"/g)].map((m) => m[1]);
  assert.deepEqual(orden, ["editar", "imprimir", "eliminar"]);
  assert.match(barra, /id="eliminar" class="peligro accion-aparte"/);
  const css = fs.readFileSync(path.join(__dirname, "..", "css", "estilos.css"), "utf8");
  assert.match(css, /\.acciones-principales \.accion-aparte \{\s*margin-left: auto;/);
});

test("Supervisor no aparece en auth.js, usuarios.html ni usuarios.js (3 roles)", () => {
  for (const archivo of ["js/auth.js", "usuarios.html", "js/usuarios.js", "js/asistente.js"]) {
    const texto = fs.readFileSync(path.join(__dirname, "..", archivo), "utf8");
    assert.doesNotMatch(texto, /supervis/i, archivo);
  }
  const html = fs.readFileSync(path.join(__dirname, "..", "usuarios.html"), "utf8");
  for (const id of ["rol", "editar-rol"]) {
    const select = html.slice(html.indexOf(`id="${id}"`), html.indexOf("</select>", html.indexOf(`id="${id}"`)));
    const opciones = [...select.matchAll(/<option value="([^"]+)"/g)].map((m) => m[1]).sort();
    assert.deepEqual(opciones, ["Administrador", "Solicitante", "Técnico"], id);
  }
});
