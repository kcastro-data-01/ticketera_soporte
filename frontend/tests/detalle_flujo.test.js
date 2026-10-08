/* Tarea 20.2 — Pruebas de frontend/js/detalle.js: formato de hora de
   Costa Rica, listado de comentarios (carga, vacío, errores y refresco
   tras agregar) y asignación de usuarios.
   Infraestructura mínima: solo node:test de Node.js (sin librerías
   externas), misma técnica que app_errors.test.js (script real en vm).
   Ejecutar con: node --test frontend/tests/detalle_flujo.test.js */

"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const DETALLE_PATH = path.join(__dirname, "..", "js", "detalle.js");
const APP_PATH = path.join(__dirname, "..", "js", "app.js");
const detalleSource = fs.readFileSync(DETALLE_PATH, "utf8");
const appSource = fs.readFileSync(APP_PATH, "utf8");

const USER = { id: 3, name: "Sofía Ruiz", email: "sofia@example.com", role: "Soporte" };

const TICKET = {
  id: 1,
  title: "Impresora sin conexión",
  description: "La impresora del segundo piso no responde.",
  category: "Incidente",
  priority: "Alta",
  state: "Nuevo",
  assigned_to_id: null,
  created_at: "2026-10-08T16:00:00Z",
  updated_at: "2026-10-08T16:00:00Z",
};

const COMMENT = {
  id: 10,
  ticket_id: 1,
  author: "Anónimo",
  content: "Primer comentario.",
  created_at: "2026-10-08T16:05:00Z",
};

const ELEMENT_IDS = [
  "estado-carga",
  "ver-id",
  "ver-title",
  "ver-description",
  "ver-category",
  "ver-priority",
  "ver-state",
  "ver-assigned",
  "ver-created",
  "ver-updated",
  "form-editar",
  "title",
  "description",
  "category",
  "priority",
  "guardar",
  "usuario",
  "asignar",
  "estado-actual",
  "estado-destino",
  "cambiar-estado",
  "estado-final",
  "form-comentario",
  "contenido",
  "comentar",
  "comentarios-estado",
  "lista-comentarios",
  "historial",
  "historial-estado",
  "tabla-historial",
  "historial-cuerpo",
];

function createNode(id) {
  return {
    id,
    textContent: "",
    className: "",
    hidden: false,
    disabled: false,
    value: "",
    children: [],
    listeners: {},
    get options() {
      return this.children;
    },
    addEventListener(type, handler) {
      this.listeners[type] = this.listeners[type] || [];
      this.listeners[type].push(handler);
    },
    appendChild(node) {
      this.children.push(node);
      return node;
    },
    replaceChildren(...nodes) {
      this.children = nodes;
    },
  };
}

function jsonResponse(status, body) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  };
}

/* Enruta las llamadas del detalle real. Cada override puede ser una
   respuesta o una función que devuelve la respuesta (para evolucionar
   el estado entre llamadas). */
function makeFetch(overrides = {}) {
  const resolve = (value, fallback) =>
    typeof value === "function" ? value() : value !== undefined ? value : fallback;
  return async (url, options = {}) => {
    const method = (options.method || "GET").toUpperCase();
    if (url === "/api/users") {
      return resolve(overrides.users, jsonResponse(200, [USER]));
    }
    if (url === "/api/tickets/1/comments" && method === "POST") {
      return resolve(overrides.postComment, jsonResponse(201, COMMENT));
    }
    if (url === "/api/tickets/1/comments") {
      return resolve(overrides.comments, jsonResponse(200, []));
    }
    if (url === "/api/tickets/1/assign" && method === "PATCH") {
      return resolve(overrides.assign, jsonResponse(200, TICKET));
    }
    if (url === "/api/tickets/1" && method === "GET") {
      return resolve(overrides.ticket, jsonResponse(200, TICKET));
    }
    throw new Error(`URL no soportada por el harness: ${method} ${url}`);
  };
}

function createHarness(fetchImpl) {
  const nodes = new Map(ELEMENT_IDS.map((id) => [id, createNode(id)]));
  const fetchCalls = [];
  const consoleErrors = [];

  const sandbox = {
    document: {
      getElementById(id) {
        return nodes.get(id);
      },
      createElement(tag) {
        return createNode(tag);
      },
      addEventListener() {},
    },
    window: { location: { search: "?id=1" } },
    fetch: (url, options) => {
      fetchCalls.push({ url, options });
      return fetchImpl(url, options);
    },
    console: {
      error: (...args) => consoleErrors.push(args),
      log() {},
    },
    URLSearchParams,
    Map,
  };

  vm.runInNewContext(detalleSource, sandbox, { filename: "detalle.js" });

  return {
    init: () => sandbox.init(),
    call(name, ...args) {
      assert.equal(typeof sandbox[name], "function", `${name} debe existir en detalle.js`);
      return sandbox[name](...args);
    },
    node: (id) => nodes.get(id),
    urls: () => fetchCalls.map((call) => call.url),
    fetchCalls,
    consoleErrors,
    clearCalls: () => fetchCalls.splice(0, fetchCalls.length),
  };
}

