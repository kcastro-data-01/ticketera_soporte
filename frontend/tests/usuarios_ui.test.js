/* Tarea 20.3 — Pruebas de frontend/js/usuarios.js: carga del listado
   (éxito, vacío, errores), validaciones del formulario y alta de
   usuarios (éxito, email duplicado, datos inválidos).
   Infraestructura mínima: solo node:test de Node.js (sin librerías
   externas), misma técnica que app_errors.test.js (script real en vm).
   Ejecutar con: node --test frontend/tests/usuarios_ui.test.js */

"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const USUARIOS_PATH = path.join(__dirname, "..", "js", "usuarios.js");
const usuariosSource = fs.readFileSync(USUARIOS_PATH, "utf8");

const USER_A = {
  id: 1,
  name: "Ana Pérez",
  email: "ana@soporte.local",
  role: "Soporte",
};
const USER_B = {
  id: 2,
  name: "Carlos Gómez",
  email: "carlos@soporte.local",
  role: "Administrador",
};

const ELEMENT_IDS = [
  "estado-usuario",
  "form-usuario",
  "nombre",
  "email",
  "rol",
  "crear",
  "usuarios-estado",
  "tabla-usuarios",
  "cuerpo-usuarios",
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

/* Enruta las llamadas reales de usuarios.js. Cada override puede ser una
   respuesta o una función que devuelve la respuesta (para evolucionar el
   estado entre llamadas). */
function makeFetch(overrides = {}) {
  const resolve = (value, fallback) =>
    typeof value === "function" ? value() : value !== undefined ? value : fallback;
  return async (url, options = {}) => {
    const method = (options.method || "GET").toUpperCase();
    if (url === "/api/users" && method === "POST") {
      return resolve(overrides.create, jsonResponse(201, USER_A));
    }
    if (url === "/api/users") {
      return resolve(overrides.users, jsonResponse(200, [USER_A]));
    }
    throw new Error(`URL no soportada por el harness: ${method} ${url}`);
  };
}

function createHarness(fetchImpl) {
  const nodes = new Map(ELEMENT_IDS.map((id) => [id, createNode(id)]));
  /* Refleja <option value="Soporte" selected> del HTML real. */
  nodes.get("rol").value = "Soporte";
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
      fetchCalls.push({ url, options });
      return fetchImpl(url, options);
    },
    console: {
      error: (...args) => consoleErrors.push(args),
      log() {},
    },
  };

  vm.runInNewContext(usuariosSource, sandbox, { filename: "usuarios.js" });

  const fakeEvent = { preventDefault() {} };

  return {
    init: () => sandbox.init(),
    crear: () => sandbox.crearUsuario(fakeEvent),
    call(name, ...args) {
      assert.equal(
        typeof sandbox[name],
        "function",
        `${name} debe existir en usuarios.js`
      );
      return sandbox[name](...args);
    },
    node: (id) => nodes.get(id),
    urls: () => fetchCalls.map((call) => call.url),
    fetchCalls,
    consoleErrors,
    clearCalls: () => fetchCalls.splice(0, fetchCalls.length),
  };
}

/* ---------------------------------------------------------------------------
   Listado
   --------------------------------------------------------------------------- */

test("init lista los usuarios con nombre, correo, rol y estado", async () => {
  const harness = createHarness(makeFetch({ users: jsonResponse(200, [USER_A, USER_B]) }));

  await harness.init();

  assert.deepEqual(harness.urls(), ["/api/users"]);
  const rows = harness.node("cuerpo-usuarios").children;
  assert.equal(rows.length, 2);
  assert.deepEqual(rows[0].children.map((cell) => cell.textContent), [
    "Ana Pérez",
    "ana@soporte.local",
    "Soporte",
    "", // la celda de estado contiene el badge
  ]);
  const badge = rows[0].children[3].children[0];
  assert.equal(badge.className, "badge badge-activo");
  assert.equal(badge.textContent, "Activo");
  assert.equal(rows[1].children[0].textContent, "Carlos Gómez");
  assert.equal(harness.node("tabla-usuarios").hidden, false);
  assert.equal(harness.node("usuarios-estado").hidden, true);
});

