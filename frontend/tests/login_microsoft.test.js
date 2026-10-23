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
const script = html.slice(html.lastIndexOf("<script>") + "<script>".length, html.lastIndexOf("</script>"));

test("login.html: un solo botón de Microsoft, MSAL con versión fija y sin registro", () => {
  assert.match(html, /<button type="button" id="btn-microsoft" class="btn-primario btn-microsoft">[\s\S]*?Iniciar sesión con Microsoft<\/button>/);
  assert.match(html, /<script src="https:\/\/cdn\.jsdelivr\.net\/npm\/@azure\/msal-browser@4\.30\.0\/lib\/msal-browser\.min\.js"\s+integrity="sha384-[^"]+"\s+crossorigin="anonymous"><\/script>/);
  assert.match(script, /const SCOPES = \["openid", "profile", "email", "User\.Read"\];/);
  assert.match(script, /loginRedirect\(/, "flujo de código con PKCE (redirect)");
  assert.doesNotMatch(html, /form-register|Crear cuenta|\/register|\/setup|registro=1/);
  assert.match(html, /<form id="form-login" class="auth-form">/, "contraseña oculta por defecto");
});

function montar({ config = { tenant: "data.cr", client_id: "app-123", login_local: false }, respuesta = null } = {}) {
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
  const guardado = new Map();
  const msalCreado = [];
  const redirecciones = [];
  const sandbox = {
    document: { getElementById: nodo, querySelectorAll: () => [] },
    window: { location: { origin: "http://localhost:8000", href: "login.html" } },
    localStorage: { setItem: (k, v) => guardado.set(k, v), getItem: (k) => guardado.get(k) ?? null },
    setTimeout: (fn) => fn(),
    fetch: async (url, opciones = {}) => {
      pedidos.push({ url, opciones });
      if (url === "/api/auth/config") return { ok: true, status: 200, json: async () => config };
      if (url === "/api/auth/microsoft") return { ok: true, status: 200, json: async () => ({ access_token: "token-app" }) };
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
        };
      },
    },
  };
  vm.createContext(sandbox);
  vm.runInContext(script, sandbox);
  return { nodo, pedidos, guardado, msalCreado, redirecciones, sandbox };
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
