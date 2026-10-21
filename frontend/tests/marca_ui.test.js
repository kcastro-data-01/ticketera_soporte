/* Marca: todas las páginas tienen el favicon de la empresa y las páginas
   con menú lateral muestran el nombre y el logo arriba.
   Ejecutar con: node --test frontend/tests/marca_ui.test.js */

"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const FRONTEND = path.join(__dirname, "..");
const paginas = fs.readdirSync(FRONTEND).filter((f) => f.endsWith(".html"));

test("cada página enlaza el favicon y el ícono de inicio, y los archivos existen", () => {
  assert.equal(paginas.length, 11, "9 pantallas + 404 y sin permiso");
  for (const pagina of paginas) {
    const html = fs.readFileSync(path.join(FRONTEND, pagina), "utf8");
    /* 404.html y sin-permiso.html usan rutas absolutas (/images/...). */
    assert.match(html, /<link rel="icon" type="image\/png" sizes="64x64" href="\/?images\/favicon\.png">/, pagina);
    assert.match(html, /<link rel="apple-touch-icon" href="\/?images\/apple-touch-icon\.png">/, pagina);
  }
  assert.ok(fs.existsSync(path.join(FRONTEND, "images", "favicon.png")));
  assert.ok(fs.existsSync(path.join(FRONTEND, "images", "apple-touch-icon.png")));
});

test("el menú lateral muestra el logo y el nombre de la empresa", () => {
  for (const pagina of paginas.filter((p) => !["login.html", "404.html", "sin-permiso.html"].includes(p))) {
    const html = fs.readFileSync(path.join(FRONTEND, pagina), "utf8");
    assert.match(html, /<img src="images\/logo-circular\.jpg" alt="" class="marca-logo">/, pagina);
    assert.match(html, /<span class="marca-nombre">American Data Networks<\/span>/, pagina);
  }
});
