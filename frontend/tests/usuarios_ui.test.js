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
const AUTH_PATH = path.join(__dirname, "..", "js", "auth.js");
const usuariosSource = fs.readFileSync(USUARIOS_PATH, "utf8");
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

const USER_A = {
  id: 1,
  name: "Ana Pérez",
  email: "ana@soporte.local",
  role: "Técnico",
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
  "password",
  "rol",
  "crear",
  "usuarios-estado",
  "tabla-usuarios",
  "cuerpo-usuarios",
  "estado-pagina",
  "dialogo-usuario",
  "dialogo-usuario-titulo",
  "abrir-agregar-usuario",
  "cancelar-usuario",
  "cerrar-dialogo-usuario",
  "form-editar-usuario",
  "editar-id",
  "editar-nombre",
  "editar-email",
  "editar-password",
  "editar-rol",
  "guardar-edicion",
  "cancelar-edicion",
  "estado-edicion",
];

function createNode(id) {
  return {
    id,
    textContent: "",
    className: "",
    dataset: {},
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
  return async (rawUrl, options = {}) => {
    /* La lista se pide con ?todos=true (incluye desactivados). */
    const url = rawUrl.split("?")[0];
    const method = (options.method || "GET").toUpperCase();
    /* ¿LOGIN_LOCAL? Por defecto no: sin campos de contraseña. */
    if (url === "/api/auth/config") {
      return resolve(overrides.config, jsonResponse(200, { tenant: "t", client_id: "c", login_local: false }));
    }
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
  /* Refleja <option value="Técnico" selected> del HTML real. */
  nodes.get("rol").value = "Técnico";
  /* Contraseña válida por defecto: cada prueba cambia solo lo que valida. */
  nodes.get("password").value = "clave2026";
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
    window: { location: {} },
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

  assert.deepEqual(harness.urls(), ["/api/auth/config", "/api/areas", "/api/users?todos=true"]);
  const rows = harness.node("cuerpo-usuarios").children;
  assert.equal(rows.length, 2);
  assert.deepEqual(rows[0].children.map((cell) => cell.textContent), [
    "Ana Pérez",
    "ana@soporte.local",
    "", // la celda de rol contiene la etiqueta
    "Sin departamento", // Técnico sin departamento
    "", // la celda de estado contiene el badge
    "", // la celda de acciones contiene el botón Editar
  ]);
  // Nombre con iniciales y rol como etiqueta de color.
  assert.match(rows[0].children[0].className, /con-avatar tono-avatar-\d/);
  assert.equal(rows[0].children[0].dataset.iniciales, "AP");
  const rol = rows[0].children[2].children[0];
  assert.equal(rol.className, "badge rol-tecnico");
  assert.equal(rol.textContent, "Técnico");
  const badge = rows[0].children[4].children[0];
  assert.equal(badge.className, "badge badge-activo");
  assert.equal(badge.textContent, "Activo");
  const editButton = rows[0].children[5].children[0];
  assert.equal(editButton.textContent, "Editar");
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
    "No se pudo conectar con el servidor. Verifique que esté en funcionamiento."
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

/* Con LOGIN_LOCAL=true (desarrollo) vuelven los campos de contraseña. */
const conLoginLocal = (extra = {}) =>
  makeFetch({ config: jsonResponse(200, { tenant: "t", client_id: "c", login_local: true }), ...extra });

test("contraseña corta devuelve error sin enviar (solo con LOGIN_LOCAL)", async () => {
  const harness = createHarness(conLoginLocal());
  await harness.init();

  await assertValidation(
    harness,
    (h) => {
      h.node("nombre").value = "Ana Pérez";
      h.node("email").value = "ana@soporte.local";
      h.node("password").value = "12345";
    },
    "La contraseña debe tener al menos 6 caracteres."
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
    "Seleccione un rol válido."
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

  assert.deepEqual(harness.urls(), ["/api/users", "/api/users?todos=true"]);
  assert.equal(harness.fetchCalls[0].options.method, "POST");
  /* Sin contraseña: la persona entra con su cuenta de Microsoft. */
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
  assert.equal(harness.node("password").value, "", "no deja la contraseña escrita");
  assert.equal(harness.node("rol").value, "Técnico");
  /* La ventana se cierra y el aviso queda en la página, arriba de la tabla. */
  assert.equal(
    harness.node("estado-pagina").textContent,
    "Usuario agregado correctamente."
  );
  assert.equal(harness.node("estado-pagina").className, "estado exito");
  assert.ok(!harness.node("dialogo-usuario").open, "la ventana queda cerrada");
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
    "No se pudo conectar con el servidor. Verifique que esté en funcionamiento."
  );
  assert.equal(harness.node("estado-usuario").className, "estado error");
  assert.ok(harness.consoleErrors.length > 0);
  assert.equal(harness.node("crear").disabled, false);
});

test("con LOGIN_LOCAL el alta también envía la contraseña", async () => {
  const harness = createHarness(conLoginLocal());
  await harness.init();
  harness.node("nombre").value = "Carlos Gómez";
  harness.node("email").value = "carlos@soporte.local";
  harness.clearCalls();
  await harness.crear();
  assert.equal(JSON.parse(harness.fetchCalls[0].options.body).password, "clave2026");
});

test("usuarios.html: contraseña y nueva contraseña ocultas salvo LOGIN_LOCAL", () => {
  const html = fs.readFileSync(path.join(__dirname, "..", "usuarios.html"), "utf8");
  assert.match(html, /<label class="campo solo-login-local" hidden>\s*<span>Contraseña \*<\/span>\s*<input type="password" id="password"/);
  assert.match(html, /<label class="campo solo-login-local" hidden>\s*<span>Nueva contraseña<\/span>/);
  assert.doesNotMatch(html, /id="password"[^>]*required/, "no es obligatoria si no se ve");
});


// --- Área de IT --------------------------------------------------------------

test("el departamento: «—» para el Solicitante, «Sin departamento» o su nombre para IT", () => {
  const ctx = {};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, "..", "js", "usuarios.js"), "utf8"), ctx);
  assert.equal(ctx.textoAreaUsuario({ role: "Solicitante", area_name: null }), "—");
  assert.equal(ctx.textoAreaUsuario({ role: "Técnico", area_name: null }), "Sin departamento");
  assert.equal(ctx.textoAreaUsuario({ role: "Administrador", area_name: "Redes" }), "Redes");
  const rol = { value: "Técnico" };
  const area = { value: "4" };
  assert.equal(ctx.areaElegida(rol, area), 4);
  area.value = "";
  assert.equal(ctx.areaElegida(rol, area), null, "Sin departamento se envía como null");
  rol.value = "Solicitante";
  assert.equal(ctx.areaElegida(rol, area), undefined, "al Solicitante no se le envía área");
  const campo = { hidden: false };
  const select = { value: "", disabled: false, closest: () => campo };
  ctx.mostrarCampoArea(rol, select);
  assert.deepEqual([campo.hidden, select.disabled], [true, true]);
  rol.value = "Administrador";
  ctx.mostrarCampoArea(rol, select);
  assert.deepEqual([campo.hidden, select.disabled], [false, false]);
});

