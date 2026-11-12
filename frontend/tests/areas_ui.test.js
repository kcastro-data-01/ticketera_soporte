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

test("permisos: nadie administra áreas (son fijas); cambiar el área, Administrador y Técnico", () => {
  for (const [rol, cambiar] of [["Administrador", true], ["Técnico", true], ["Solicitante", false]]) {
    const { sandbox } = sandboxCon(rol, async () => respuesta(200, []));
    assert.equal(sandbox.puede("areas"), false, rol);
    assert.equal(sandbox.puede("cambiar_area"), cambiar, rol);
  }
});

test("llenarSelectAreas: «Todos», «Sin departamento» y los departamentos fijos", () => {
  const { sandbox } = sandboxCon("Administrador", async () => respuesta(200, []));
  const select = nodo("area");
  sandbox.llenarSelectAreas(select, [{ id: 1, name: "Soporte IT" }, { id: 2, name: "Redes e Infraestructura" }],
    { primera: "Todos", sinArea: true });
  assert.deepEqual(select.children.map((o) => [o.value, o.textContent]),
    [["", "Todos"], ["sin", "Sin departamento"], ["1", "Soporte IT"], ["2", "Redes e Infraestructura"]]);
});

test("cargarAreas pide las áreas fijas y devuelve [] si falla", async () => {
  let falla = false;
  const { sandbox, llamadas } = sandboxCon("Administrador", async () =>
    (falla ? respuesta(500, {}) : respuesta(200, [{ id: 1, name: "Soporte IT" }])));
  assert.equal((await sandbox.cargarAreas()).length, 1);
  falla = true;
  assert.deepEqual(JSON.parse(JSON.stringify(await sandbox.cargarAreas())), []);
  assert.deepEqual(llamadas.map((l) => l.url), ["/api/areas", "/api/areas"]);
});

test("el historial muestra el cambio de departamento", () => {
  const { sandbox } = sandboxCon("Técnico", async () => respuesta(200, []));
  assert.deepEqual({ ...sandbox.describirHistorial({ action: "area_changed", old_value: "Soporte IT", new_value: "Programación" }) },
    { accion: "Cambió el departamento", detalle: "Soporte IT → Programación" });
  assert.equal(sandbox.describirHistorial({ action: "area_changed", old_value: null, new_value: "Redes" }).detalle,
    "Sin departamento → Redes");
});

// --- Detalle -------------------------------------------------------------------