test("init sin usuarios muestra la lista vacía", async () => {
  const harness = createHarness(makeFetch({ users: jsonResponse(200, []) }));

  await harness.init();

  assert.equal(
    harness.node("usuarios-estado").textContent,
    "No hay usuarios registrados."
  );
  assert.equal(harness.node("usuarios-estado").className, "estado vacio");
  assert.equal(harness.node("tabla-usuarios").hidden, true);
  assert.equal(harness.node("cuerpo-usuarios").children.length, 0);
});

test("init con error de conexión informa que el servidor no responde", async () => {
  const harness = createHarness(async () => {
    throw new TypeError("Failed to fetch");
  });

  await harness.init();

  assert.equal(
    harness.node("usuarios-estado").textContent,
    "No se pudo conectar con el servidor. Comprueba que está en ejecución."
  );
  assert.equal(harness.node("usuarios-estado").className, "estado error");
  assert.ok(harness.consoleErrors.length > 0);
});

test("init con error HTTP muestra el detail del backend", async () => {
  const harness = createHarness(
    makeFetch({ users: jsonResponse(500, { detail: "Fallo interno" }) })
  );

  await harness.init();

  assert.equal(
    harness.node("usuarios-estado").textContent,
    "Error de API (500): Fallo interno"
  );
  assert.equal(harness.node("usuarios-estado").className, "estado error");
});

test("init con JSON que no es una lista da respuesta inválida", async () => {
  const harness = createHarness(
    makeFetch({
      users: {
        ok: true,
        status: 200,
        json: async () => {
          throw new SyntaxError("no es JSON");
        },
      },
    })
  );

  await harness.init();

  assert.equal(
    harness.node("usuarios-estado").textContent,
    "Respuesta inválida del servidor."
  );
  assert.equal(harness.node("usuarios-estado").className, "estado error");
});

/* ---------------------------------------------------------------------------
   Validaciones del formulario (sin peticiones)
   --------------------------------------------------------------------------- */

async function assertValidation(harness, fill, expectedMessage) {
  fill(harness);
  harness.clearCalls();
  await harness.crear();

  assert.deepEqual(harness.urls(), [], "la validación no debe enviar peticiones");
  assert.equal(harness.node("estado-usuario").textContent, expectedMessage);
  assert.equal(harness.node("estado-usuario").className, "estado error");
  assert.equal(harness.node("crear").disabled, false);
}

test("nombre vacío devuelve error sin enviar", async () => {
  const harness = createHarness(makeFetch());
  await harness.init();

  await assertValidation(
    harness,
    (h) => {
      h.node("nombre").value = "   ";
      h.node("email").value = "ana@soporte.local";
    },
    "El nombre no puede estar vacío."
  );
});

test("email vacío devuelve error sin enviar", async () => {
  const harness = createHarness(makeFetch());
  await harness.init();

  await assertValidation(
    harness,
    (h) => {
      h.node("nombre").value = "Ana Pérez";
      h.node("email").value = "  ";
    },
    "El correo electrónico no puede estar vacío."
  );
});

test("email inválido devuelve error sin enviar", async () => {
  const harness = createHarness(makeFetch());
  await harness.init();

  await assertValidation(
    harness,
    (h) => {
      h.node("nombre").value = "Ana Pérez";
      h.node("email").value = "no-es-un-correo";
    },
    "El correo electrónico no tiene un formato válido."
  );
});

test("rol inválido devuelve error sin enviar", async () => {
  const harness = createHarness(makeFetch());
  await harness.init();

  await assertValidation(
    harness,
    (h) => {
      h.node("nombre").value = "Ana Pérez";
      h.node("email").value = "ana@soporte.local";
      h.node("rol").value = "SuperUsuario";
    },
    "Selecciona un rol válido."
  );
});

/* ---------------------------------------------------------------------------
   Alta de usuarios
   --------------------------------------------------------------------------- */