test("usuarios.html tiene «Departamento» en agregar y editar, y la columna en la tabla", () => {
  const html = fs.readFileSync(path.join(__dirname, "..", "usuarios.html"), "utf8");
  assert.match(html, /<select id="area" name="area"/);
  assert.match(html, /<select id="editar-area" name="area"/);
  assert.match(html, /<th>Rol<\/th>\s*<th>Departamento<\/th>/);
});

/* ---------------------------------------------------------------------------
   Ventana para agregar y editar
   --------------------------------------------------------------------------- */

function dialogoDePrueba(harness) {
  const dialogo = harness.node("dialogo-usuario");
  dialogo.open = false;
  dialogo.showModal = function () { this.open = true; this.modal = true; };
  dialogo.close = function () { this.open = false; };
  for (const id of ["nombre", "editar-nombre"]) {
    harness.node(id).focus = function () { this.enfocado = true; };
  }
  return dialogo;
}

test("«Agregar usuario» abre la ventana vacía en modo agregar; Cancelar y ✕ la cierran", async () => {
  const harness = createHarness(makeFetch());
  await harness.init();
  const dialogo = dialogoDePrueba(harness);
  harness.node("nombre").value = "Quedó escrito";
  harness.node("estado-usuario").hidden = false;

  harness.node("abrir-agregar-usuario").listeners.click[0]();
  assert.equal(dialogo.open, true);
  assert.equal(dialogo.modal, true, "con showModal()");
  assert.equal(harness.node("dialogo-usuario-titulo").textContent, "Agregar usuario");
  assert.equal(harness.node("form-usuario").hidden, false);
  assert.equal(harness.node("form-editar-usuario").hidden, true);
  assert.equal(harness.node("nombre").value, "", "empieza vacío");
  assert.equal(harness.node("rol").value, "Técnico");
  assert.equal(harness.node("estado-usuario").hidden, true);
  assert.equal(harness.node("nombre").enfocado, true, "el foco en Nombre");

  harness.node("cancelar-usuario").listeners.click[0]();
  assert.equal(dialogo.open, false);
  harness.node("abrir-agregar-usuario").listeners.click[0]();
  harness.node("cerrar-dialogo-usuario").listeners.click[0]();
  assert.equal(dialogo.open, false);
});

