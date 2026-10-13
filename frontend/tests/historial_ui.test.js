/* Pruebas de frontend/js/historial.js (pantalla Historial de cambios).
   Infraestructura mínima: solo node:test de Node.js (sin librerías
   externas), misma técnica que app_errors.test.js: se cargan los scripts
   reales (auth.js + historial.js) en un contexto con DOM mínimo y fetch
   controlado.
   Regresión principal: la petición al endpoint protegido /api/history debe
   enviarse con fetchWithAuth, que adjunta el Bearer token de la sesión.
   Ejecutar con: node --test frontend/tests/historial_ui.test.js */

"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const HISTORIAL_PATH = path.join(__dirname, "..", "js", "historial.js");
const AUTH_PATH = path.join(__dirname, "..", "js", "auth.js");
const historialSource = fs.readFileSync(HISTORIAL_PATH, "utf8");
const authSource = fs.readFileSync(AUTH_PATH, "utf8");

const TOKEN = "token-de-prueba";

/* Sesión activa mínima para que fetchWithAuth() (auth.js) adjunte el token. */
function createLocalStorage() {
  const store = new Map([["access_token", TOKEN]]);
  return {
    getItem: (key) => (store.has(key) ? store.get(key) : null),
    setItem: (key, value) => store.set(key, String(value)),
    removeItem: (key) => store.delete(key),
  };
}

function createNode(id) {
  return {
    id,
    textContent: "",
    className: "",
    hidden: false,
    href: "",
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
  };
}

function jsonResponse(status, body) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  };
}

function createHarness(fetchImpl) {
  const nodes = new Map(
    ["estado-carga", "lista-historial"].map((id) => [id, createNode(id)])
  );
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
    window: { location: { href: "" } },
    localStorage: createLocalStorage(),
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

  vm.runInNewContext(authSource, sandbox, { filename: "auth.js" });
  vm.runInNewContext(historialSource, sandbox, { filename: "historial.js" });

  return {
    /* init() de historial.js no devuelve la promesa; se invoca la función
       async directamente para poder esperarla (mismo criterio que
       app_errors.test.js con fetchTickets). */
    init: () => sandbox.fetchHistorial(),
    estado: () => nodes.get("estado-carga"),
    tbody: () => nodes.get("lista-historial"),
    window: sandbox.window,
    localStorage: sandbox.localStorage,
    fetchCalls,
    consoleErrors,
  };
}

const ENTRY = {
  id: 13,
  ticket_id: 7,
  action: "Cambio de estado",
  field: "state",
  old_value: "Nuevo",
  new_value: "En proceso",
  author: "Ana Pérez",
  created_at: "2026-10-13T18:27:20.075110Z",
};

/* Regresión del 401: la pantalla debe usar fetchWithAuth (auth.js), que
   adjunta el Bearer token almacenado en la sesión. */
test("el historial se pide con fetchWithAuth y envía el Bearer token", async () => {
  const harness = createHarness(async () => jsonResponse(200, [ENTRY]));

  await harness.init();

  assert.equal(harness.fetchCalls.length, 1);
  assert.equal(harness.fetchCalls[0].url, "/api/history");
  const headers = harness.fetchCalls[0].options.headers || {};
  assert.equal(
    headers.Authorization,
    `Bearer ${TOKEN}`,
    "falta la cabecera Authorization: /api/history responde 401 sin ella"
  );
});

test("con sesión válida pinta las siete columnas del registro", async () => {
  const harness = createHarness(async () => jsonResponse(200, [ENTRY]));

  await harness.init();

  const rows = harness.tbody().children;
  assert.equal(rows.length, 1);
  assert.equal(rows[0].children.length, 7);

  const [fecha, ticket, accion, campo, anterior, nuevo, autor] =
    rows[0].children;
  assert.match(fecha.textContent, /12:27:20/); // 18:27Z son las 12:27 de Costa Rica
  assert.equal(ticket.children[0].href, "detalle.html?id=7");
  assert.equal(ticket.children[0].textContent, "#7");
  assert.equal(accion.textContent, "Cambio de estado");
  assert.equal(campo.textContent, "state");
  assert.equal(anterior.textContent, "Nuevo");
  assert.equal(nuevo.textContent, "En proceso");
  assert.equal(autor.textContent, "Ana Pérez");
  assert.equal(harness.estado().hidden, true);
});

test("conserva el autor real y usa — solo para campos no registrados", async () => {
  const sinDetalle = { ...ENTRY, field: null, old_value: null, new_value: null };
  const harness = createHarness(async () => jsonResponse(200, [sinDetalle]));

  await harness.init();

  const cells = harness.tbody().children[0].children;
  assert.equal(cells[3].textContent, "—");
  assert.equal(cells[4].textContent, "—");
  assert.equal(cells[5].textContent, "—");
  assert.equal(cells[6].textContent, "Ana Pérez");
});

test("lista vacía muestra el mensaje de vacío", async () => {
  const harness = createHarness(async () => jsonResponse(200, []));

  await harness.init();

  assert.equal(harness.estado().textContent, "No hay registros de historial todavía.");
  assert.equal(harness.estado().hidden, false);
  assert.equal(harness.tbody().children.length, 0);
});

test("error HTTP muestra el código de la API", async () => {
  const harness = createHarness(async () =>
    jsonResponse(500, { detail: "Fallo interno" })
  );

  await harness.init();

  assert.equal(harness.estado().textContent, "Error de API (500).");
  assert.equal(harness.consoleErrors.length, 1);
});

test("respuesta que no es lista se reporta como inválida", async () => {
  const harness = createHarness(async () => jsonResponse(200, { detalle: "no" }));

  await harness.init();

  assert.equal(harness.estado().textContent, "Respuesta inválida del servidor.");
});

test("JSON inválido se reporta como respuesta inválida", async () => {
  const harness = createHarness(async () => ({
    ok: true,
    status: 200,
    json: async () => {
      throw new Error("JSON roto");
    },
  }));

  await harness.init();

  assert.equal(harness.estado().textContent, "Respuesta inválida del servidor.");
});

test("sin conexión muestra el aviso del servidor", async () => {
  const harness = createHarness(async () => {
    throw new Error("red caída");
  });

  await harness.init();

  assert.equal(
    harness.estado().textContent,
    "No se pudo conectar con el servidor. Comprueba que está en ejecución."
  );
});

test("un 401 limpia la sesión y redirige a login (auth.js)", async () => {
  const harness = createHarness(async () =>
    jsonResponse(401, { detail: "No autenticado" })
  );

  await harness.init();

  // fetchWithAuth redirige y lanza; historial.js captura el error y pinta
  // su aviso genérico (mismo comportamiento que el resto de pantallas).
  assert.equal(harness.window.location.href, "login.html");
  assert.equal(
    harness.localStorage.getItem("access_token"),
    null,
    "la sesión expirada debe limpiarse del navegador"
  );
  assert.equal(
    harness.estado().textContent,
    "No se pudo conectar con el servidor. Comprueba que está en ejecución."
  );
});
