/* Inicio de sesión solo con Microsoft (login.html): un botón, MSAL.js con
   versión fija, scopes mínimos y el id_token que va al backend. El
   formulario de contraseña solo con LOGIN_LOCAL (desarrollo).
   Ejecutar con: node --test frontend/tests/login_microsoft.test.js */

"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const html = fs.readFileSync(path.join(__dirname, "..", "login.html"), "utf8");
const script = fs.readFileSync(path.join(__dirname, "..", "js", "login.js"), "utf8");

test("login.html: un solo botón de Microsoft, MSAL con versión fija y sin registro", () => {
  assert.match(html, /<button type="button" id="btn-microsoft" class="btn-primario btn-microsoft">[\s\S]*?Iniciar sesión con Microsoft<\/button>/);
  assert.match(html, /<script src="https:\/\/cdn\.jsdelivr\.net\/npm\/@azure\/msal-browser@4\.30\.0\/lib\/msal-browser\.min\.js"\s+integrity="sha384-[^"]+"\s+crossorigin="anonymous"><\/script>/);
  assert.match(script, /const SCOPES = \["openid", "profile", "email", "User\.Read"\];/);
  assert.match(script, /loginRedirect\(/, "flujo de código con PKCE (redirect)");
  assert.doesNotMatch(html, /form-register|Crear cuenta|\/register|\/setup|registro=1/);
  assert.match(html, /<form id="form-login" class="auth-form">/, "contraseña oculta por defecto");
});

function montar({ config = { tenant: "data.cr", client_id: "app-123", login_local: false }, respuesta = null,
  almacen = {}, search = "", cuentas = [], silencioso = null, sso = null, estadoMicrosoft = 200 } = {}) {
  const nodos = new Map();
  const nodo = (id) => {
    if (!nodos.has(id)) {
      const clases = new Set();
      nodos.set(id, {
        id, value: "", textContent: "", innerHTML: "", disabled: false, dataset: {}, listeners: {},
        classList: { add: (c) => clases.add(c), remove: (c) => clases.delete(c), contains: (c) => clases.has(c) },
        addEventListener(t, fn) { (this.listeners[t] = this.listeners[t] || []).push(fn); },
      });
    }
    return nodos.get(id);
  };
  const pedidos = [];
  const guardado = new Map(Object.entries(almacen));
  const silenciosos = [];
  const msalCreado = [];
  const redirecciones = [];
  const sandbox = {
    document: { getElementById: nodo, querySelectorAll: () => [] },
    window: { location: { origin: "http://localhost:8000", href: "login.html", search } },
    localStorage: { setItem: (k, v) => guardado.set(k, v), getItem: (k) => guardado.get(k) ?? null,
      removeItem: (k) => guardado.delete(k) },
    sessionStorage: { setItem() {}, getItem: () => null, removeItem() {} },
    URLSearchParams,
    atob: (t) => Buffer.from(t, "base64").toString("binary"),
    setTimeout: (fn) => fn(),
    fetch: async (url, opciones = {}) => {
      pedidos.push({ url, opciones });
      if (url === "/api/auth/config") return { ok: true, status: 200, json: async () => config };
      if (url === "/api/auth/microsoft") {
        return { ok: estadoMicrosoft === 200, status: estadoMicrosoft, json: async () => ({ access_token: "token-app" }) };
      }
      if (url === "/api/auth/me") return { ok: true, status: 200, json: async () => ({ id: 1, name: "Kristin", role: "Administrador" }) };
      throw new Error(url);
    },
  };
  sandbox.window.msal = sandbox.msal = {
    PublicClientApplication: {
      createPublicClientApplication: async (cfg) => {
        msalCreado.push(cfg);
        return {
          handleRedirectPromise: async () => respuesta,
          loginRedirect: async (pedido) => redirecciones.push(pedido),
          getAllAccounts: () => cuentas,
          acquireTokenSilent: async (pedido) => {
            silenciosos.push(["acquireTokenSilent", pedido]);
            if (!silencioso) throw new Error("interaction_required");
            return silencioso;
          },
          ssoSilent: async (pedido) => {
            silenciosos.push(["ssoSilent", pedido]);
            if (!sso) throw new Error("login_required");
            return sso;
          },
        };
      },
    },
  };
  vm.createContext(sandbox);
  vm.runInContext(script, sandbox);
  return { nodo, pedidos, guardado, msalCreado, redirecciones, sandbox, silenciosos };
}

const esperar = async () => { for (let i = 0; i < 10; i += 1) await new Promise((r) => setImmediate(r)); };

test("MSAL usa la app y el tenant de la empresa; el botón inicia sesión con los scopes", async () => {
  const p = montar();
  await esperar();
  assert.deepEqual(JSON.parse(JSON.stringify(p.msalCreado[0].auth)), {
    clientId: "app-123",
    authority: "https://login.microsoftonline.com/data.cr",
    redirectUri: "http://localhost:8000/login.html",
  });
  assert.equal(p.msalCreado[0].cache.cacheLocation, "localStorage", "la cuenta se recuerda entre pestañas");
  p.nodo("btn-microsoft").listeners.click[0]();
  await esperar();
  assert.deepEqual([...p.redirecciones[0].scopes], ["openid", "profile", "email", "User.Read"]);
  assert.equal(p.nodo("form-login").classList.contains("activo"), false, "sin LOGIN_LOCAL no hay contraseña");
});

test("al volver de Microsoft manda el id_token al backend y guarda la sesión de la app", async () => {
  const p = montar({ respuesta: { idToken: "id-token-de-microsoft" } });
  await esperar();
  const login = p.pedidos.find((x) => x.url === "/api/auth/microsoft");
  assert.deepEqual(JSON.parse(login.opciones.body), { id_token: "id-token-de-microsoft" });
  assert.equal(p.guardado.get("access_token"), "token-app");
  assert.equal(JSON.parse(p.guardado.get("user")).role, "Administrador");
  assert.equal(p.sandbox.window.location.href, "index.html");
});

test("con LOGIN_LOCAL se muestra el formulario de contraseña", async () => {
  const p = montar({ config: { tenant: "data.cr", client_id: "app-123", login_local: true } });
  await esperar();
  assert.equal(p.nodo("form-login").classList.contains("activo"), true);
});


// --- Volver a entrar en silencio (sesión vencida) ---------------------------------

const AHORA = Date.now();
const CUENTA = { username: "ksanchez@data.cr", homeAccountId: "abc" };

test("sesión vencida y cuenta de Microsoft conectada: entra sin pedir nada y vuelve a la página", async () => {
  const inicio = AHORA - 2 * 3600 * 1000;
  const p = montar({
    almacen: { sesion_cierre: "vencida", sesion_inicio: String(inicio) },
    search: `?volver=${encodeURIComponent("detalle.html?id=5")}`,
    cuentas: [CUENTA],
    silencioso: { idToken: "id-token-silencioso" },
  });
  await esperar();
  assert.equal(p.silenciosos[0][0], "acquireTokenSilent");
  assert.equal(p.silenciosos[0][1].account, CUENTA);
  assert.equal(p.silenciosos[0][1].forceRefresh, true);
  const login = p.pedidos.find((x) => x.url === "/api/auth/microsoft");
  assert.deepEqual(JSON.parse(login.opciones.body), { id_token: "id-token-silencioso", inicio: Math.floor(inicio / 1000) },
    "el máximo de horas sigue contando desde el inicio anterior");
  assert.equal(p.sandbox.window.location.href, "detalle.html?id=5");
  assert.equal(p.guardado.has("sesion_cierre"), false);
  assert.equal(p.redirecciones.length, 0, "sin ir a la página de Microsoft");
});

test("sin caché de MSAL usa ssoSilent con el iframe que vuelve a msal/silencioso.html", async () => {
  const p = montar({
    almacen: { sesion_cierre: "vencida", sesion_inicio: String(AHORA - 60000) },
    sso: { idToken: "id-token-sso" },
  });
  await esperar();
  assert.deepEqual(p.silenciosos.map(([n]) => n), ["ssoSilent"]);
  assert.equal(p.silenciosos[0][1].redirectUri, "http://localhost:8000/msal/silencioso.html");
  assert.equal(p.sandbox.window.location.href, "index.html");
});

test("si entrar en silencio falla, queda el botón de siempre con el aviso de sesión vencida", async () => {
  const p = montar({ almacen: { sesion_cierre: "vencida", sesion_inicio: String(AHORA - 60000) }, cuentas: [CUENTA] });
  await esperar();
  assert.deepEqual(p.silenciosos.map(([n]) => n), ["acquireTokenSilent", "ssoSilent"]);
  assert.equal(p.sandbox.window.location.href, "login.html");
  assert.equal(p.nodo("btn-microsoft").disabled, false);
  assert.match(p.nodo("auth-success").textContent, /venció/);
});

for (const [motivo, mensaje] of [["inactividad", "Su sesión se cerró por inactividad."],
  ["maxima", "Su sesión llegó al máximo de horas permitido. Inicie sesión nuevamente."],
  ["manual", ""]]) {
  test(`cerrada por «${motivo}»: no entra en silencio${mensaje ? " y lo dice" : ""}`, async () => {
    const p = montar({ almacen: { sesion_cierre: motivo, sesion_inicio: String(AHORA - 60000) },
      cuentas: [CUENTA], silencioso: { idToken: "x" }, sso: { idToken: "x" } });
    await esperar();
    assert.equal(p.silenciosos.length, 0);
    assert.equal(p.pedidos.some((x) => x.url === "/api/auth/microsoft"), false);
    assert.equal(p.nodo("auth-success").textContent, mensaje);
  });
}

test("pasado el máximo de horas desde el inicio no entra en silencio", async () => {
  const p = montar({ almacen: { sesion_cierre: "vencida", sesion_inicio: String(AHORA - 10 * 3600 * 1000 - 1000) },
    cuentas: [CUENTA], silencioso: { idToken: "x" } });
  await esperar();
  assert.equal(p.silenciosos.length, 0);
  assert.equal(p.guardado.get("sesion_cierre"), "maxima");
  assert.match(p.nodo("auth-success").textContent, /máximo de horas/);
});

test("?volver= solo acepta una página propia", async () => {
  for (const malo of ["https://otro.sitio/x.html", "//otro.sitio/x.html", "login.html", "../x.html", "javascript:alert(1)"]) {
    const p = montar({ almacen: { sesion_cierre: "vencida", sesion_inicio: String(AHORA - 60000) },
      search: `?volver=${encodeURIComponent(malo)}`, cuentas: [CUENTA], silencioso: { idToken: "x" } });
    await esperar();
    assert.equal(p.sandbox.window.location.href, "index.html", malo);
  }
});
