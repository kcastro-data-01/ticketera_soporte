/* Menú lateral con secciones: Gestión (Tickets, Nuevo ticket, Historial),
   Administración (Métricas, Usuarios) y Soporte (Ayuda), con título chico
   en mayúsculas, línea fina entre secciones y título oculto si el rol no
   ve ninguno de sus enlaces o si el menú está plegado.
   Ejecutar con: node --test frontend/tests/menu_secciones.test.js */

"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const carpeta = path.join(__dirname, "..");
const leer = (archivo) => fs.readFileSync(path.join(carpeta, archivo), "utf8");
const css = leer("css/estilos.css");
const PAGINAS_CON_MENU = fs.readdirSync(carpeta)
  .filter((f) => f.endsWith(".html") && leer(f).includes('<nav class="menu"'));

const ESPERADO = [
  ["gestion", "Gestión", ["index.html", "crear.html", "historial.html"]],
  ["administracion", "Administración", ["metricas.html", "usuarios.html"]],
  ["soporte", "Soporte", ["ayuda.html"]],
];

const regla = (selector) => {
  const inicio = css.indexOf(`${selector} {`);
  assert.ok(inicio >= 0, selector);
  return css.slice(inicio, css.indexOf("}", inicio));
};

test("cada página con menú tiene las tres secciones con sus enlaces", () => {
  assert.equal(PAGINAS_CON_MENU.length, 8, PAGINAS_CON_MENU.join(", "));
  for (const pagina of PAGINAS_CON_MENU) {
    const nav = leer(pagina).match(/<nav class="menu"[\s\S]*?<\/nav>/)[0];
    const secciones = [...nav.matchAll(/<div class="menu-seccion" role="group" aria-labelledby="menu-([a-z]+)">\s*<p class="menu-titulo" id="menu-\1">([^<]+)<\/p>([\s\S]*?)<\/div>/g)]
      .map((m) => [m[1], m[2], [...m[3].matchAll(/<a href="([^"]+)" class="menu-enlace/g)].map((a) => a[1])]);
    assert.deepEqual(secciones, ESPERADO, pagina);
    assert.doesNotMatch(nav.replace(/<div class="menu-seccion"[\s\S]*?<\/div>/g, ""), /<a /, `${pagina}: ningún enlace suelto`);
  }
});

test("CSS: título chico en mayúsculas y gris claro, línea entre secciones", () => {
  const titulo = regla(".menu-titulo");
  assert.match(titulo, /font-size: 0\.68rem;/);
  assert.match(titulo, /text-transform: uppercase;/);
  assert.match(titulo, /color: var\(--color-menu-tenue\);/);
  assert.match(regla(".menu-seccion + .menu-seccion"), /border-top: 1px solid rgba\(255, 255, 255, 0\.12\);/);
});

test("CSS: sin enlaces visibles para el rol, la sección (y su título) no se ve", () => {
  assert.match(css, /\.menu-seccion:not\(:has\(> \.menu-enlace:not\(\[hidden\]\)\)\) \{\s*display: none;/);
});

test("CSS: plegado sin títulos; en pantallas chicas, enlaces en fila sin títulos", () => {
  assert.match(css, /body\.menu-plegado \.menu-enlace span,\n  body\.menu-plegado \.menu-titulo \{\n    display: none;/);
  const chico = css.slice(css.indexOf("@media (max-width: 900px)"));
  assert.match(chico, /\.menu-seccion \{\s*display: contents;\s*\}\s*\.menu-titulo \{\s*display: none;/);
});
