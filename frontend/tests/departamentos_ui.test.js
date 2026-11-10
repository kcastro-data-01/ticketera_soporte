/* Pantalla «Departamentos» (solo Administrador): enlace en el menú debajo de
   «Métricas», tabla por departamento con números que abren la lista
   filtrada, el resumen de arriba y la lista que entiende ?area=&estado=.
   Ejecutar con: node --test frontend/tests/departamentos_ui.test.js */

"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const carpeta = path.join(__dirname, "..");
const leer = (archivo) => fs.readFileSync(path.join(carpeta, archivo), "utf8");

function nodo(tag = "") {
  return {
    tag, id: "", textContent: "", className: "", hidden: false, value: "", href: "", title: "",
    attrs: {}, children: [],
    get options() { return this.children; },
    setAttribute(k, v) { this.attrs[k] = v; },
    appendChild(h) { this.children.push(h); return h; },
    replaceChildren(...hs) { this.children = hs; },
    addEventListener() {},
  };
}

const RESUMEN = {
  total_abiertos: 5,
  mas_abiertos: { area_id: 2, nombre: "Redes e Infraestructura", abiertos: 3 },
  departamentos: [
    { area_id: 1, nombre: "Soporte IT", total: 4, abiertos: 2,
      por_estado: { Nuevo: 1, "En proceso": 1, Resuelto: 1, Cerrado: 1 },
      tecnicos: [{ id: 7, name: "Ana Mora" }, { id: 8, name: "Luis Solís" }] },
    { area_id: 2, nombre: "Redes e Infraestructura", total: 3, abiertos: 3,
      por_estado: { Nuevo: 3, "En proceso": 0, Resuelto: 0, Cerrado: 0 }, tecnicos: [] },
    { area_id: null, nombre: "Sin departamento", total: 1, abiertos: 0,
      por_estado: { Nuevo: 0, "En proceso": 0, Resuelto: 0, Cerrado: 1 }, tecnicos: [] },
  ],
};

function montar(rol, respuesta) {
  const ids = ["estado-carga", "d-total-abiertos", "d-mas-abiertos", "d-mas-abiertos-nota",
    "cuerpo-departamentos", "tabla-departamentos"];
  const nodos = new Map(ids.map((id) => [id, nodo(id)]));
  const sesion = JSON.stringify({ id: 1, name: "Quien", role: rol });
  const llamadas = [];
  const sandbox = {
    document: { getElementById: (id) => nodos.get(id), createElement: (t) => nodo(t), addEventListener() {}, querySelectorAll: () => [] },
    window: { location: { href: "departamentos.html", search: "" } },
    localStorage: { getItem: (k) => (k === "access_token" ? "t" : k === "user" ? sesion : null), setItem() {}, removeItem() {} },
    fetch: async (url) => { llamadas.push(url); return respuesta; },
    console: { error() {}, log() {} },
    URLSearchParams, Map,
  };
  vm.runInNewContext(leer("js/auth.js"), sandbox, { filename: "auth.js" });
  vm.runInNewContext(leer("js/departamentos.js"), sandbox, { filename: "departamentos.js" });
  return { sandbox, nodos, llamadas };
}

const ok = (cuerpo) => ({ ok: true, status: 200, json: async () => cuerpo });

test("el enlace «Departamentos» va debajo de «Métricas» en todas las páginas, solo para el Administrador", () => {
  const paginas = fs.readdirSync(carpeta).filter((f) => f.endsWith(".html") && leer(f).includes('<nav class="menu"'));
  assert.ok(paginas.includes("departamentos.html"));
  for (const pagina of paginas) {
    const nav = leer(pagina).match(/<nav class="menu"[\s\S]*?<\/nav>/)[0];
    const enlaces = [...nav.matchAll(/<a href="([^"]+)"/g)].map((m) => m[1]);
    assert.equal(enlaces[enlaces.indexOf("metricas.html") + 1], "departamentos.html", pagina);
    assert.match(nav, /<a href="departamentos.html" class="menu-enlace[^"]*"(?: aria-current="page")? data-permiso="departamentos">/, pagina);
  }
  for (const [rol, puede] of [["Administrador", true], ["Técnico", false], ["Solicitante", false]]) {
    const { sandbox: s } = montar(rol, ok(RESUMEN));
    assert.equal(s.puede("departamentos"), puede, rol);
  }
});

test("departamentos.html: solo Administrador, sin código inline y con las columnas pedidas", () => {
  const html = leer("departamentos.html");
  assert.match(html, /<script src="js\/guardia\.js" data-permiso="departamentos"><\/script>/);
  assert.doesNotMatch(html.replace(/<script src="[^"]+"(?: [a-z-]+(?:="[^"]*")?)*><\/script>/g, ""), /<script|<style|\sstyle="|\son[a-z]+="/);
  const columnas = [...html.matchAll(/<th scope="col">([^<]+)<\/th>/g)].map((m) => m[1]);
  assert.deepEqual(columnas, ["Departamento", "Total", "Abiertos", "Nuevo", "En proceso", "Resuelto", "Cerrado", "Técnicos activos"]);
  assert.match(html, /<main class="contenido metricas departamentos">/, "mismo estilo que Métricas");
});

