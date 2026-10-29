/* Tickets asignados a quien los ve (por ejemplo, los que llegan desde un
   correo): el asignado cambia el estado aunque su rol no pueda (auth.js y
   detalle.js) y el historial dice desde qué correo se creó.
   Ejecutar con: node --test frontend/tests/asignado_ui.test.js */

"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const leer = (archivo) => fs.readFileSync(path.join(__dirname, "..", archivo), "utf8");
const authSource = leer("js/auth.js");
const detalleSource = leer("js/detalle.js");
const html = leer("detalle.html");
const ayuda = leer("ayuda.html");

function nodo(id) {
  return {
    id, value: "", textContent: "", className: "", hidden: false, disabled: false, children: [],
    dataset: {}, listeners: {}, classList: { add() {}, remove() {}, toggle() {}, contains: () => false },
    setAttribute() {}, getAttribute: () => null,
    addEventListener(t, fn) { (this.listeners[t] = this.listeners[t] || []).push(fn); },
    appendChild(h) { this.children.push(h); return h; },
    replaceChildren(...h) { this.children = h; },
  };
}

function montar(user) {
  const nodos = new Map();
  const sandbox = {
    document: {
      getElementById: (id) => { if (!nodos.has(id)) nodos.set(id, nodo(id)); return nodos.get(id); },
      createElement: (tag) => nodo(tag),
      createTextNode: (t) => ({ textContent: t }),
      querySelectorAll: () => [],
      addEventListener() {},
    },
    window: { location: { search: "?id=1", href: "" } },
    localStorage: {
      getItem: (k) => ({ access_token: "t", user: JSON.stringify(user) })[k] ?? null,
      setItem() {}, removeItem() {},
    },
    console: { error() {}, log() {} },
    URLSearchParams, Map, Date, Number, String,
  };
  vm.createContext(sandbox);
  vm.runInContext(authSource, sandbox);
  vm.runInContext(detalleSource, sandbox);
  return { sandbox, nodos };
}

const TICKET = {
  id: 1, title: "Impresora", description: "No imprime", category: "Hardware", priority: "Media",
  state: "Nuevo", assigned_to_id: 9, created_by_id: 1,
  created_at: "2026-10-26T15:00:00Z", updated_at: "2026-10-26T15:00:00Z",
};
const PEDRO = { id: 9, name: "Pedro Rojas", role: "Solicitante" };

test("puedeCambiarEstado: el equipo siempre; los demás, solo en sus asignados", () => {
  const { sandbox } = montar(PEDRO);
  assert.equal(sandbox.puede("cambiar_estado"), false, "la tabla de permisos del rol no cambia");
  assert.equal(sandbox.puedeCambiarEstado(TICKET), true);
  assert.equal(sandbox.puedeCambiarEstado({ ...TICKET, assigned_to_id: 4 }), false);
  assert.equal(sandbox.puedeCambiarEstado({ ...TICKET, assigned_to_id: null }), false);
  const tecnico = montar({ id: 3, name: "Sofía", role: "Técnico" }).sandbox;
  assert.equal(tecnico.puedeCambiarEstado({ ...TICKET, assigned_to_id: 4 }), true);
  // Editar, asignar y eliminar siguen siendo del rol.
  for (const permiso of ["editar", "asignar", "eliminar"]) assert.equal(sandbox.puede(permiso), false);
});

test("detalle: el asignado ve «Cambio de estado» solo en sus tickets asignados", () => {
  assert.match(html, /id="seccion-estado"[^>]*data-permiso="cambiar_estado"/);
  const asignado = montar(PEDRO);
  asignado.sandbox.renderTicket(TICKET);
  assert.equal(asignado.nodos.get("seccion-estado").hidden, false);

  const otro = montar(PEDRO);
  otro.sandbox.renderTicket({ ...TICKET, assigned_to_id: 4 });
  assert.equal(otro.nodos.get("seccion-estado").hidden, true);
});

test("historial: el ticket creado desde un correo dice quién lo envió y a quién", () => {
  const { sandbox } = montar(PEDRO);
  const texto = "Ticket creado desde correo enviado por Kristin Castro a Pedro Rojas";
  assert.deepEqual(
    { ...sandbox.describirHistorial({ action: "created", field: "correo", new_value: texto }) },
    { accion: "Creó el ticket", detalle: texto }
  );
  assert.deepEqual(
    { ...sandbox.describirHistorial({ action: "created", field: "assigned_to_id", new_value: "Sofía" }) },
    { accion: "Creó el ticket", detalle: "Asignado automáticamente a Sofía" }
  );
});

test("ayuda: la tabla de permisos explica lo del Solicitante asignado", () => {
  assert.match(ayuda, /<td>Cambiar estado<\/td>(<td>Sí<\/td>){2}<td>Solo en los asignados a él<\/td>/);
  assert.match(ayuda, /<td>Ver tickets<\/td>.*<td>Los suyos y los asignados a él<\/td>/);
});

test("ayuda: los correos enviados pasan por el mismo filtro que los que llegan", () => {
  assert.match(ayuda, /Los correos que el dueño del buzón envía a alguien de la empresa pasan por el mismo filtro que los que llegan: crean un ticket si el asunto empieza con «Ticket:» o si le reporta a un compañero un problema técnico/);
  assert.match(ayuda, /Los avisos que envía la ticketera .* nunca crean tickets/);
  assert.match(ayuda, /Responder en el hilo de un ticket, o con «\[Ticket #N\]» en el asunto, agrega un comentario/);
  assert.match(ayuda, /primero se ingresa a la ticketera con la cuenta de Microsoft de la empresa/);
  assert.match(ayuda, /Nuevo comentario en el ticket #N/);
});
