/* Tipografía: Inter de Google Fonts (400, 500, 600) en todas las páginas,
   con respaldo del sistema, y la misma en los gráficos de métricas.
   Ejecutar con: node --test frontend/tests/tipografia_ui.test.js */

"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const carpeta = path.join(__dirname, "..");
const leer = (archivo) => fs.readFileSync(path.join(carpeta, archivo), "utf8");
const PAGINAS = fs.readdirSync(carpeta).filter((f) => f.endsWith(".html"));
const FUENTE = '"Inter", system-ui, "Segoe UI", Roboto, Arial, sans-serif';

test("todas las páginas cargan Inter 400, 500 y 600 antes de estilos.css", () => {
  assert.ok(PAGINAS.length >= 11, PAGINAS.join(", "));
  for (const pagina of PAGINAS) {
    const html = leer(pagina);
    assert.match(
      html,
      /<link rel="preconnect" href="https:\/\/fonts\.googleapis\.com">\s*<link rel="preconnect" href="https:\/\/fonts\.gstatic\.com" crossorigin>\s*<link rel="stylesheet" href="https:\/\/fonts\.googleapis\.com\/css2\?family=Inter:wght@400;500;600&display=swap">\s*<link rel="stylesheet" href="\/?css\/estilos\.css">/,
      pagina,
    );
  }
});

test("body y gráficos usan Inter con respaldo system-ui, Segoe UI, Roboto, Arial", () => {
  assert.ok(leer("css/estilos.css").includes(`body {\n  margin: 0;\n  font-family: ${FUENTE};`));
  assert.ok(leer("js/metricas.js").includes(`const FUENTE_SITIO = '${FUENTE}';`));
});