/* Hora de Costa Rica: 16:00Z son las 10:00 de Costa Rica (UTC-6). */
test("formatFecha del detalle muestra la hora de Costa Rica", () => {
  const harness = createHarness(makeFetch());

  const formatted = harness.call("formatFecha", "2026-10-08T16:00:00Z");

  assert.match(formatted, /10:00:00/);
  assert.ok(!formatted.includes("16:00"), "no debe mostrar la hora UTC");
});

test("formatFecha del listado muestra la hora de Costa Rica", () => {
  const sandbox = {
    document: {
      getElementById: () => undefined,
      createElement: () => createNode("x"),
      addEventListener() {},
    },
    fetch: async () => jsonResponse(200, []),
    console: { error() {}, log() {} },
    URLSearchParams,
    Map,
  };
  vm.runInNewContext(appSource, sandbox, { filename: "app.js" });

  const formatted = sandbox.formatFecha("2026-10-08T16:00:00Z");

  assert.match(formatted, /10:00:00/);
  assert.ok(!formatted.includes("16:00"), "no debe mostrar la hora UTC");
});

test("init carga usuarios, ticket y comentarios con una petición por recurso", async () => {
  const harness = createHarness(makeFetch());

  await harness.init();

  assert.deepEqual(harness.urls(), [
    "/api/users",
    "/api/tickets/1",
    "/api/tickets/1/comments",
  ]);
  assert.equal(harness.node("ver-title").textContent, TICKET.title);
  assert.equal(
    harness.node("estado-carga").hidden,
    true,
    "el estado principal queda oculto tras cargar"
  );
  /* Select con «Sin asignar» + usuarios. */
  const options = harness.node("usuario").children.map((option) => option.textContent);
  assert.deepEqual(options, ["Sin asignar", "Sofía Ruiz"]);
  assert.equal(harness.node("usuario").disabled, false);
  /* Lista vacía: mensaje de vacío en su propio bloque de estado. */
  assert.equal(
    harness.node("comentarios-estado").textContent,
    "Este ticket todavía no tiene comentarios."
  );
  assert.equal(harness.node("comentarios-estado").className, "estado vacio");
  assert.equal(harness.node("lista-comentarios").hidden, true);
});

test("init con ticket asignado muestra quién está asignado", async () => {
  const assigned = { ...TICKET, assigned_to_id: USER.id };
  const harness = createHarness(
    makeFetch({ ticket: jsonResponse(200, assigned) })
  );

  await harness.init();

  assert.equal(harness.node("ver-assigned").textContent, "Sofía Ruiz");
  assert.equal(harness.node("usuario").value, String(USER.id));
});

test("init pinta los comentarios en orden cronológico", async () => {
  const second = {
    ...COMMENT,
    id: 11,
    author: "Soporte",
    content: "Segundo comentario.",
    created_at: "2026-10-08T16:10:00Z",
  };
  const harness = createHarness(
    makeFetch({ comments: jsonResponse(200, [COMMENT, second]) })
  );

  await harness.init();

  const cards = harness.node("lista-comentarios").children;
  assert.equal(cards.length, 2);
  assert.equal(cards[0].children[1].textContent, "Primer comentario.");
  assert.equal(cards[1].children[1].textContent, "Segundo comentario.");
  assert.equal(cards[0].children[0].children[0].textContent, "Anónimo");
  assert.equal(cards[1].children[0].children[0].textContent, "Soporte");
  assert.equal(cards[0].children[0].children[1].textContent.includes("10:05:00"), true);
  assert.equal(harness.node("comentarios-estado").hidden, true);
  assert.equal(harness.node("lista-comentarios").hidden, false);
});

test("comentarios: error HTTP 500 informa el código", async () => {
  const harness = createHarness(
    makeFetch({ comments: jsonResponse(500, { detail: "Fallo" }) })
  );

  await harness.init();

  assert.equal(
    harness.node("comentarios-estado").textContent,
    "No se pudieron cargar los comentarios (HTTP 500)."
  );
  assert.equal(harness.node("comentarios-estado").className, "estado error");
  assert.equal(harness.node("lista-comentarios").hidden, true);
});

test("comentarios: error de conexión informa que el servidor no responde", async () => {
  const harness = createHarness(async (url) => {
    if (url === "/api/tickets/1/comments") throw new TypeError("Failed to fetch");
    return makeFetch()(url, {});
  });

  await harness.init();

  assert.equal(
    harness.node("comentarios-estado").textContent,
    "No se pudo conectar con el servidor. Comprueba que está en ejecución."
  );
  assert.equal(harness.node("comentarios-estado").className, "estado error");
  assert.ok(harness.consoleErrors.length > 0);
});