test("un error al agregar queda dentro de la ventana, que sigue abierta", async () => {
  const harness = createHarness(makeFetch({ create: jsonResponse(500, {}) }));
  await harness.init();
  const dialogo = dialogoDePrueba(harness);
  harness.node("abrir-agregar-usuario").listeners.click[0]();
  harness.node("nombre").value = "Ana Pérez";
  harness.node("email").value = "ana@data.cr";
  await harness.crear();
  assert.equal(dialogo.open, true);
  assert.equal(harness.node("estado-usuario").className, "estado error");
  assert.equal(harness.node("estado-pagina").textContent, "", "en la página no aparece nada");
});

test("«Editar» usa la misma ventana con los datos del usuario; al guardar se cierra y avisa en la página", async () => {
  const harness = createHarness(makeFetch());
  await harness.init();
  const dialogo = dialogoDePrueba(harness);
  harness.call("editarUsuario", { ...USER_A, area_id: null });
  assert.equal(dialogo.open, true);
  assert.equal(harness.node("dialogo-usuario-titulo").textContent, "Editar usuario");
  assert.equal(harness.node("form-usuario").hidden, true);
  assert.equal(harness.node("form-editar-usuario").hidden, false);
  assert.equal(harness.node("editar-nombre").value, "Ana Pérez");
  assert.equal(harness.node("editar-email").value, "ana@soporte.local");
  assert.equal(harness.node("editar-nombre").enfocado, true);
  harness.call("cancelarEdicion");
  assert.equal(dialogo.open, false);
});

test("usuarios.html: la tabla primero, el botón arriba a la derecha y una sola ventana en dos columnas", () => {
  const html = fs.readFileSync(path.join(__dirname, "..", "usuarios.html"), "utf8");
  const cabecera = html.slice(html.indexOf('<header class="cabecera">'), html.indexOf("</header>"));
  assert.match(cabecera, /<div class="cabecera-acciones">\s*<button type="button" id="abrir-agregar-usuario" aria-haspopup="dialog">Agregar usuario<\/button>/);
  const main = html.slice(html.indexOf('<main class="contenido">'), html.indexOf("</main>"));
  assert.match(main, /^<main class="contenido">\s*<section class="seccion" aria-labelledby="titulo-usuarios">\s*<h2 id="titulo-usuarios">Usuarios registrados<\/h2>/);
  assert.doesNotMatch(main, /<form\b/, "el formulario ya no está en la página");
  const dialogo = html.slice(html.indexOf('<dialog id="dialogo-usuario"'), html.indexOf("</dialog>"));
  assert.match(dialogo, /^<dialog id="dialogo-usuario" class="ventana-usuario" aria-labelledby="dialogo-usuario-titulo">/);
  assert.equal((dialogo.match(/<form id="form-(usuario|editar-usuario)" class="formulario-usuario" novalidate( hidden)?>/g) || []).length, 2);
  assert.equal((dialogo.match(/<div class="campos-dos">/g) || []).length, 2, "campos en dos columnas");
  for (const prefijo of ["", "editar-"]) {
    const orden = ["nombre", "email", "rol", "area"].map((c) => dialogo.indexOf(`id="${prefijo}${c}"`));
    assert.ok(orden.every((i) => i >= 0));
    assert.deepEqual([...orden].sort((a, b) => a - b), orden, `${prefijo}: Nombre, Correo, Rol y Departamento`);
  }
  assert.equal((html.match(/placeholder="nombre@data\.cr"/g) || []).length, 2);
  assert.doesNotMatch(html, /soporte\.local/);
  assert.doesNotMatch(html, /class="ayuda-campo"/, "sin textos de ayuda largos");
  assert.match(dialogo, /<button type="button" id="cerrar-dialogo-usuario" class="ventana-cerrar" aria-label="Cerrar">/);
});