test("crear usuario envía los datos, recarga la lista y limpia el formulario", async () => {
  let store = [USER_A];
  const harness = createHarness(
    makeFetch({
      users: () => jsonResponse(200, store),
      create: () => {
        store = [...store, USER_B];
        return jsonResponse(201, USER_B);
      },
    })
  );
  await harness.init();
  harness.node("nombre").value = "  Carlos Gómez ";
  harness.node("email").value = " carlos@soporte.local ";
  harness.node("rol").value = "Administrador";
  harness.clearCalls();

  await harness.crear();

  assert.deepEqual(harness.urls(), ["/api/users", "/api/users"]);
  assert.equal(harness.fetchCalls[0].options.method, "POST");
  assert.deepEqual(JSON.parse(harness.fetchCalls[0].options.body), {
    name: "Carlos Gómez",
    email: "carlos@soporte.local",
    role: "Administrador",
  });
  /* La lista se recarga sola: el usuario nuevo aparece sin recargar. */
  const rows = harness.node("cuerpo-usuarios").children;
  assert.equal(rows.length, 2);
  assert.equal(rows[1].children[0].textContent, "Carlos Gómez");
  assert.equal(harness.node("nombre").value, "");
  assert.equal(harness.node("email").value, "");
  assert.equal(harness.node("rol").value, "Soporte");
  assert.equal(
    harness.node("estado-usuario").textContent,
    "Usuario agregado correctamente."
  );
  assert.equal(harness.node("estado-usuario").className, "estado exito");
  assert.equal(harness.node("crear").disabled, false);
});

test("email duplicado (409) muestra el detail y no recarga la lista", async () => {
  const harness = createHarness(
    makeFetch({
      create: jsonResponse(409, {
        detail: "El email ana@soporte.local ya está registrado",
      }),
    })
  );
  await harness.init();
  harness.node("nombre").value = "Otra Persona";
  harness.node("email").value = "ana@soporte.local";
  harness.clearCalls();

  await harness.crear();

  assert.deepEqual(harness.urls(), ["/api/users"], "solo el POST fallido");
  assert.equal(
    harness.node("estado-usuario").textContent,
    "El email ana@soporte.local ya está registrado"
  );
  assert.equal(harness.node("estado-usuario").className, "estado error");
  assert.equal(harness.node("email").value, "ana@soporte.local", "conserva lo escrito");
  assert.equal(harness.node("crear").disabled, false);
});

test("datos inválidos (422) muestran los errores de campo", async () => {
  const harness = createHarness(
    makeFetch({
      create: jsonResponse(422, {
        detail: [{ loc: ["body", "email"], msg: "el email no tiene un formato válido" }],
      }),
    })
  );
  await harness.init();
  harness.node("nombre").value = "Ana Pérez";
  harness.node("email").value = "ana@soporte.local";
  harness.clearCalls();

  await harness.crear();

  assert.deepEqual(harness.urls(), ["/api/users"]);
  assert.equal(
    harness.node("estado-usuario").textContent,
    "email: el email no tiene un formato válido"
  );
  assert.equal(harness.node("estado-usuario").className, "estado error");
});

test("error de conexión al crear informa que el servidor no responde", async () => {
  let calls = 0;
  const harness = createHarness(async (url, options) => {
    calls += 1;
    if (calls === 1) return jsonResponse(200, [USER_A]);
    throw new TypeError("Failed to fetch");
  });
  await harness.init();
  harness.node("nombre").value = "Ana Pérez";
  harness.node("email").value = "ana@soporte.local";
  harness.clearCalls();

  await harness.crear();

  assert.equal(harness.fetchCalls.length, 1, "solo el POST");
  assert.equal(
    harness.node("estado-usuario").textContent,
    "No se pudo conectar con el servidor. Comprueba que está en ejecución."
  );
  assert.equal(harness.node("estado-usuario").className, "estado error");
  assert.ok(harness.consoleErrors.length > 0);
  assert.equal(harness.node("crear").disabled, false);
});
