/* Avisos flotantes (auth.js): aparecen abajo a la izquierda, se van a
   los 3 segundos y pueden quedar pendientes para la página siguiente.
   Ejecutar con: node --test frontend/tests/avisos_ui.test.js */

"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const authSource = fs.readFileSync(path.join(__dirname, "..", "js", "auth.js"), "utf8");

function nodo(tag) {
  return {
    tag, id: "", className: "", textContent: "", children: [], atributos: {}, quitado: false,
    classList: { add(c) { this.owner.className += ` ${c}`; } },
    setAttribute(k, v) { this.atributos[k] = v; },
    appendChild(h) { this.children.push(h); return h; },
    remove() { this.quitado = true; },
  };
}

function cargar() {
  const almacen = new Map();
  const timers = [];
  const body = nodo("body");
  const doc = {
    body,
    createElement(tag) { const n = nodo(tag); n.classList.owner = n; return n; },
    getElementById: (id) => body.children.find((n) => n.id === id) || null,
  };
  const sandbox = {
    console,
    localStorage: { getItem: () => null, setItem() {}, removeItem() {} },
    sessionStorage: {
      getItem: (k) => (almacen.has(k) ? almacen.get(k) : null),
      setItem: (k, v) => almacen.set(k, String(v)),
      removeItem: (k) => almacen.delete(k),
    },
    setTimeout: (fn, ms) => timers.push({ fn, ms }),
  };
  vm.runInNewContext(authSource, sandbox, { filename: "auth.js" });
  sandbox.document = doc;
  return { s: sandbox, doc, timers, almacen };
}

test("el aviso de éxito aparece y se va a los 3 segundos", () => {
  const { s, doc, timers } = cargar();
  const aviso = s.mostrarAviso("Comentario agregado correctamente.", "exito", doc);
  const zona = doc.getElementById("avisos");
  assert.equal(zona.className, "avisos");
  assert.equal(zona.atributos["aria-live"], "polite");
  assert.equal(aviso.className, "aviso exito");
  assert.equal(aviso.textContent, "Comentario agregado correctamente.");
  assert.equal(timers[0].ms, 3000);
  timers[0].fn();
  assert.match(aviso.className, /saliendo/);
  timers[1].fn();
  assert.equal(aviso.quitado, true);
});

test("los errores usan el mismo aviso en rojo", () => {
  const { s, doc } = cargar();
  s.mostrarAviso("Error al comunicarse con la API.", "error", doc);
  s.mostrarAviso("Otro", "error", doc);
  const zona = doc.getElementById("avisos");
  assert.equal(doc.body.children.length, 1, "una sola zona para todos los avisos");
  assert.deepEqual(zona.children.map((a) => a.className), ["aviso error", "aviso error"]);
});

test("un aviso pendiente se muestra una sola vez en la página siguiente", () => {
  const { s, doc, almacen } = cargar();
  s.avisoPendiente("Ticket #4 eliminado.");
  assert.ok(almacen.has("aviso_pendiente"));
  s.mostrarAvisoPendiente();
  assert.equal(doc.getElementById("avisos").children[0].textContent, "Ticket #4 eliminado.");
  assert.equal(almacen.has("aviso_pendiente"), false);
  s.mostrarAvisoPendiente();
  assert.equal(doc.getElementById("avisos").children.length, 1);
});

test("los avisos reemplazan los mensajes de éxito de las acciones", () => {
  const detalle = fs.readFileSync(path.join(__dirname, "..", "js", "detalle.js"), "utf8");
  for (const texto of ["Cambios guardados correctamente.", "Comentario agregado correctamente.", "Estado actualizado a"]) {
    assert.match(detalle, new RegExp(`avisar\\(\\s*\`?"?${texto}`), texto);
  }
  assert.match(detalle, /avisoPendiente\(`Ticket #\$\{ticketId\} eliminado.`\)/);
  const crear = fs.readFileSync(path.join(__dirname, "..", "js", "crear.js"), "utf8");
  assert.match(crear, /avisoPendiente\(`Ticket #\$\{ticket\.id\} guardado.`\)/);
  assert.doesNotMatch(detalle + crear, /\balert\(/);
});
