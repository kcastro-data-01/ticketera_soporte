/* Reglas de integridad en el frontend (auth.js, detalle.js y app.js):
   - Editar: quien creó el ticket solo mientras está «Nuevo»; el
     Administrador en cualquier estado salvo «Cerrado»; nadie más.
   - Un ticket Cerrado es de solo lectura para todos: sin «Editar»,
     «Asignación», «Eliminar» ni cuadro de comentario, con la nota
     «Este ticket está Cerrado y no admite cambios.».
   Ejecutar con: node --test frontend/tests/integridad_ui.test.js */

"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const JS = path.join(__dirname, "..", "js");
const authSource = fs.readFileSync(path.join(JS, "auth.js"), "utf8");
const detalleSource = fs.readFileSync(path.join(JS, "detalle.js"), "utf8");
const appSource = fs.readFileSync(path.join(JS, "app.js"), "utf8");

const ADMIN = { id: 1, name: "Ana Admin", role: "Administrador" };
const TECNICO = { id: 2, name: "Tomás Técnico", role: "Técnico" };
const SOLICITANTE = { id: 3, name: "Sara Solicitante", role: "Solicitante" };

function ticket(cambios = {}) {
  return {
    id: 1,
    title: "Impresora sin conexión",
    description: "La impresora del segundo piso no responde.",
    category: "Hardware",
    priority: "Alta",
    state: "Nuevo",
    assigned_to_id: TECNICO.id,
    created_by_id: SOLICITANTE.id,
    created_at: "2026-10-08T16:00:00Z",
    updated_at: "2026-10-08T16:00:00Z",
    ...cambios,
  };
}

function localStorageCon(usuario) {
  const store = new Map([["access_token", "token"]]);
  if (usuario) store.set("user", JSON.stringify(usuario));
  return {
    getItem: (key) => (store.has(key) ? store.get(key) : null),
    setItem: (key, value) => store.set(key, String(value)),
    removeItem: (key) => store.delete(key),
  };
}

function cargarAuth(usuario) {
  const ctx = { localStorage: localStorageCon(usuario), window: { location: { href: "" } } };
  vm.createContext(ctx);
  vm.runInContext(authSource, ctx);
  return ctx;
}

/* ---------------- auth.js: puedeEditarTicket ---------------- */

const CASOS_EDITAR = [
  ["creador (Solicitante) en Nuevo", SOLICITANTE, ticket(), true],
  ["creador (Solicitante) en En proceso", SOLICITANTE, ticket({ state: "En proceso" }), false],
  ["creador (Técnico) en Nuevo", TECNICO, ticket({ created_by_id: TECNICO.id }), true],
  ["creador en Cerrado", SOLICITANTE, ticket({ state: "Cerrado" }), false],
  ["Administrador en En proceso", ADMIN, ticket({ state: "En proceso" }), true],
  ["Administrador en Resuelto", ADMIN, ticket({ state: "Resuelto" }), true],
  ["Administrador en Cerrado", ADMIN, ticket({ state: "Cerrado" }), false],
  ["Técnico que no lo creó (asignado) en Nuevo", TECNICO, ticket(), false],
  ["Solicitante que no lo creó", { ...SOLICITANTE, id: 9 }, ticket(), false],
];

for (const [caso, usuario, t, esperado] of CASOS_EDITAR) {
  test(`puedeEditarTicket: ${caso} → ${esperado ? "sí" : "no"}`, () => {
    assert.equal(cargarAuth(usuario).puedeEditarTicket(t), esperado);
  });
}

test("puedeCambiarEstado: en un ticket Cerrado nadie, ni el Administrador ni el asignado", () => {
  assert.equal(cargarAuth(ADMIN).puedeCambiarEstado(ticket({ state: "Cerrado" })), false);
  assert.equal(cargarAuth(TECNICO).puedeCambiarEstado(ticket({ state: "Cerrado" })), false);
  assert.equal(cargarAuth(ADMIN).puedeCambiarEstado(ticket({ state: "Resuelto" })), true);
});