test("pinta el resumen y una fila por departamento con enlaces a la lista filtrada", async () => {
  const { sandbox, nodos, llamadas } = montar("Administrador", ok(RESUMEN));
  await sandbox.cargarDepartamentos();
  assert.deepEqual(llamadas, ["/api/departamentos/resumen"]);
  assert.equal(nodos.get("d-total-abiertos").textContent, "5");
  assert.equal(nodos.get("d-mas-abiertos").textContent, "Redes e Infraestructura");
  assert.equal(nodos.get("d-mas-abiertos-nota").textContent, "3 tickets abiertos");
  const uno = montar("Administrador", ok({ ...RESUMEN, mas_abiertos: { area_id: 4, nombre: "Programación", abiertos: 1 } }));
  await uno.sandbox.cargarDepartamentos();
  assert.equal(uno.nodos.get("d-mas-abiertos-nota").textContent, "1 ticket abierto");
  const filas = nodos.get("cuerpo-departamentos").children;
  assert.equal(filas.length, 3);
  const soporte = filas[0].children;
  assert.equal(soporte[0].textContent, "Soporte IT");
  const enlaces = soporte.slice(1, 7).map((td) => [td.children[0].textContent, td.children[0].href]);
  assert.deepEqual(enlaces, [
    ["4", "index.html?area=1"],
    ["2", "index.html?area=1&estado=abiertos"],
    ["1", "index.html?area=1&estado=Nuevo"],
    ["1", "index.html?area=1&estado=En+proceso"],
    ["1", "index.html?area=1&estado=Resuelto"],
    ["1", "index.html?area=1&estado=Cerrado"],
  ]);
  // Técnicos activos: la cantidad y los nombres debajo (y al pasar el mouse).
  assert.equal(soporte[7].children[0].textContent, "2");
  assert.equal(soporte[7].children[1].textContent, "Ana Mora, Luis Solís");
  assert.equal(soporte[7].title, "Ana Mora, Luis Solís");
  assert.equal(filas[1].children[7].children[1].textContent, "Sin técnicos");
  const sin = filas[2].children;
  assert.equal(sin[0].textContent, "Sin departamento");
  assert.equal(sin[6].children[0].href, "index.html?area=sin&estado=Cerrado");
  assert.equal(nodos.get("tabla-departamentos").hidden, false);
});

test("sin abiertos lo dice, y con 403 avisa que el rol no tiene permiso", async () => {
  const vacio = { ...RESUMEN, total_abiertos: 0, mas_abiertos: null };
  const a = montar("Administrador", ok(vacio));
  await a.sandbox.cargarDepartamentos();
  assert.equal(a.nodos.get("d-mas-abiertos-nota").textContent, "Ningún departamento tiene tickets abiertos");
  const b = montar("Técnico", { ok: false, status: 403, json: async () => ({ detail: "x" }) });
  await b.sandbox.cargarDepartamentos();
  assert.equal(b.nodos.get("estado-carga").textContent, "Su rol no tiene permiso para ver los departamentos.");
  assert.equal(b.nodos.get("cuerpo-departamentos").children.length, 0, "no se pinta la tabla");
});

test("la lista aplica ?area=&estado= y «abiertos» pide Nuevo y En proceso", () => {
  const nodos = new Map(["state", "area", "search", "category", "priority", "assigned", "fecha"].map((id) => [id, nodo(id)]));
  const opcion = (v) => Object.assign(nodo("option"), { value: v });
  nodos.get("state").children = ["", "abiertos", "Nuevo", "En proceso", "Resuelto", "Cerrado"].map(opcion);
  nodos.get("area").children = ["", "sin", "1", "2"].map(opcion);
  const sandbox = {
    document: { getElementById: (id) => nodos.get(id), createElement: (t) => nodo(t), addEventListener() {} },
    window: { location: { search: "" } }, localStorage: { getItem: () => null }, console, URLSearchParams, Map,
  };
  vm.runInNewContext(leer("js/app.js"), sandbox, { filename: "app.js" });
  sandbox.aplicarFiltrosDeUrl("?area=2&estado=abiertos");
  assert.deepEqual([nodos.get("area").value, nodos.get("state").value], ["2", "abiertos"]);
  assert.equal(sandbox.buildTicketsUrl({ area: "2", state: "abiertos" }),
    "/api/tickets?state=Nuevo&state=En+proceso&area=2&limit=1000");
  sandbox.aplicarFiltrosDeUrl("?area=99&estado=Inventado");
  assert.deepEqual([nodos.get("area").value, nodos.get("state").value], ["2", "abiertos"], "lo que no existe se ignora");
});
