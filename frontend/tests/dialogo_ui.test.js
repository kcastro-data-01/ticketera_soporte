/* Ventana de confirmación propia (auth.js: confirmarAccion) en lugar de
   window.confirm.
   Ejecutar con: node --test frontend/tests/dialogo_ui.test.js */

"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const leer = (archivo) => fs.readFileSync(path.join(__dirname, "..", archivo), "utf8");

function el(tag, doc) {
  return {
    tag, id: "", className: "", textContent: "", type: "", children: [], atributos: {}, listeners: {}, quitado: false,
    setAttribute(k, v) { this.atributos[k] = String(v); },
    addEventListener(t, fn) { (this.listeners[t] = this.listeners[t] || []).push(fn); },
    appendChild(h) { this.children.push(h); return h; },
    append(...hs) { this.children.push(...hs); },
    remove() { this.quitado = true; },
    focus() { doc.activeElement = this; },
  };
}

function montar() {
  const doc = { activeElement: null, teclas: [] };
  doc.createElement = (tag) => el(tag, doc);
  doc.body = el("body", doc);
  doc.addEventListener = (t, fn) => { if (t === "keydown") doc.teclas.push(fn); };
  doc.removeEventListener = (t, fn) => { doc.teclas = doc.teclas.filter((f) => f !== fn); };
  const sandbox = { console, document: doc, localStorage: { getItem: () => null, setItem() {}, removeItem() {} } };
  vm.runInNewContext(leer("js/auth.js"), sandbox);
  return { sandbox, doc };
}

function partes(doc) {
  const fondo = doc.body.children.at(-1);
  const caja = fondo.children[0];
  const [titulo, mensaje, acciones] = caja.children;
  const [no, si] = acciones.children;
  return { fondo, caja, titulo, mensaje, no, si };
}

test("muestra título, mensaje y botones; el foco empieza en Cancelar", async () => {
  const { sandbox, doc } = montar();
  const promesa = sandbox.confirmarAccion({ titulo: "Eliminar ticket", mensaje: "¿Está seguro?", aceptar: "Eliminar", peligro: true });
  const { caja, titulo, mensaje, no, si, fondo } = partes(doc);
  assert.equal(caja.atributos.role, "alertdialog");
  assert.equal(caja.atributos["aria-modal"], "true");
  assert.equal(titulo.textContent, "Eliminar ticket");
  assert.equal(mensaje.textContent, "¿Está seguro?");
  assert.equal(no.textContent, "Cancelar");
  assert.equal(si.textContent, "Eliminar");
  assert.equal(si.className, "boton-peligro");
  assert.equal(doc.activeElement, no);
  si.listeners.click[0]();
  assert.equal(await promesa, true);
  assert.equal(fondo.quitado, true);
});

test("Cancelar, Escape y un clic afuera devuelven false", async () => {
  const { sandbox, doc } = montar();
  let p = sandbox.confirmarAccion({ mensaje: "x" });
  partes(doc).no.listeners.click[0]();
  assert.equal(await p, false);

  p = sandbox.confirmarAccion({ mensaje: "x" });
  doc.teclas[0]({ key: "Escape", preventDefault() {} });
  assert.equal(await p, false);
  assert.equal(doc.teclas.length, 0, "deja de escuchar el teclado");

  p = sandbox.confirmarAccion({ mensaje: "x" });
  const { fondo, caja } = partes(doc);
  fondo.listeners.click[0]({ target: caja });
  fondo.listeners.click[0]({ target: fondo });
  assert.equal(await p, false);
});

test("Tab alterna entre los dos botones", () => {
  const { sandbox, doc } = montar();
  sandbox.confirmarAccion({ mensaje: "x" });
  const { no, si } = partes(doc);
  doc.teclas[0]({ key: "Tab", preventDefault() {} });
  assert.equal(doc.activeElement, si);
  doc.teclas[0]({ key: "Tab", preventDefault() {} });
  assert.equal(doc.activeElement, no);
});

test("ya no se usa window.confirm al eliminar ni al desactivar", () => {
  for (const archivo of ["js/detalle.js", "js/usuarios.js"]) {
    const codigo = leer(archivo);
    assert.doesNotMatch(codigo, /window\.confirm\(/, archivo);
    assert.match(codigo, /await confirmarAccion\(\{/, archivo);
  }
});
