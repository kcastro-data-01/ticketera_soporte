/* Scripts y hojas de estilo propios con ?v=: todas las páginas piden la
   misma versión, para que el navegador no mezcle un .js viejo guardado con
   el HTML nuevo (pasó en Ayuda y en Usuarios: los botones no hacían nada).
   El servidor además manda «Cache-Control: no-cache» (backend/main.py).
   Al cambiar un .js o .css, se sube la versión en todas las páginas.
   Ejecutar con: node --test frontend/tests/version_recursos.test.js */

"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const RAIZ = path.join(__dirname, "..");
const PAGINAS = fs.readdirSync(RAIZ).filter((f) => f.endsWith(".html"));
const leer = (f) => fs.readFileSync(path.join(RAIZ, f), "utf8");
// Cada src/href a un .js o .css propio (no los de CDN ni Google Fonts).
const RECURSO = /(?:src|href)="((?:js|css)\/[a-z_-]+\.(?:js|css))(\?v=([\w-]+))?"/g;

test("cada script y hoja de estilo propia lleva ?v=, la misma en todas las páginas", () => {
  assert.ok(PAGINAS.length >= 12, PAGINAS.join(", "));
  const versiones = new Set();
  for (const pagina of PAGINAS) {
    const recursos = [...leer(pagina).matchAll(RECURSO)];
    assert.ok(recursos.length > 0, pagina);
    for (const [, archivo, conVersion, version] of recursos) {
      assert.ok(conVersion, `${pagina}: ${archivo} sin ?v=`);
      versiones.add(version);
    }
  }
  assert.equal(versiones.size, 1, `una sola versión: ${[...versiones].join(", ")}`);
});

test("cada archivo pedido existe", () => {
  for (const pagina of PAGINAS) {
    for (const [, archivo] of leer(pagina).matchAll(RECURSO)) {
      assert.ok(fs.existsSync(path.join(RAIZ, archivo)), `${pagina}: ${archivo}`);
    }
  }
});

test("usuarios.html carga auth.js antes que usuarios.js, diferidos, y la guarda sin defer", () => {
  const html = leer("usuarios.html");
  const scripts = [...html.matchAll(/<script src="js\/([a-z]+)\.js\?v=[\w-]+"([^>]*)><\/script>/g)].map((m) => [m[1], m[2].trim()]);
  const orden = scripts.map(([nombre]) => nombre);
  assert.ok(orden.indexOf("auth") < orden.indexOf("usuarios"), orden.join(", "));
  assert.deepEqual(scripts.find(([n]) => n === "usuarios"), ["usuarios", "defer"]);
  assert.deepEqual(scripts.find(([n]) => n === "auth"), ["auth", "defer"]);
  assert.deepEqual(scripts.filter(([n]) => n === "guardia").map(([, a]) => a), ['data-permiso="usuarios"', ""]);
});
