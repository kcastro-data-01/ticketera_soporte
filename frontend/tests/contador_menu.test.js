/* Contador junto a «Tickets» en el menú lateral (auth.js): Nuevos sin
   asignar para el Administrador, los suyos sin resolver para el
   Técnico; el Solicitante no lo ve y con 0 no se muestra.
   Ejecutar con: node --test frontend/tests/contador_menu.test.js */

"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const leer = (archivo) => fs.readFileSync(path.join(__dirname, "..", archivo), "utf8");
const css = leer("css/estilos.css");

const NUEVOS = [
  { id: 1, state: "Nuevo", assigned_to_id: null },
  { id: 2, state: "Nuevo", assigned_to_id: 5 },
  { id: 3, state: "Nuevo", assigned_to_id: null },
];

function el(tag) {
  return {
    tag, className: "", textContent: "", title: "", children: [], atributos: {},
    setAttribute(k, v) { this.atributos[k] = String(v); },
    appendChild(h) { this.children.push(h); return h; },
    querySelector(sel) { return sel === ".menu-contador" ? this.children.find((h) => h.className === "menu-contador") || null : null; },
  };
}

async function montar(role, respuestas = {}) {
  const enlace = el("a");
  const pedidos = [];
  const doc = {
    createElement: el,
    querySelector: (sel) => (sel === '.menu a[href="index.html"]' ? enlace : null),
  };
  const sandbox = {
    console,
    window: { location: { href: "" } },
    localStorage: { getItem: (k) => (k === "user" ? JSON.stringify({ name: "Ana", role }) : k === "access_token" ? "t" : null), setItem() {}, removeItem() {} },
    fetch: async (url) => {
      pedidos.push(url);
      const cuerpo = url.includes("summary") ? respuestas.resumen : respuestas.nuevos;
      return { ok: cuerpo !== undefined, status: cuerpo === undefined ? 500 : 200, json: async () => cuerpo };
    },
  };
  vm.runInNewContext(leer("js/auth.js"), sandbox);
  const etiqueta = await sandbox.pintarContadorTickets(doc);
  return { etiqueta, enlace, pedidos };
}

test("Administrador: cuenta los Nuevos sin asignar", async () => {
  for (const role of ["Administrador"]) {
    const { etiqueta, enlace, pedidos } = await montar(role, { nuevos: NUEVOS });
    assert.deepEqual(pedidos, ["/api/tickets?state=Nuevo"], role);
    assert.equal(etiqueta.textContent, "2");
    assert.equal(etiqueta.className, "menu-contador");
    assert.equal(enlace.children.at(-1), etiqueta, "va junto a «Tickets»");
    assert.equal(enlace.atributos["aria-label"], "Tickets: 2 nuevos sin asignar");
  }
});

test("Técnico: sus tickets sin resolver, del resumen", async () => {
  const { etiqueta, pedidos } = await montar("Técnico", { resumen: { mios_abiertos: 4 } });
  assert.deepEqual(pedidos, ["/api/tickets/summary"]);
  assert.equal(etiqueta.textContent, "4");
});

test("Solicitante, cantidad 0 o error de la API: no se muestra", async () => {
  const solicitante = await montar("Solicitante", { nuevos: NUEVOS, resumen: { mios_abiertos: 3 } });
  assert.equal(solicitante.etiqueta, null);
  assert.deepEqual(solicitante.pedidos, [], "ni siquiera consulta");
  const cero = await montar("Técnico", { resumen: { mios_abiertos: 0 } });
  assert.equal(cero.etiqueta, null);
  assert.equal(cero.enlace.children.length, 0);
  assert.equal((await montar("Administrador", {})).etiqueta, null);
});

test("CSS: etiqueta con el color principal y visible con el menú plegado", () => {
  assert.match(css, /\.menu-enlace \.menu-contador \{[^}]*background: var\(--color-primario\);[^}]*color: var\(--color-texto-inverso\);/);
  assert.match(css, /body\.menu-plegado \.menu-enlace \.menu-contador \{\s*display: inline-grid;\s*position: absolute;/);
  assert.doesNotMatch(css.slice(css.indexOf(".menu-enlace .menu-contador {"), css.indexOf("/* Botón para achicar")), /gradient/);
});