const IDS_DETALLE = ["usuario", "usuarios-nota", "area-destino", "area-reasignar", "cambiar-area", "estado-carga",
  "seccion-area",
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

test("detalle.html: «Departamento» en el encabezado y la sección «Cambiar departamento» para quien puede", () => {
  const html = leer("detalle.html");
  assert.match(html, /<span class="etiqueta-dato-nombre">Departamento<\/span><span id="ver-area" class="etiqueta-dato-valor">/);
  assert.match(html, /<h2>Cambiar departamento<\/h2>/);
  assert.match(html, /id="cambiar-area">Cambiar departamento<\/button>/);
  assert.match(html, /Reasignar al técnico del nuevo departamento con menos tickets abiertos/);
  assert.doesNotMatch(html.replace(/<!--[\s\S]*?-->/g, ""), /[ÁáA]rea/);
  assert.match(html, /<section id="seccion-area"[^>]*data-permiso="cambiar_area" hidden>/, "oculta hasta saber si el ticket está en Nuevo");
  assert.match(html, /<input type="checkbox" id="area-reasignar" checked>/);
});

// --- Áreas fijas: sin pantalla de administración --------------------------------

test("ya no existe la pantalla «Áreas de IT» ni su enlace en el menú", () => {
  assert.equal(fs.existsSync(path.join(__dirname, "..", "areas.html")), false);
  assert.equal(fs.existsSync(path.join(__dirname, "..", "js", "areas.js")), false);
  for (const pagina of fs.readdirSync(path.join(__dirname, "..")).filter((f) => f.endsWith(".html"))) {
    assert.doesNotMatch(leer(pagina), /areas\.html/, pagina);
  }
});

test("«Nuevo ticket»: debajo de «Departamento», qué atiende cada uno", () => {
  const html = leer("crear.html");
  const bloque = html.slice(html.indexOf('<select id="area"'), html.indexOf("</ul>", html.indexOf('id="ayuda-area"')));
  const items = [...bloque.matchAll(/<li><strong>([^<]+)<\/strong>: ([^<]+)<\/li>/g)].map((m) => [m[1], m[2]]);
  assert.deepEqual(items, [
    ["Soporte IT", "computadoras, impresoras, programas."],
    ["Redes e Infraestructura", "internet, wifi, servidores, VPN."],
    ["Ciberseguridad", "accesos, contraseñas, cuentas, incidentes de seguridad."],
    ["Programación", "sistemas internos, Odoo, desarrollos y reportes."],
  ]);
  assert.match(html, /<select id="area" name="area" required aria-describedby="ayuda-area">/);
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

test("ninguna pantalla muestra «Área»: se llama «Departamento»", () => {
  const carpeta = path.join(__dirname, "..");
  for (const pagina of fs.readdirSync(carpeta).filter((f) => f.endsWith(".html"))) {
    const visible = leer(pagina).replace(/<!--[\s\S]*?-->/g, "").replace(/área de TI/g, "");
    assert.doesNotMatch(visible, /[ÁáAa]reas? de IT|>[^<]*\b[Áá]reas?\b|«Sin área»|Cambiar área/, pagina);
  }
  for (const archivo of ["js/auth.js", "js/crear.js", "js/detalle.js", "js/usuarios.js", "js/app.js", "js/metricas.js"]) {
    const textos = [...leer(archivo).matchAll(/(["`])((?:(?!\1).)*)\1/g)].map((m) => m[2]);
    const conArea = textos.filter((t) => /\b[Áá]reas?\b|Sin área/.test(t));
    assert.deepEqual(conArea, [], archivo);
  }
});

// --- El departamento solo se cambia en Nuevo --------------------------------------

const SOLO_NUEVO = "El departamento solo se puede cambiar mientras el ticket está en Nuevo";

test("la sección «Departamento» solo se ve en Nuevo; en los demás estados no aparece", () => {
  for (const rol of ["Administrador", "Técnico"]) {
    const { sandbox, nodos } = detalle(rol, async () => respuesta(200, {}));
    sandbox.pintarSeccionArea({ state: "Nuevo", area_name: "Soporte IT" });
    assert.equal(nodos.get("seccion-area").hidden, false, rol);
    for (const estado of ["En proceso", "Resuelto", "Cerrado"]) {
      sandbox.pintarSeccionArea({ state: estado, area_name: "Programación" });
      assert.equal(nodos.get("seccion-area").hidden, true, `${rol} ${estado}`);
    }
    sandbox.pintarSeccionArea({ state: "Nuevo", area_name: null });
    assert.equal(nodos.get("seccion-area").hidden, false, `${rol} vuelve a Nuevo`);
  }
  const { sandbox, nodos } = detalle("Solicitante", async () => respuesta(200, {}));
  for (const estado of ["Nuevo", "En proceso", "Resuelto", "Cerrado"]) {
    sandbox.pintarSeccionArea({ state: estado, area_name: "Soporte IT" });
    assert.equal(nodos.get("seccion-area").hidden, true, `el Solicitante no cambia el departamento (${estado})`);
  }
});

test("fuera de Nuevo «Cambiar departamento» no llama a la API", async () => {
  const { sandbox, nodos, llamadas } = detalle("Administrador", async () => respuesta(200, {}));
  vm.runInNewContext('ticketActual = { id: 7, state: "En proceso" };', sandbox);
  nodos.get("area-destino").value = "2";
  await sandbox.cambiarAreaTicket();
  assert.equal(llamadas.length, 0);
});

test("detalle.html: sin «Departamento actual» repetido, la casilla normal a la izquierda y sin la nota técnica de Asignación", () => {
  const html = leer("detalle.html");
  assert.doesNotMatch(html, /area-solo-nuevo|area-actual|Departamento actual/);
  assert.doesNotMatch(html, new RegExp(`<p class="nota">${SOLO_NUEVO}</p>`));
  assert.match(html, /<label class="casilla">\s*<input type="checkbox" id="area-reasignar" checked>\s*<span>Reasignar al técnico del nuevo departamento con menos tickets abiertos<\/span>/);
  assert.doesNotMatch(html, /IT solo recibe tickets/);
  const css = leer("css/estilos.css");
  assert.match(css, /\.casilla \{\s*display: flex;\s*align-items: flex-start;/);
  assert.match(css, /\.casilla input\[type="checkbox"\] \{[^}]*width: 17px;\s*height: 17px;/);
});
