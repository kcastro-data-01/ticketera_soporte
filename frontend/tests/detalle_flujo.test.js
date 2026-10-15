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
const AUTH_PATH = path.join(__dirname, "..", "js", "auth.js");
const detalleSource = fs.readFileSync(DETALLE_PATH, "utf8");
const appSource = fs.readFileSync(APP_PATH, "utf8");
const authSource = fs.readFileSync(AUTH_PATH, "utf8");

/* Sesión activa mínima para que fetchWithAuth() (auth.js) adjunte el token. */
function createLocalStorage() {
  const store = new Map([["access_token", "token-de-prueba"]]);
  return {
    getItem: (key) => (store.has(key) ? store.get(key) : null),
    setItem: (key, value) => store.set(key, String(value)),
    removeItem: (key) => store.delete(key),
  };
}

const USER = { id: 3, name: "Sofía Ruiz", email: "sofia@example.com", role: "Técnico" };

const TICKET = {
  id: 1,
  title: "Impresora sin conexión",
  description: "La impresora del segundo piso no responde.",
  category: "Hardware",
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
  "editar",
  "seccion-edicion",
  "modo-edicion",
  "cancelar-edicion",
  "title",
  "description",
  "category",
  "priority",
  "guardar",
  "usuario",
  "asignar",
  "usuarios-nota",
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
    focused: false,
    children: [],
    listeners: {},
    get options() {
      return this.children;
    },
    focus() {
      this.focused = true;
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
    if (url === "/api/tickets/1/state" && method === "PATCH") {
      return resolve(overrides.state, jsonResponse(200, TICKET));
    }
    if (url === "/api/tickets/1" && method === "PATCH") {
      return resolve(overrides.edit, jsonResponse(200, TICKET));
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
    window: { location: {} },
    localStorage: createLocalStorage(),
    fetch: async () => jsonResponse(200, []),
    console: { error() {}, log() {} },
    URLSearchParams,
    Map,
  };
  vm.runInNewContext(authSource, sandbox, { filename: "auth.js" });
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
  assert.equal(
    harness.node("usuarios-nota").hidden,
    true,
    "la nota de lista vacía no corresponde a un fallo de red"
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

test("sin usuarios: nota visible, select deshabilitado y guardado bloqueado", async () => {
  const harness = createHarness(makeFetch({ users: jsonResponse(200, []) }));

  await harness.init();

  assert.equal(harness.node("usuario").disabled, true);
  assert.deepEqual(
    harness.node("usuario").children.map((option) => option.textContent),
    ["Sin asignar"]
  );
  /* El mensaje vive en el HTML estático de detalle.html. */
  const detalleHtml = fs.readFileSync(
    path.join(__dirname, "..", "detalle.html"),
    "utf8"
  );
  assert.ok(detalleHtml.includes("No hay usuarios disponibles"));
  assert.ok(detalleHtml.includes('href="usuarios.html"'));
  assert.ok(detalleHtml.includes('id="usuarios-nota"'));
  assert.equal(harness.node("usuarios-nota").hidden, false);

  harness.clearCalls();
  await harness.call("guardarAsignacion");

  assert.deepEqual(harness.urls(), [], "no debe enviar una asignación sin usuarios");
  assert.match(
    harness.node("estado-carga").textContent,
    /No hay usuarios disponibles/
  );
  assert.equal(harness.node("estado-carga").className, "estado error");
});

/* ---------------------------------------------------------------------------
   Modo edición (Tarea 20.4)
   --------------------------------------------------------------------------- */

test("HTML: botón Editar ticket, sección de edición oculta y un solo formulario", () => {
  const html = fs.readFileSync(
    path.join(__dirname, "..", "detalle.html"),
    "utf8"
  );

  assert.ok(html.includes(">Editar ticket</button>"), "botón con texto visible");
  assert.ok(html.includes('id="editar"'), "id del botón principal");
  assert.ok(
    html.includes(
      'id="seccion-edicion" class="seccion" aria-label="Edición del ticket" hidden'
    ),
    "la sección de edición empieza oculta"
  );
  assert.equal(
    html.split('id="form-editar"').length - 1,
    1,
    "solo puede existir un formulario de edición"
  );
  assert.ok(html.includes('id="cancelar-edicion"'), "acción Cancelar presente");
  assert.ok(html.includes("Editando ticket."), "indicador de modo edición en texto");
});

test("activarEdicion muestra el formulario, rellena datos y enfoca el primer campo", async () => {
  const harness = createHarness(makeFetch());
  await harness.init();

  /* Si quedó texto suelto del intento anterior, al entrar se rellena con
     los datos reales del ticket. */
  harness.node("title").value = "";
  harness.clearCalls();

  await harness.call("activarEdicion");

  assert.equal(harness.node("seccion-edicion").hidden, false, "el formulario se muestra");
  assert.equal(harness.node("editar").hidden, true, "el botón principal se oculta");
  assert.equal(harness.node("title").value, TICKET.title);
  assert.equal(harness.node("description").value, TICKET.description);
  assert.equal(harness.node("category").value, TICKET.category);
  assert.equal(harness.node("priority").value, TICKET.priority);
  assert.equal(harness.node("title").focused, true, "el foco entra al primer campo");
  assert.deepEqual(harness.urls(), [], "activar el modo no hace peticiones");
});

test("cancelarEdicion vuelve al modo consulta y descarta lo escrito", async () => {
  const harness = createHarness(makeFetch());
  await harness.init();

  harness.call("activarEdicion");
  harness.node("title").value = "Título que no debe guardarse";
  harness.clearCalls();

  harness.call("cancelarEdicion");

  assert.equal(harness.node("seccion-edicion").hidden, true, "sale del modo edición");
  assert.equal(harness.node("editar").hidden, false, "vuelve el botón Editar ticket");
  assert.equal(harness.node("title").value, TICKET.title, "los cambios se descartan");
  assert.deepEqual(harness.urls(), [], "cancelar no envía peticiones");
  assert.match(harness.node("estado-carga").textContent, /Edición cancelada/);
  assert.equal(harness.node("editar").focused, true);
});

test("guardarEdicion guarda, recarga el ticket y vuelve al modo consulta", async () => {
  const harness = createHarness(makeFetch());
  await harness.init();

  harness.call("activarEdicion");
  harness.node("title").value = "Impresora sin conexión (arreglada)";
  harness.clearCalls();

  await harness.call("guardarEdicion");

  /* PATCH + recarga silenciosa del ticket. */
  assert.deepEqual(harness.urls(), [
    "/api/tickets/1",
    "/api/tickets/1",
  ]);
  assert.equal(harness.fetchCalls[0].options.method, "PATCH");
  /* La recarga silenciosa usa fetch(url) sin opciones (GET plano). */
  assert.equal(harness.fetchCalls[1].options?.method ?? "GET", "GET");
  assert.deepEqual(JSON.parse(harness.fetchCalls[0].options.body), {
    title: "Impresora sin conexión (arreglada)",
    description: TICKET.description,
    category: TICKET.category,
    priority: TICKET.priority,
  });
  assert.equal(
    harness.node("estado-carga").textContent,
    "Cambios guardados correctamente."
  );
  assert.equal(harness.node("seccion-edicion").hidden, true, "vuelve a consulta");
  assert.equal(harness.node("editar").hidden, false);
  assert.equal(harness.node("guardar").disabled, false);
});

test("si guardar falla se mantiene el modo edición con el error visible", async () => {
  const harness = createHarness(
    makeFetch({ edit: jsonResponse(500, { detail: "Fallo interno" }) })
  );
  await harness.init();

  harness.call("activarEdicion");
  harness.clearCalls();

  await harness.call("guardarEdicion");

  assert.equal(
    harness.node("seccion-edicion").hidden,
    false,
    "sigue en modo edición"
  );
  assert.equal(harness.node("editar").hidden, true);
  assert.match(harness.node("estado-carga").textContent, /HTTP 500/);
  assert.equal(harness.node("estado-carga").className, "estado error");
  assert.equal(harness.node("guardar").disabled, false, "se puede reintentar");
});

/* Regresión (Fase 2): los endpoints de escritura exigen JWT y sin la
   cabecera Authorization responden 401 ("No se pudo guardar la
   asignación (HTTP 401)"). Todas las peticiones del detalle deben pasar
   por fetchWithAuth (auth.js), que adjunta el Bearer token. */
test("las cuatro escrituras del detalle envían el Bearer token", async () => {
  const harness = createHarness(makeFetch());
  await harness.init();
  harness.clearCalls();

  /* Editar */
  harness.call("activarEdicion");
  await harness.call("guardarEdicion");

  /* Asignar */
  harness.node("usuario").value = String(USER.id);
  await harness.call("guardarAsignacion");

  /* Cambiar estado */
  harness.node("estado-destino").value = "En proceso";
  await harness.call("cambiarEstado");

  /* Comentar */
  harness.node("contenido").value = "Comentario con token.";
  await harness.call("agregarComentario");

  const escrituras = harness.fetchCalls.filter(
    (call) => (call.options.method || "GET").toUpperCase() !== "GET"
  );
  const esperadas = [
    "/api/tickets/1",
    "/api/tickets/1/assign",
    "/api/tickets/1/state",
    "/api/tickets/1/comments",
  ];
  assert.deepEqual(
    escrituras.map((call) => call.url),
    esperadas
  );
  for (const call of escrituras) {
    const headers = call.options.headers || {};
    assert.equal(
      headers.Authorization,
      "Bearer token-de-prueba",
      `${call.options.method} ${call.url} no envía Authorization: respondería 401`
    );
  }
});

/* La cabecera Content-Type debe conservarse junto al Authorization. */
test("las escrituras envían Content-Type application/json con el token", async () => {
  const harness = createHarness(makeFetch());
  await harness.init();
  harness.clearCalls();

  harness.node("usuario").value = String(USER.id);
  await harness.call("guardarAsignacion");

  const headers = harness.fetchCalls[0].options.headers || {};
  assert.equal(headers.Authorization, "Bearer token-de-prueba");
  assert.equal(headers["Content-Type"], "application/json");
});
