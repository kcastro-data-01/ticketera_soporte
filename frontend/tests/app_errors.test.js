/* Tarea 19 — Pruebas del manejo de errores de fetchTickets() en frontend/js/app.js.
   Infraestructura mínima: solo node:test de Node.js (sin librerías externas).
   Cada prueba comprueba además que fetchTickets() realiza EXACTAMENTE UNA
   petición HTTP por ejecución.
   Ejecutar con: node --test frontend/tests/app_errors.test.js */

"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const APP_PATH = path.join(__dirname, "..", "js", "app.js");
const appSource = fs.readFileSync(APP_PATH, "utf8");

const TICKET = {
  id: 1,
  title: "Sin acceso al correo",
  category: "Incidente",
  priority: "Alta",
  state: "Nuevo",
  assigned_to_id: null,
  created_at: "2026-10-08T10:00:00",
};

function createNode(id) {
  return {
    id,
    textContent: "",
    className: "",
    hidden: false,
    href: "",
    value: "",
    children: [],
    listeners: {},
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
    reset() {},
  };
}

function jsonResponse(status, body) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  };
}

/* Carga el app.js real en un contexto con un DOM mínimo y fetch controlado. */
function createHarness(fetchImpl) {
  const nodes = new Map();
  [
    "form-filtros",
    "search",
    "category",
    "priority",
    "state",
    "limpiar",
    "estado-carga",
    "lista-tickets",
  ].forEach((id) => nodes.set(id, createNode(id)));

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
    fetch: (url, options) => {
      fetchCalls.push(url);
      return fetchImpl(url, options);
    },
    console: {
      error: (...args) => consoleErrors.push(args),
    },
    URLSearchParams,
    Map,
  };

  vm.runInNewContext(appSource, sandbox, { filename: "app.js" });

  return {
    fetchTickets: () => sandbox.fetchTickets(),
    estado: () => nodes.get("estado-carga"),
    tbody: () => nodes.get("lista-tickets"),
    setFilter(id, value) {
      nodes.get(id).value = value;
    },
    fetchCalls,
    consoleErrors,
  };
}

/* Invariante central de la T19: una sola petición por ejecución. */
function assertFetchCount(harness, expected, label = "") {
  assert.equal(
    harness.fetchCalls.length,
    expected,
    `${label ? `${label}: ` : ""}fetchTickets() debe haber realizado exactamente ${expected} petición(es) HTTP`
  );
}

test("respuesta 200 con tickets: se pinta la lista y se oculta el estado", async () => {
  const harness = createHarness(async () => jsonResponse(200, [TICKET]));

  await harness.fetchTickets();

  assertFetchCount(harness, 1);
  assert.equal(harness.fetchCalls[0], "/api/tickets");
  assert.equal(harness.estado().hidden, true);
  assert.equal(harness.tbody().children.length, 1);
  assert.equal(harness.consoleErrors.length, 0);
});

test("respuesta 200 vacía: se muestra el mensaje de vacío", async () => {
  const harness = createHarness(async () => jsonResponse(200, []));

  await harness.fetchTickets();

  assertFetchCount(harness, 1);
  assert.equal(harness.estado().textContent, "No hay tickets para mostrar.");
  assert.equal(harness.estado().className, "estado vacio");
  assert.equal(harness.estado().hidden, false);
});

test("con filtros la URL conserva los parámetros y sin filtros usa /api/tickets", async () => {
  const harness = createHarness(async () => jsonResponse(200, []));

  await harness.fetchTickets();
  assertFetchCount(harness, 1);

  harness.setFilter("search", "correo");
  harness.setFilter("state", "En proceso");
  await harness.fetchTickets();

  /* Cada ejecución añade exactamente UNA petición. */
  assertFetchCount(harness, 2);
  assert.equal(harness.fetchCalls[0], "/api/tickets");
  assert.equal(
    harness.fetchCalls[1],
    "/api/tickets?search=correo&state=En+proceso"
  );
});

test("error HTTP con detail de texto: se muestra el código y el detalle", async () => {
  const harness = createHarness(async () =>
    jsonResponse(404, { detail: "Ticket no encontrado" })
  );

  await harness.fetchTickets();

  assertFetchCount(harness, 1);
  assert.equal(
    harness.estado().textContent,
    "Error de API (404): Ticket no encontrado"
  );
  assert.equal(harness.estado().className, "estado error");
  assert.equal(harness.consoleErrors.length, 1);
});

test("error HTTP con detail no legible: se muestra solo el código HTTP", async () => {
  const harness = createHarness(async () =>
    jsonResponse(422, {
      detail: [{ type: "enum", loc: ["query", "state"], msg: "Input should be..." }],
    })
  );

  await harness.fetchTickets();

  assertFetchCount(harness, 1);
  assert.equal(harness.estado().textContent, "Error de API (422).");
});

test("error HTTP con cuerpo no JSON: se muestra solo el código HTTP", async () => {
  const harness = createHarness(async () => ({
    ok: false,
    status: 500,
    json: async () => {
      throw new SyntaxError("Unexpected token '<'");
    },
  }));

  await harness.fetchTickets();

  assertFetchCount(harness, 1);
  assert.equal(harness.estado().textContent, "Error de API (500).");
});

test("error de conexión: se informa que el servidor no responde", async () => {
  const harness = createHarness(async () => {
    throw new TypeError("Failed to fetch");
  });

  await harness.fetchTickets();

  assertFetchCount(harness, 1);
  assert.equal(
    harness.estado().textContent,
    "No se pudo conectar con el servidor. Comprueba que está en ejecución."
  );
  assert.equal(harness.estado().className, "estado error");
  assert.ok(harness.consoleErrors.length > 0);
});

test("respuesta 200 con cuerpo no JSON: respuesta inválida del servidor", async () => {
  const harness = createHarness(async () => ({
    ok: true,
    status: 200,
    json: async () => {
      throw new SyntaxError("Unexpected token '<'");
    },
  }));

  await harness.fetchTickets();

  assertFetchCount(harness, 1);
  assert.equal(harness.estado().textContent, "Respuesta inválida del servidor.");
  assert.equal(harness.estado().className, "estado error");
});

test("respuesta 200 con JSON que no es un array: respuesta inválida del servidor", async () => {
  const harness = createHarness(async () =>
    jsonResponse(200, { detail: "algo inesperado" })
  );

  await harness.fetchTickets();

  assertFetchCount(harness, 1);
  assert.equal(harness.estado().textContent, "Respuesta inválida del servidor.");
  assert.equal(harness.estado().className, "estado error");
});

test("cada ejecución de fetchTickets() realiza exactamente una petición HTTP", async () => {
  const escenarios = [
    ["200 con tickets", async () => jsonResponse(200, [TICKET])],
    ["200 vacío", async () => jsonResponse(200, [])],
    [
      "error HTTP",
      async () => jsonResponse(500, { detail: "Fallo interno del servidor" }),
    ],
    [
      "error de conexión",
      async () => {
        throw new TypeError("Failed to fetch");
      },
    ],
  ];

  for (const [nombre, fetchImpl] of escenarios) {
    const harness = createHarness(fetchImpl);
    assertFetchCount(harness, 0);
    await harness.fetchTickets();
    assertFetchCount(harness, 1, nombre);
  }
});