test("comentarios: JSON que no es una lista da respuesta inválida", async () => {
  const harness = createHarness(
    makeFetch({ comments: jsonResponse(200, { detail: "inesperado" }) })
  );

  await harness.init();

  assert.equal(
    harness.node("comentarios-estado").textContent,
    "Respuesta inválida del servidor."
  );
  assert.equal(harness.node("comentarios-estado").className, "estado error");
});

test("comentarios: 404 muestra el detail del backend", async () => {
  const harness = createHarness(
    makeFetch({ comments: jsonResponse(404, { detail: "Ticket 1 no encontrado" }) })
  );

  await harness.init();

  assert.equal(
    harness.node("comentarios-estado").textContent,
    "Ticket 1 no encontrado"
  );
  assert.equal(harness.node("comentarios-estado").className, "estado error");
});

test("agregarComentario vuelve a consultar la lista sin recargar", async () => {
  let commentsStore = [];
  const harness = createHarness(
    makeFetch({
      comments: () => jsonResponse(200, commentsStore),
      postComment: () => {
        commentsStore = [COMMENT];
        return jsonResponse(201, COMMENT);
      },
    })
  );
  await harness.init();
  harness.clearCalls();

  harness.node("contenido").value = COMMENT.content;
  await harness.call("agregarComentario");

  assert.deepEqual(harness.urls(), [
    "/api/tickets/1/comments", // POST
    "/api/tickets/1/comments", // GET de refresco
  ]);
  assert.equal(harness.fetchCalls[0].options.method, "POST");
  const cards = harness.node("lista-comentarios").children;
  assert.equal(cards.length, 1);
  assert.equal(cards[0].children[1].textContent, "Primer comentario.");
  assert.equal(harness.node("contenido").value, "");
  assert.equal(
    harness.node("estado-carga").textContent,
    "Comentario agregado correctamente."
  );
  assert.equal(harness.node("estado-carga").className, "estado exito");
});

test("agregarComentario vacío no hace ninguna petición", async () => {
  const harness = createHarness(makeFetch());
  await harness.init();
  harness.clearCalls();

  harness.node("contenido").value = "   ";
  await harness.call("agregarComentario");

  assert.deepEqual(harness.urls(), []);
  assert.equal(
    harness.node("estado-carga").textContent,
    "El comentario no puede estar vacío."
  );
  assert.equal(harness.node("estado-carga").className, "estado error");
});

test("asignación con usuario inexistente muestra el detail del backend", async () => {
  const harness = createHarness(
    makeFetch({ assign: jsonResponse(404, { detail: "Usuario 9999 no encontrado" }) })
  );
  await harness.init();
  harness.clearCalls();

  harness.node("usuario").value = "9999";
  await harness.call("guardarAsignacion");

  assert.deepEqual(harness.urls(), ["/api/tickets/1/assign"]);
  assert.equal(harness.fetchCalls[0].options.method, "PATCH");
  assert.deepEqual(JSON.parse(harness.fetchCalls[0].options.body), {
    assigned_to_id: 9999,
  });
  assert.equal(
    harness.node("estado-carga").textContent,
    "Usuario 9999 no encontrado"
  );
  assert.equal(harness.node("estado-carga").className, "estado error");
});

test("asignar la opción «Sin asignar» envía null y confirma el cambio", async () => {
  const harness = createHarness(
    makeFetch({ assign: jsonResponse(200, TICKET) })
  );
  await harness.init();
  harness.clearCalls();

  harness.node("usuario").value = "";
  await harness.call("guardarAsignacion");

  assert.equal(harness.fetchCalls[0].url, "/api/tickets/1/assign");
  assert.deepEqual(JSON.parse(harness.fetchCalls[0].options.body), {
    assigned_to_id: null,
  });
  assert.equal(
    harness.node("estado-carga").textContent,
    "El ticket quedó sin asignar."
  );
  assert.equal(harness.node("estado-carga").className, "estado exito");
  /* Tras guardar se reconsulta el ticket: el panel sigue el estado real. */
  assert.ok(harness.urls().includes("/api/tickets/1"));
});

test("usuarios no disponibles: select deshabilitado y no se envía nada", async () => {
  const harness = createHarness(
    makeFetch({ users: jsonResponse(500, { detail: "Fallo" }) })
  );
  await harness.init();
  harness.clearCalls();

  assert.equal(harness.node("usuario").disabled, true);
  assert.equal(
    harness.node("usuario").children[0].textContent,
    "No se pudo cargar la lista de usuarios"
  );

  await harness.call("guardarAsignacion");

  assert.deepEqual(harness.urls(), [], "no debe enviar una asignación inválida");
  assert.match(
    harness.node("estado-carga").textContent,
    /No se pudo cargar la lista de usuarios/
  );
  assert.equal(harness.node("estado-carga").className, "estado error");
  assert.ok(harness.consoleErrors.length > 0);
});
