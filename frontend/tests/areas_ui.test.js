/* Áreas de IT en el navegador: pantalla «Áreas de IT», «Asignar a» solo con
   Técnicos y Administradores, «Cambiar área» en el detalle, el área en el
   historial y los selectores de área.
   Ejecutar con: node --test frontend/tests/areas_ui.test.js */

"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const leer = (archivo) => fs.readFileSync(path.join(__dirname, "..", archivo), "utf8");

function nodo(id = "") {
  return {
    id, textContent: "", className: "", hidden: false, disabled: false, value: "", checked: false,
    children: [], listeners: {}, dataset: {},
    get options() { return this.children; },
    addEventListener(t, fn) { (this.listeners[t] = this.listeners[t] || []).push(fn); },
    appendChild(h) { this.children.push(h); return h; },
    append(...hs) { this.children.push(...hs); },
    replaceChildren(...hs) { this.children = hs; },
    focus() {}, reset() {}, setAttribute() {}, scrollIntoView() {},
    classList: { add() {}, remove() {}, toggle() {}, contains: () => false },
  };
}

function sandboxCon(rol, fetchImpl, ids = []) {
  const nodos = new Map(ids.map((id) => [id, nodo(id)]));
  const llamadas = [];
  const sesion = JSON.stringify({ id: 1, name: "Quien mira", role: rol });
  const sandbox = {
    document: {
      getElementById: (id) => nodos.get(id),
      createElement: (tag) => nodo(tag),
      addEventListener() {},
      querySelectorAll: () => [],
    },
    window: { location: { search: "?id=7", href: "detalle.html?id=7" } },
    localStorage: { getItem: (k) => (k === "access_token" ? "t" : k === "user" ? sesion : null), setItem() {}, removeItem() {} },
    fetch: async (url, opciones = {}) => { llamadas.push({ url, opciones }); return fetchImpl(url, opciones); },
    console: { error() {}, log() {} },
    URLSearchParams, Map,
  };
  vm.runInNewContext(leer("js/auth.js"), sandbox, { filename: "auth.js" });
  return { sandbox, nodos, llamadas };
}

const respuesta = (status, cuerpo) => ({ ok: status < 300, status, json: async () => cuerpo });

// --- auth.js ---------------------------------------------------------------------

test("permisos: áreas solo Administrador; cambiar el área, Administrador y Técnico", () => {
  for (const [rol, areas, cambiar] of [["Administrador", true, true], ["Técnico", false, true], ["Solicitante", false, false]]) {
    const { sandbox } = sandboxCon(rol, async () => respuesta(200, []));
    assert.equal(sandbox.puede("areas"), areas, rol);
    assert.equal(sandbox.puede("cambiar_area"), cambiar, rol);
  }
});

test("llenarSelectAreas: «Todas», «Sin área» y las áreas (las desactivadas marcadas)", () => {
  const { sandbox } = sandboxCon("Administrador", async () => respuesta(200, []));
  const select = nodo("area");
  sandbox.llenarSelectAreas(select, [{ id: 2, name: "Redes", is_active: true }, { id: 5, name: "Viejas", is_active: false }],
    { primera: "Todas", sinArea: true });
  assert.deepEqual(select.children.map((o) => [o.value, o.textContent]),
    [["", "Todas"], ["sin", "Sin área"], ["2", "Redes"], ["5", "Viejas (desactivada)"]]);
});

test("cargarAreas pide las activas (o todas) y devuelve [] si falla", async () => {
  const { sandbox, llamadas } = sandboxCon("Administrador", async (url) =>
    (url.includes("todas") ? respuesta(500, {}) : respuesta(200, [{ id: 1, name: "Redes" }])));
  assert.equal((await sandbox.cargarAreas()).length, 1);
  assert.deepEqual(JSON.parse(JSON.stringify(await sandbox.cargarAreas(true))), []);
  assert.deepEqual(llamadas.map((l) => l.url), ["/api/areas", "/api/areas?todas=true"]);
});

test("el historial muestra el cambio de área", () => {
  const { sandbox } = sandboxCon("Técnico", async () => respuesta(200, []));
  assert.deepEqual({ ...sandbox.describirHistorial({ action: "area_changed", old_value: "Redes", new_value: "Infraestructura" }) },
    { accion: "Cambió el área", detalle: "Redes → Infraestructura" });
  assert.equal(sandbox.describirHistorial({ action: "area_changed", old_value: null, new_value: "Redes" }).detalle,
    "Sin área → Redes");
});

// --- Detalle -------------------------------------------------------------------

const IDS_DETALLE = ["usuario", "usuarios-nota", "area-destino", "area-reasignar", "cambiar-area", "estado-carga",
  "guardar", "editar", "cancelar-edicion", "asignar", "comentar", "historial"];

function detalle(rol, fetchImpl) {
  const h = sandboxCon(rol, fetchImpl, IDS_DETALLE);
  vm.runInNewContext(leer("js/detalle.js"), h.sandbox, { filename: "detalle.js" });
  vm.runInNewContext("ticketId = 7;", h.sandbox);
  return h;
}

