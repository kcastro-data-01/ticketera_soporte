/* Seguridad de lo que se publica en el navegador: sin código inline (la CSP
   no lo permite), cabeceras de seguridad en vercel.json y ningún secreto en
   frontend/.
   Ejecutar con: node --test frontend/tests/seguridad_web.test.js */

"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const FRONTEND = path.join(__dirname, "..");
const paginas = fs.readdirSync(FRONTEND).filter((n) => n.endsWith(".html"));

/* Archivos que publica Vercel: todo frontend/ menos tests/ (.vercelignore). */
function publicados(dir = FRONTEND) {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((e) => {
    const ruta = path.join(dir, e.name);
    if (e.isDirectory()) return e.name === "tests" ? [] : publicados(ruta);
    return /\.(html|js|css|txt|json)$/.test(e.name) ? [ruta] : [];
  });
}

test("ninguna página tiene scripts, estilos ni manejadores inline", () => {
  for (const pagina of paginas) {
    const html = fs.readFileSync(path.join(FRONTEND, pagina), "utf8");
    assert.doesNotMatch(html, /<script(?![^>]*\bsrc=)[^>]*>/, `${pagina}: <script> inline`);
    assert.doesNotMatch(html, /<style[\s>]/, `${pagina}: <style>`);
    assert.doesNotMatch(html, /\sstyle="/, `${pagina}: atributo style`);
    assert.doesNotMatch(html, /\son[a-z]+="/, `${pagina}: manejador on*=`);
    assert.doesNotMatch(html, /javascript:/i, `${pagina}: enlace javascript:`);
  }
});

test("los scripts externos usan versión fija y hash de integridad", () => {
  for (const pagina of paginas) {
    const html = fs.readFileSync(path.join(FRONTEND, pagina), "utf8");
    for (const [etiqueta] of html.matchAll(/<script[^>]*src="https?:[^>]*>/g)) {
      assert.match(etiqueta, /integrity="sha384-[^"]+"/, `${pagina}: ${etiqueta}`);
      assert.match(etiqueta, /crossorigin="anonymous"/, `${pagina}: ${etiqueta}`);
    }
  }
});

test("vercel.json manda CSP estricta y las cabeceras de seguridad", () => {
  const config = JSON.parse(fs.readFileSync(path.join(FRONTEND, "..", "vercel.json"), "utf8"));
  const bloque = config.headers.find((h) => h.source === "/(.*)");
  const cabeceras = Object.fromEntries(bloque.headers.map((h) => [h.key, h.value]));
  assert.equal(cabeceras["X-Content-Type-Options"], "nosniff");
  assert.equal(cabeceras["X-Frame-Options"], "DENY");
  assert.equal(cabeceras["Referrer-Policy"], "same-origin");
  assert.match(cabeceras["Strict-Transport-Security"], /^max-age=\d{8,}/);
  // Primero se publica en modo de solo aviso (Report-Only); después pasa a
  // Content-Security-Policy con el mismo valor.
  const csp = cabeceras["Content-Security-Policy"] || cabeceras["Content-Security-Policy-Report-Only"];
  assert.ok(csp, "falta Content-Security-Policy (o su versión Report-Only)");
  assert.doesNotMatch(csp, /unsafe-inline|unsafe-eval|\*/);
  for (const directiva of ["default-src 'self'", "object-src 'none'", "base-uri 'none'", "frame-ancestors 'none'", "form-action 'self'"]) {
    assert.ok(csp.includes(directiva), directiva);
  }
  // Lo que usa la app: MSAL (jsDelivr), Chart.js (cdnjs), Google Fonts,
  // miniaturas de adjuntos (blob:) y el canje de código de Microsoft.
  const scriptSrc = csp.match(/script-src ([^;]+)/)[1];
  for (const html of paginas.map((p) => fs.readFileSync(path.join(FRONTEND, p), "utf8"))) {
    for (const [, origen] of html.matchAll(/<script[^>]*src="(https:\/\/[^/"]+)/g)) {
      assert.ok(scriptSrc.includes(origen), `script-src no permite ${origen}`);
    }
  }
  assert.match(csp, /img-src [^;]*blob:/);
  assert.match(csp, /connect-src [^;]*https:\/\/login\.microsoftonline\.com/);
});

test("ningún archivo publicado contiene secretos", () => {
  const patrones = [
    /postgres(ql)?:\/\/[^"'\s]*@/i,
    /\bsk-[A-Za-z0-9_-]{20,}/,
    /\bgsk_[A-Za-z0-9]{20,}/,
    /CRON_SECRET|JWT_SECRET|DATABASE_URL|client_secret/i,
    /-----BEGIN [A-Z ]*PRIVATE KEY-----/,
    /\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\./, // JWT
  ];
  for (const archivo of publicados()) {
    const texto = fs.readFileSync(archivo, "utf8");
    for (const patron of patrones) {
      assert.doesNotMatch(texto, patron, path.relative(FRONTEND, archivo));
    }
  }
});

/* guardia.js reemplaza a las guardas inline: mismo comportamiento. */
function cargarGuardia(dataset, { permitido = true } = {}) {
  const listeners = [];
  const llamadas = [];
  const sandbox = {
    document: {
      currentScript: { dataset },
      addEventListener: (tipo, fn) => listeners.push([tipo, fn]),
    },
    requireAuth: () => llamadas.push("auth"),
    requirePermiso: (p) => { llamadas.push(p); return permitido; },
  };
  vm.runInNewContext(fs.readFileSync(path.join(FRONTEND, "js", "guardia.js"), "utf8"), sandbox);
  assert.equal(listeners.length, 1);
  assert.equal(listeners[0][0], "DOMContentLoaded");
  let cortado = false;
  listeners[0][1]({ stopImmediatePropagation: () => { cortado = true; } });
  return { llamadas, cortado };
}

test("guardia.js: sin data-permiso exige sesión", () => {
  assert.deepEqual(cargarGuardia({}), { llamadas: ["auth"], cortado: false });
});

test("guardia.js: sin el permiso corta la inicialización de la página", () => {
  assert.deepEqual(cargarGuardia({ permiso: "metricas" }, { permitido: false }), { llamadas: ["metricas"], cortado: true });
  assert.deepEqual(cargarGuardia({ permiso: "metricas" }), { llamadas: ["metricas"], cortado: false });
});

test("cada página carga sus guardas con guardia.js, sin defer", () => {
  const esperadas = {
    "historial.html": ["historial_global"], "metricas.html": ["metricas"], "departamentos.html": ["departamentos"],
    "usuarios.html": ["usuarios", ""], "index.html": [""], "crear.html": [""],
    "cuenta.html": [""], "detalle.html": [""], "ayuda.html": [""],
  };
  for (const [pagina, permisos] of Object.entries(esperadas)) {
    const html = fs.readFileSync(path.join(FRONTEND, pagina), "utf8");
    const guardas = [...html.matchAll(/<script src="js\/guardia\.js"(?: data-permiso="([a-z_]+)")?><\/script>/g)];
    assert.deepEqual(guardas.map((m) => m[1] || ""), permisos, pagina);
  }
});