test("CSS: ventana con fondo oscuro, campos en dos columnas y una en el celular", () => {
  const css = fs.readFileSync(path.join(__dirname, "..", "css", "estilos.css"), "utf8");
  const ventana = css.slice(css.indexOf(".ventana-usuario {"), css.indexOf("}", css.indexOf(".ventana-usuario {")));
  assert.match(ventana, /width: min\(640px, calc\(100vw - 2rem\)\);/);
  assert.match(ventana, /background: var\(--color-superficie-alta\);/);
  assert.doesNotMatch(ventana, /display:/, "cerrada, la oculta el navegador");
  assert.match(css, /\.ventana-usuario::backdrop \{/);
  assert.match(css, /\.campos-dos \{\s*display: grid;\s*grid-template-columns: repeat\(2, minmax\(0, 1fr\)\);/);
  assert.match(css, /@media \(max-width: 600px\) \{\s*\.campos-dos \{\s*grid-template-columns: minmax\(0, 1fr\);/);
});

test("tablet y celular: cada usuario es una tarjeta con la etiqueta de cada dato (sin scroll de costado)", async () => {
  const harness = createHarness(makeFetch({ users: jsonResponse(200, [{ ...USER_A, area_name: "Soporte IT" }]) }));
  await harness.init();
  const celdas = harness.node("cuerpo-usuarios").children[0].children;
  assert.deepEqual(celdas.map((td) => td.dataset.label), [undefined, "Correo", "Rol", "Departamento", "Estado", undefined]);
  assert.match(celdas[0].className, /^celda-nombre con-avatar/, "el nombre conserva el avatar");
  assert.equal(celdas[5].className, "celda-acciones");
  const html = fs.readFileSync(path.join(__dirname, "..", "usuarios.html"), "utf8");
  assert.match(html, /<table id="tabla-usuarios" class="listado tabla-usuarios" hidden>/);
  const css = fs.readFileSync(path.join(__dirname, "..", "css", "estilos.css"), "utf8");
  const bloque = css.slice(css.indexOf("/* ===== Usuarios: en tablet y celular"), css.indexOf("/* ===== Usuarios: rol como etiqueta"));
  assert.match(bloque, /@media \(max-width: 900px\) \{\s*\.tabla-usuarios thead \{\s*display: none;/);
  assert.match(bloque, /\.listado\.tabla-usuarios tbody td:not\(\.celda-nombre\)::before \{\s*content: attr\(data-label\);/);
  assert.doesNotMatch(bloque, /celda-nombre::before/, "no tapa las iniciales");
});

test("cada id que busca usuarios.js existe en usuarios.html (ninguno desapareció)", () => {
  const html = fs.readFileSync(path.join(__dirname, "..", "usuarios.html"), "utf8");
  const ids = [...usuariosSource.matchAll(/getElementById\("([a-z-]+)"\)/g)].map((m) => m[1]);
  assert.ok(ids.length >= 20, ids.join(", "));
  for (const id of ids) {
    assert.match(html, new RegExp(`id="${id}"`), id);
  }
  assert.doesNotMatch(usuariosSource, /seccion-editar|seccionEditar|limpiar-usuario/, "nada de la página vieja");
});