/* ---------------- detalle.js: controles según el ticket ---------------- */

function nodo(id) {
  return {
    id,
    textContent: "",
    className: "",
    hidden: false,
    disabled: false,
    value: "",
    children: [],
    listeners: {},
    dataset: {},
    get options() {
      return this.children;
    },
    focus() {},
    setAttribute() {},
    removeAttribute() {},
    addEventListener(type, handler) {
      (this.listeners[type] = this.listeners[type] || []).push(handler);
    },
    appendChild(child) {
      this.children.push(child);
      return child;
    },
    replaceChildren(...hijos) {
      this.children = hijos;
    },
  };
}

function json(status, body) {
  return { ok: status >= 200 && status < 300, status, json: async () => body };
}

function montarDetalle(usuario, t, rutas = {}) {
  const nodos = new Map();
  const llamadas = [];
  /* El HTML real: la sección de edición empieza oculta. */
  const seccion = nodo("seccion-edicion");
  seccion.hidden = true;
  nodos.set("seccion-edicion", seccion);
  const sandbox = {
    document: {
      getElementById(id) {
        if (!nodos.has(id)) nodos.set(id, nodo(id));
        return nodos.get(id);
      },
      createElement: (tag) => nodo(tag),
      addEventListener() {},
    },
    window: { location: { search: "?id=1", href: "detalle.html?id=1" } },
    localStorage: localStorageCon(usuario),
    fetch: async (url, opciones = {}) => {
      const metodo = (opciones.method || "GET").toUpperCase();
      llamadas.push(`${metodo} ${url}`);
      const ruta = rutas[`${metodo} ${url}`];
      if (ruta) return typeof ruta === "function" ? ruta() : ruta;
      if (url === "/api/users") return json(200, [ADMIN, TECNICO, SOLICITANTE]);
      if (url === "/api/tickets/1/comments") return json(200, []);
      if (url === "/api/tickets/1") return json(200, t);
      throw new Error(`URL no soportada: ${metodo} ${url}`);
    },
    console: { error() {}, log() {} },
    URLSearchParams,
    Map,
  };
  /* avisar() es de js/avisos.js: acá se anotan los avisos. */
  const avisos = [];
  sandbox.avisar = (texto, tipo = "exito") => avisos.push({ texto, tipo });
  vm.runInNewContext(authSource, sandbox, { filename: "auth.js" });
  vm.runInNewContext(detalleSource, sandbox, { filename: "detalle.js" });
  return { sandbox, nodo: (id) => sandbox.document.getElementById(id), llamadas, avisos };
}

function visibles(h) {
  return ["editar", "seccion-asignacion", "eliminar", "form-comentario", "estado-final"].filter(
    (id) => !h.nodo(id).hidden
  );
}

test("Detalle: el Administrador en un ticket En proceso ve Editar, Asignación, Eliminar y comentar", async () => {
  const h = montarDetalle(ADMIN, ticket({ state: "En proceso" }));
  await h.sandbox.init();
  assert.deepEqual(visibles(h), ["editar", "seccion-asignacion", "eliminar", "form-comentario"]);
});

test("Detalle: en un ticket Cerrado nadie ve Editar, Asignación, Eliminar ni el cuadro de comentario", async () => {
  for (const usuario of [ADMIN, TECNICO, SOLICITANTE]) {
    const h = montarDetalle(usuario, ticket({ state: "Cerrado" }));
    await h.sandbox.init();
    assert.deepEqual(visibles(h), ["estado-final"], usuario.role);
  }
});

test("detalle.html: la nota de un ticket Cerrado dice que no admite cambios", () => {
  const html = fs.readFileSync(path.join(__dirname, "..", "detalle.html"), "utf8");
  const nota = html.slice(html.indexOf('id="estado-final"'), html.indexOf("</p>", html.indexOf('id="estado-final"')));
  assert.equal(nota.replace(/<[^>]+>/g, "").replace(/\s+/g, " ").replace(/^[^>]*>\s*/, "").trim(),
    "Este ticket está Cerrado y no admite cambios.");
  /* «Editar ticket» lo decide detalle.js por ticket, no por rol. */
  assert.match(html, /<button type="button" id="editar" hidden>Editar ticket<\/button>/);
  assert.match(html, /<section id="seccion-asignacion"[^>]*data-permiso="asignar"/);
});