test("«Asignar a» solo ofrece Técnicos y Administradores, con su área", () => {
  const { sandbox, nodos } = detalle("Administrador", async () => respuesta(200, {}));
  sandbox.renderUsuarios([
    { id: 1, name: "Ana", role: "Administrador", area_name: null },
    { id: 2, name: "Pedro", role: "Técnico", area_name: "Redes" },
    { id: 3, name: "Sofía", role: "Solicitante", area_name: null },
  ]);
  assert.deepEqual(nodos.get("usuario").children.map((o) => [o.value, o.textContent]),
    [["", "Sin asignar"], ["1", "Ana"], ["2", "Pedro · Redes"]]);
});

test("un ticket viejo asignado a un Solicitante muestra su nombre para reasignarlo", () => {
  const { sandbox, nodos } = detalle("Administrador", async () => respuesta(200, {}));
  sandbox.renderUsuarios([{ id: 2, name: "Pedro", role: "Técnico" }, { id: 3, name: "Sofía", role: "Solicitante" }]);
  sandbox.marcarAsignadoActual({ assigned_to_id: 3 });
  const opcion = nodos.get("usuario").children.at(-1);
  assert.deepEqual([opcion.value, opcion.textContent, opcion.disabled], ["3", "Sofía (Solicitante: reasígnelo)", true]);
  assert.equal(nodos.get("usuario").value, "3");
});

test("«Cambiar área» envía el área y la casilla de reasignar", async () => {
  const { sandbox, nodos, llamadas } = detalle("Técnico", async (url, op) =>
    (op.method === "PATCH" ? respuesta(200, { id: 7, area_id: 4, area_name: "Infraestructura", assigned_to_id: null })
      : respuesta(200, { id: 7, state: "Nuevo", area_id: 4, area_name: "Infraestructura" })));
  nodos.get("area-destino").value = "4";
  nodos.get("area-reasignar").checked = true;
  await sandbox.cambiarAreaTicket();
  const patch = llamadas.find((l) => l.opciones.method === "PATCH");
  assert.equal(patch.url, "/api/tickets/7/area");
  assert.deepEqual(JSON.parse(patch.opciones.body), { area_id: 4, reasignar: true });
});

test("«Cambiar área» sin elegir un área no llama a la API", async () => {
  const { sandbox, nodos, llamadas } = detalle("Técnico", async () => respuesta(200, {}));
  nodos.get("area-destino").value = "";
  await sandbox.cambiarAreaTicket();
  assert.equal(llamadas.length, 0);
});

test("detalle.html: «Área de IT» en los datos y la sección «Cambiar área» para quien puede", () => {
  const html = leer("detalle.html");
  assert.match(html, /<dt>Área de IT<\/dt>\s*<dd id="ver-area">/);
  assert.match(html, /<section id="seccion-area"[^>]*data-permiso="cambiar_area">/);
  assert.match(html, /<input type="checkbox" id="area-reasignar" checked>/);
});

// --- Pantalla «Áreas de IT» ------------------------------------------------------

test("areas.html: solo Administrador, formulario, tabla y sin código inline", () => {
  const html = leer("areas.html");
  assert.match(html, /<script src="js\/guardia\.js" data-permiso="areas"><\/script>/);
  assert.match(html, /<form id="form-area"/);
  assert.match(html, /<th>Técnicos activos<\/th>/);
  assert.match(html, /<a href="areas.html" class="menu-enlace activo" aria-current="page" data-permiso="areas">/);
  assert.doesNotMatch(html, /<script>(?!<\/script>)/);
});

test("areas.js: valida el nombre y pinta cada área con sus acciones", () => {
  const ids = ["cuerpo-areas", "tabla-areas", "areas-estado"];
  const { sandbox, nodos } = sandboxCon("Administrador", async () => respuesta(200, []), ids);
  vm.runInNewContext(leer("js/areas.js"), sandbox, { filename: "areas.js" });
  assert.deepEqual({ ...sandbox.validarNombreArea("  Mesa   de ayuda ") }, { nombre: "Mesa de ayuda" });
  assert.match(sandbox.validarNombreArea("x").error, /al menos 2/);
  sandbox.renderAreas([{ id: 1, name: "Redes", is_active: true, tecnicos: 2 },
    { id: 2, name: "Vieja", is_active: false, tecnicos: 0 }]);
  const filas = nodos.get("cuerpo-areas").children;
  assert.equal(filas.length, 2);
  assert.deepEqual(filas[0].children.slice(0, 2).map((c) => c.textContent), ["Redes", "2"]);
  assert.equal(filas[0].children[2].children[0].textContent, "Activa");
  assert.deepEqual(filas[1].children[3].children.map((b) => b.textContent), ["Renombrar", "Reactivar"]);
  assert.equal(nodos.get("tabla-areas").hidden, false);
});

test("métricas: el filtro de área existe y se manda a la API", () => {
  const html = leer("metricas.html");
  assert.match(html, /<select id="m-area"/);
  const ctx = { URLSearchParams };
  vm.runInNewContext(leer("js/metricas.js"), ctx);
  assert.equal(ctx.urlMetricas("2026-10-01", "2026-10-31", "3"),
    "/api/metricas?desde=2026-10-01&hasta=2026-10-31&area=3");
  assert.equal(ctx.urlMetricas("2026-10-01", "2026-10-31", "sin"),
    "/api/metricas?desde=2026-10-01&hasta=2026-10-31&sin_area=true");
  assert.equal(ctx.urlMetricas("2026-10-01", "2026-10-31"), "/api/metricas?desde=2026-10-01&hasta=2026-10-31");
});