test("Detalle: el creador ve Editar en Nuevo y no en En proceso; sin Asignación ni Eliminar", async () => {
  const nuevo = montarDetalle(SOLICITANTE, ticket());
  await nuevo.sandbox.init();
  assert.deepEqual(visibles(nuevo), ["editar", "form-comentario"]);

  const enProceso = montarDetalle(SOLICITANTE, ticket({ state: "En proceso" }));
  await enProceso.sandbox.init();
  assert.deepEqual(visibles(enProceso), ["form-comentario"]);
});

test("Detalle: el Técnico que no lo creó no ve Editar (sí comenta)", async () => {
  const h = montarDetalle(TECNICO, ticket());
  await h.sandbox.init();
  assert.deepEqual(visibles(h), ["form-comentario"]);
  h.sandbox.activarEdicion();
  assert.equal(h.nodo("seccion-edicion").hidden, true, "no entra al modo edición");
});

test("Detalle: un 409 al comentar muestra el motivo del servidor y recarga el ticket ya Cerrado", async () => {
  let estado = "En proceso";
  const h = montarDetalle(ADMIN, null, {
    "GET /api/tickets/1": () => json(200, ticket({ state: estado })),
    "POST /api/tickets/1/comments": () => {
      estado = "Cerrado";
      return json(409, { detail: "El ticket #1 está Cerrado y no admite cambios." });
    },
  });
  await h.sandbox.init();
  h.nodo("contenido").value = "¿Alguna novedad?";

  await h.sandbox.agregarComentario();

  assert.deepEqual(h.avisos.at(-1), { texto: "El ticket #1 está Cerrado y no admite cambios.", tipo: "error" });
  assert.deepEqual(visibles(h), ["estado-final"], "los controles se ocultan");
});

test("Detalle: un 403 al editar muestra el motivo del servidor", async () => {
  const h = montarDetalle(SOLICITANTE, ticket(), {
    "PATCH /api/tickets/1": json(403, { detail: "Solo puede editar el ticket mientras está «Nuevo»; ahora está «En proceso»." }),
  });
  await h.sandbox.init();
  h.sandbox.activarEdicion();
  h.nodo("title").value = "Impresora sin conexión (piso 2)";
  h.nodo("description").value = "La impresora del segundo piso no responde.";

  await h.sandbox.guardarEdicion();

  assert.match(h.avisos.at(-1).texto, /mientras está «Nuevo»/);
  assert.equal(h.avisos.at(-1).tipo, "error");
});

/* ---------------- app.js: «Editar» o «Ver» en el listado ---------------- */

function celdaAccion(usuario, t) {
  const sandbox = {
    document: { getElementById: () => undefined, createElement: (tag) => nodo(tag), addEventListener() {} },
    window: { location: {} },
    localStorage: localStorageCon(usuario),
    fetch: async () => json(200, []),
    console: { error() {}, log() {} },
    URLSearchParams,
    Map,
  };
  vm.runInNewContext(authSource, sandbox, { filename: "auth.js" });
  vm.runInNewContext(appSource, sandbox, { filename: "app.js" });
  const fila = nodo("tr");
  sandbox.appendActionCell(fila, t);
  return fila.children[0].children[0].textContent;
}

test("Listado: «Editar» solo en los tickets que quien mira puede editar", () => {
  assert.equal(celdaAccion(ADMIN, ticket({ state: "En proceso" })), "Editar");
  assert.equal(celdaAccion(ADMIN, ticket({ state: "Cerrado" })), "Ver");
  assert.equal(celdaAccion(SOLICITANTE, ticket()), "Editar");
  assert.equal(celdaAccion(SOLICITANTE, ticket({ state: "En proceso" })), "Ver");
  assert.equal(celdaAccion(TECNICO, ticket()), "Ver");
});
