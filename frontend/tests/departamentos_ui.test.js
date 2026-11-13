/* Pantalla «Departamentos» (solo Administrador): enlace en el menú debajo de
   «Métricas»; dos columnas con la lista de departamentos (pestañas con su
   barrita de estados) y el detalle del elegido (cajitas por estado,
   técnicos y tickets abiertos); el elegido queda en la dirección; la lista
   entiende ?area=&estado=.
   Ejecutar con: node --test frontend/tests/departamentos_ui.test.js */

"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const carpeta = path.join(__dirname, "..");
const leer = (archivo) => fs.readFileSync(path.join(carpeta, archivo), "utf8").replace(/\?v=[\w-]+"/g, '"');

function nodo(tag = "") {
  const el = {
    tag, id: "", textContent: "", className: "", hidden: false, value: "", href: "", title: "", type: "",
    tabIndex: 0, attrs: {}, children: [], style: {}, dataset: {}, parentNode: null, listeners: {}, enfocado: false,
    get options() { return this.children; },
    setAttribute(k, v) { this.attrs[k] = String(v); },
    getAttribute(k) { return this.attrs[k]; },
    appendChild(h) { this.children.push(h); h.parentNode = this; return h; },
    replaceChildren(...hs) { this.children = []; hs.forEach((h) => this.appendChild(h)); },
    addEventListener(tipo, fn) { this.listeners[tipo] = fn; },
    focus() { this.enfocado = true; },
  };
  return el;
}

const RESUMEN = {
  total_abiertos: 5,
  atencion: { criticos: 2, altos: 0, sin_asignar: 3, nuevos_viejos: 1, dias_nuevo: 2 },
  mas_abiertos: { area_id: 2, nombre: "Redes e Infraestructura", abiertos: 3 },
  departamentos: [
    { area_id: 1, nombre: "Soporte IT", total: 4, abiertos: 2, atiende: "computadoras, impresoras, programas",
      por_estado: { Nuevo: 1, "En proceso": 1, Resuelto: 1, Cerrado: 1 },
      tecnicos: [{ id: 7, name: "Ana Mora", abiertos: 1, resueltos_mes: 3 }, { id: 8, name: "Luis Solís", abiertos: 1, resueltos_mes: 0 }],
      tickets_abiertos: [
        { id: 21, title: "Impresora trabada", state: "En proceso", priority: "Crítica", assigned_to_name: "Ana Mora" },
        { id: 9, title: "Mouse roto", state: "Nuevo", priority: "Baja", assigned_to_name: null },
      ] },
    { area_id: 2, nombre: "Redes e Infraestructura", total: 3, abiertos: 3, atiende: "internet, wifi, servidores, VPN",
      por_estado: { Nuevo: 3, "En proceso": 0, Resuelto: 0, Cerrado: 0 }, tecnicos: [], tickets_abiertos: [] },
    { area_id: 3, nombre: "Ciberseguridad", total: 0, abiertos: 0, atiende: "accesos",
      por_estado: { Nuevo: 0, "En proceso": 0, Resuelto: 0, Cerrado: 0 }, tecnicos: [], tickets_abiertos: [] },
    { area_id: 4, nombre: "Programación", total: 12, abiertos: 12, atiende: "sistemas internos",
      por_estado: { Nuevo: 12, "En proceso": 0, Resuelto: 0, Cerrado: 0 }, tecnicos: [],
      tickets_abiertos: Array.from({ length: 10 }, (_, i) => ({ id: 100 + i, title: `Pedido ${i}`, state: "Nuevo", priority: "Media", assigned_to_name: null })) },
    { area_id: null, nombre: "Sin departamento", total: 1, abiertos: 0, atiende: "tickets sin departamento",
      por_estado: { Nuevo: 0, "En proceso": 0, Resuelto: 0, Cerrado: 1 }, tecnicos: [], tickets_abiertos: [] },
  ],
};

const IDS = ["estado-carga", "deptos-layout", "deptos-lista", "deptos-detalle", "depto-nombre", "depto-atiende",
  "depto-total", "depto-ver-todos", "depto-cajas", "depto-tecnicos", "depto-tecnicos-vacio", "depto-abiertos",
  "depto-abiertos-vacio", "depto-abiertos-nota", "deptos-atencion", "deptos-leyenda"];

function montar(rol, respuesta, hash = "") {
  const nodos = new Map(IDS.map((id) => [id, nodo(id)]));
  // Las tablas: el tbody vive dentro de su <table>.
  for (const id of ["depto-tecnicos", "depto-abiertos"]) nodo("table").appendChild(nodos.get(id));
  const sesion = JSON.stringify({ id: 1, name: "Quien", role: rol });
  const llamadas = [];
  const direcciones = [];
  const sandbox = {
    document: { getElementById: (id) => nodos.get(id), createElement: (t) => nodo(t), addEventListener() {}, querySelectorAll: () => [] },
    window: { location: { href: "departamentos.html", search: "", hash },
      history: { replaceState: (_e, _t, url) => direcciones.push(url) }, addEventListener() {} },
    localStorage: { getItem: (k) => (k === "access_token" ? "t" : k === "user" ? sesion : null), setItem() {}, removeItem() {} },
    fetch: async (url) => { llamadas.push(url); return respuesta; },
    console: { error() {}, log() {} },
    URLSearchParams, Map, Array,
  };
  vm.runInNewContext(leer("js/auth.js"), sandbox, { filename: "auth.js" });
  vm.runInNewContext(leer("js/departamentos.js"), sandbox, { filename: "departamentos.js" });
  return { sandbox, nodos, llamadas, direcciones };
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

test("departamentos.html: solo Administrador, sin código ni estilos inline, con pestañas y panel", () => {
  const html = leer("departamentos.html");
  assert.match(html, /<script src="js\/guardia\.js" data-permiso="departamentos"><\/script>/);
  assert.doesNotMatch(html.replace(/<script src="[^"]+"(?: [a-z-]+(?:="[^"]*")?)*><\/script>/g, ""), /<script|<style|\sstyle="|\son[a-z]+="/);
  assert.match(html, /<p class="deptos-ayuda"[^>]*>Toque un departamento para ver su detalle<\/p>/);
  assert.match(html, /id="deptos-lista" role="tablist"/);
  assert.match(html, /id="deptos-detalle" role="tabpanel"/);
  assert.match(html, /<a class="enlace-boton secundario" id="depto-ver-todos"[^>]*>Ver todos sus tickets<\/a>/);
  const columnas = [...html.matchAll(/<th scope="col"[^>]*>([^<]+)<\/th>/g)].map((m) => m[1]);
  assert.deepEqual(columnas, ["Técnico", "Abiertos", "Resueltos este mes", "Ticket", "Estado", "Prioridad", "Asignado"]);
  assert.match(html, />Técnicos<\/h3>/);
  assert.match(html, />Tickets abiertos<\/h3>/);
});

test("departamentos.js no usa innerHTML ni atributos style: los colores van por element.style", () => {
  const js = leer("js/departamentos.js");
  assert.doesNotMatch(js, /innerHTML|insertAdjacentHTML|setAttribute\(\s*["']style/);
  for (const color of ["#1d4ed8", "#7c9fe8", "#0e8a7d", "#a3abbb"]) assert.ok(js.includes(color), color);
  const css = leer("css/estilos.css");
  assert.match(css, /\.deptos-layout \{[^}]*grid-template-columns: 260px minmax\(0, 1fr\)/);
  assert.match(css, /\.deptos-layout \{[^}]*align-items: stretch;/, "mismo alto que el detalle");
  assert.match(css, /\.deptos-columna \{[^}]*display: flex;[^}]*flex-direction: column;[^}]*border-radius: 10px;/);
  assert.match(css, /\.deptos-layout \{[^}]*min-height: calc\(100vh - var\(--deptos-alto-cabecera\) - 2rem - var\(--deptos-alto-ayuda\) - 2rem\);/, "como mínimo hasta abajo de la pantalla");
  assert.match(css, /\.deptos-lista \{\s*display: flex;\s*flex: none;\s*flex-direction: column;/, "la lista arriba, con su alto");
  assert.match(css, /\.deptos-extras \{\s*border-top: 1px solid var\(--color-borde\);/, "separados de la lista por una línea fina");
  assert.match(css, /\.deptos-bloque-titulo \{[^}]*text-transform: uppercase;[^}]*color: var\(--color-tenue\);/, "títulos chicos en mayúsculas grises");
  assert.match(css, /\.deptos-atencion-fila\.con-valor \.deptos-atencion-numero \{\s*font-weight: 700;/, "mayor que cero: negrita");
  assert.match(css, /\.deptos-atencion-fila\.en-cero,\s*\.deptos-atencion-fila\.en-cero \.deptos-atencion-numero \{\s*color: var\(--color-tenue\);/, "cero: gris");
  assert.match(css, /\.deptos-leyenda \{\s*display: grid;\s*grid-template-columns: repeat\(2, minmax\(0, 1fr\)\);/, "leyenda en dos columnas");
  assert.match(css, /\.depto-boton \{[^}]*display: grid;[^}]*flex: none;[^}]*height: 64px;[^}]*padding: 12px 16px;/, "alto fijo de 64 px, sin flex: 1, 12 px y 16 px de espaciado");
  assert.doesNotMatch(css.match(/\.depto-boton \{[^}]*\}/)[0], /flex: 1/);
  assert.match(css, /\.depto-boton-nombre \{\s*grid-column: 1;\s*grid-row: 1;[^}]*font-size: 15px;\s*font-weight: 600;/, "nombre arriba, 15 px seminegrita");
  assert.match(css, /\.depto-boton-abiertos \{\s*grid-column: 1;\s*grid-row: 2;\s*font-size: 12.5px;\s*line-height: 1.35;\s*color: var\(--color-tenue\);/, "«N abiertos» debajo, 12.5 px gris");
  assert.match(css, /\.depto-pastilla \{[^}]*font-size: 13px;/, "pastilla de 13 px");
  assert.match(css, /\.depto-pastilla \{\s*grid-column: 2;\s*grid-row: 1 \/ 3;/, "pastilla a la derecha, centrada");
  assert.doesNotMatch(css + leer("departamentos.html") + leer("js/departamentos.js"), /deptos-resumen|d-sin-asignar/, "sin el resumen de abajo");
  assert.match(css, /\.app \.contenido\.departamentos \{\s*max-width: none;/, "todo el ancho");
  assert.match(css, /\.deptos-detalle \{[^}]*border-radius: 10px;/);
  assert.match(css, /\.depto-barra \{[^}]*position: absolute;[^}]*bottom: 0;[^}]*height: 3px;/, "fina y pegada abajo");
  assert.match(css, /\.depto-boton-nombre \{[^}]*white-space: nowrap;/);
  assert.match(css, /\.depto-boton \+ \.depto-boton\.sin-departamento \{\s*border-top: 1px solid var\(--color-borde-fuerte\);/, "«Sin departamento» separado");
  assert.match(css, /\.depto-caja \{[^}]*border-top: 3px solid/);
  assert.match(css, /\.depto-tabla tbody tr:hover \{/);
  const angosto = css.match(/@media \(max-width: 900px\) \{\s*\.deptos-layout \{[\s\S]*?\n\}/);
  assert.ok(angosto, "debajo de 900 px cambia el diseño");
  assert.match(angosto[0], /\.deptos-layout \{\s*grid-template-columns: minmax\(0, 1fr\);/, "el detalle a todo el ancho");
  assert.match(angosto[0], /\.deptos-lista \{[^}]*flex-direction: row;[^}]*overflow-x: auto;/, "fila con scroll propio");
  assert.match(angosto[0], /\.deptos-layout \{\s*min-height: 0;/, "en el celular, su alto normal");
  assert.match(angosto[0], /\.deptos-columna \{\s*display: contents;/);
  assert.match(angosto[0], /\.deptos-lista \{\s*order: 1;[\s\S]*\.deptos-detalle \{\s*order: 2;[\s\S]*\.deptos-extras \{\s*order: 3;/, "en el celular, los bloques debajo del detalle");
  assert.match(angosto[0], /\.depto-boton \{[^}]*flex: none;/);
});

test("la lista: un botón por departamento (con «Sin departamento» si tiene tickets), su total y la barrita de estados", async () => {
  const { sandbox, nodos, llamadas, direcciones } = montar("Administrador", ok(RESUMEN));
  await sandbox.cargarDepartamentos();
  assert.deepEqual(llamadas, ["/api/departamentos/resumen"]);
  assert.equal(nodos.get("deptos-layout").hidden, false);
  const botones = nodos.get("deptos-lista").children;
  assert.deepEqual(botones.map((b) => b.children[0].textContent),
    ["Soporte IT", "Redes e Infraestructura", "Ciberseguridad", "Programación", "Sin departamento"]);
  const [soporte] = botones;
  assert.equal(soporte.attrs.role, "tab");
  assert.equal(soporte.type, "button");
  assert.equal(soporte.id, "tab-soporte-it");
  assert.deepEqual(soporte.children.map((h) => h.className),
    ["depto-boton-nombre", "depto-boton-abiertos", "depto-pastilla", "depto-barra"], "nombre, abiertos, pastilla y la barrita al final");
  assert.equal(soporte.children[1].textContent, "2 abiertos");
  assert.equal(botones[1].children[0].title, "Redes e Infraestructura", "nombre completo al pasar el mouse");
  assert.equal(botones[2].children[1].textContent, "0 abiertos");
  assert.equal(soporte.children[2].textContent, "4");
  const partes = soporte.children[3].children;
  assert.deepEqual(partes.map((p) => [p.style.width, p.style.backgroundColor]), [
    ["25%", "#1d4ed8"], ["25%", "#7c9fe8"], ["25%", "#0e8a7d"], ["25%", "#a3abbb"]]);
  assert.equal(botones[2].children[3].children.length, 0, "sin tickets: barrita vacía");
  // Al entrar queda elegido el primero, sin tocar la dirección.
  assert.equal(soporte.attrs["aria-selected"], "true");
  assert.match(soporte.className, /\belegido\b/);
  assert.equal(soporte.tabIndex, 0);
  assert.equal(botones[1].attrs["aria-selected"], "false");
  assert.equal(botones[1].tabIndex, -1);
  assert.equal(nodos.get("deptos-detalle").attrs["aria-labelledby"], "tab-soporte-it");
  assert.deepEqual(direcciones, []);

  const sinTickets = montar("Administrador", ok({ ...RESUMEN,
    departamentos: RESUMEN.departamentos.map((d) => (d.area_id === null ? { ...d, total: 0 } : d)) }));
  await sinTickets.sandbox.cargarDepartamentos();
  assert.equal(sinTickets.nodos.get("deptos-lista").children.length, 4, "«Sin departamento» sin tickets no aparece");
});

test("el detalle: nombre, qué atiende, cajitas, técnicos y abiertos con sus etiquetas", async () => {
  const { sandbox, nodos } = montar("Administrador", ok(RESUMEN));
  await sandbox.cargarDepartamentos();
  assert.equal(nodos.get("depto-nombre").textContent, "Soporte IT");
  assert.equal(nodos.get("depto-atiende").textContent, "Atiende computadoras, impresoras, programas");
  assert.equal(nodos.get("depto-total").textContent, "4 tickets en total");
  assert.equal(nodos.get("depto-ver-todos").href, "index.html?area=1");
  const cajas = nodos.get("depto-cajas").children;
  assert.deepEqual(cajas.map((c) => [c.children[1].textContent, c.children[0].textContent]),
    [["Abiertos", "2"], ["Nuevo", "1"], ["En proceso", "1"], ["Resuelto", "1"], ["Cerrado", "1"]]);
  assert.match(cajas[0].className, /depto-caja-abiertos/);
  assert.deepEqual(cajas.slice(1).map((c) => c.style.borderTopColor), ["#1d4ed8", "#7c9fe8", "#0e8a7d", "#a3abbb"]);

  const tecnicos = nodos.get("depto-tecnicos").children;
  assert.deepEqual(tecnicos.map((tr) => tr.children.map((td) => td.textContent)),
    [["Ana Mora", "1", "3"], ["Luis Solís", "1", "0"]]);
  assert.equal(tecnicos[0].children[0].dataset.iniciales, "AM", "iniciales en el círculo");
  assert.equal(nodos.get("depto-tecnicos-vacio").hidden, true);

  const abiertos = nodos.get("depto-abiertos").children;
  const [primero, segundo] = abiertos;
  assert.equal(primero.children[0].children[0].textContent, "#21");
  assert.equal(primero.children[0].children[0].href, "detalle.html?id=21");
  assert.equal(primero.children[0].children[1].textContent, "Impresora trabada");
  assert.equal(primero.children[1].children[0].className, "badge estado-proceso");
  assert.equal(primero.children[2].children[0].className, "badge prioridad-critica");
  assert.equal(primero.children[3].textContent, "Ana Mora");
  assert.equal(segundo.children[3].textContent, "—");
  assert.equal(nodos.get("depto-abiertos-nota").hidden, true);
});

test("con teclado: flechas, Inicio y Fin cambian de departamento; el elegido queda en la dirección", async () => {
  const { sandbox, nodos, direcciones } = montar("Administrador", ok(RESUMEN));
  await sandbox.cargarDepartamentos();
  const botones = nodos.get("deptos-lista").children;
  const tecla = (boton, key) => { let evitado = false; boton.listeners.keydown({ key, preventDefault() { evitado = true; } }); return evitado; };
  assert.equal(tecla(botones[0], "ArrowDown"), true);
  assert.equal(botones[1].attrs["aria-selected"], "true");
  assert.equal(botones[1].enfocado, true);
  assert.equal(nodos.get("depto-nombre").textContent, "Redes e Infraestructura");
  tecla(botones[1], "End");
  assert.equal(nodos.get("depto-nombre").textContent, "Sin departamento");
  tecla(botones[4], "ArrowDown");
  assert.equal(nodos.get("depto-nombre").textContent, "Soporte IT", "vuelve al primero");
  tecla(botones[0], "ArrowUp");
  assert.equal(nodos.get("depto-nombre").textContent, "Sin departamento");
  tecla(botones[4], "Home");
  assert.equal(tecla(botones[0], "a"), false, "otras teclas no hacen nada");
  botones[3].listeners.click();
  assert.equal(nodos.get("depto-nombre").textContent, "Programación");
  assert.equal(direcciones.at(-1), "#programacion");
  assert.deepEqual(direcciones, ["#redes-e-infraestructura", "#sin-departamento", "#soporte-it", "#sin-departamento", "#soporte-it", "#programacion"]);
});

test("al recargar con #programacion queda elegido Programación; con más de 10 abiertos el botón lleva al resto", async () => {
  const { sandbox, nodos } = montar("Administrador", ok(RESUMEN), "#programacion");
  await sandbox.cargarDepartamentos();
  assert.equal(nodos.get("depto-nombre").textContent, "Programación");
  assert.equal(nodos.get("deptos-lista").children[3].attrs["aria-selected"], "true");
  assert.equal(nodos.get("depto-abiertos").children.length, 10);
  assert.equal(nodos.get("depto-ver-todos").href, "index.html?area=4&estado=abiertos");
  assert.equal(nodos.get("depto-abiertos-nota").hidden, false);
  assert.equal(nodos.get("depto-abiertos-nota").textContent, "Se muestran 10 de 12 abiertos. «Ver todos sus tickets» muestra el resto.");
  assert.equal(nodos.get("depto-tecnicos-vacio").hidden, false);
  assert.equal(nodos.get("depto-tecnicos").parentNode.hidden, true);

  const otro = montar("Administrador", ok(RESUMEN), "#inventado");
  await otro.sandbox.cargarDepartamentos();
  assert.equal(otro.nodos.get("depto-nombre").textContent, "Soporte IT", "lo que no existe: el primero");
  assert.equal(sandbox.slugDepartamento("Redes e Infraestructura"), "redes-e-infraestructura");
  assert.equal(sandbox.slugDepartamento("Programación"), "programacion");
});

test("«Requieren atención»: cada fila es un enlace a la lista filtrada, en negrita si es mayor que cero; y la leyenda", async () => {
  const html = leer("departamentos.html");
  const columna = html.match(/<div class="deptos-columna">[\s\S]*?<\/div>\n      <\/div>/)[0];
  assert.ok(columna.indexOf('id="deptos-lista"') < columna.indexOf('id="deptos-extras"'), "debajo de la lista, en la misma tarjeta");
  assert.deepEqual([...columna.matchAll(/<h2 class="deptos-bloque-titulo"[^>]*>([^<]+)<\/h2>/g)].map((m) => m[1]),
    ["Requieren atención", "Leyenda"]);

  const { sandbox, nodos } = montar("Administrador", ok(RESUMEN));
  await sandbox.cargarDepartamentos();
  const filas = nodos.get("deptos-atencion").children.map((li) => li.children[0]);
  assert.deepEqual(filas.map((a) => [a.children[0].textContent, a.children[1].textContent, a.href]), [
    ["Críticos abiertos", "2", "index.html?prioridad=Cr%C3%ADtica&estado=abiertos"],
    ["Altos abiertos", "0", "index.html?prioridad=Alta&estado=abiertos"],
    ["Sin asignar", "3", "index.html?asignado=sin&estado=abiertos"],
    ["Más de 2 días en Nuevo", "1", "index.html?estado=Nuevo&antiguedad=2"],
  ]);
  assert.deepEqual(filas.map((a) => a.className.split(" ")[1]), ["con-valor", "en-cero", "con-valor", "con-valor"]);
  assert.equal(filas[0].attrs["aria-label"], "Críticos abiertos: 2. Abrir la lista de tickets");

  const leyenda = nodos.get("deptos-leyenda").children;
  assert.deepEqual(leyenda.map((li) => [li.children[1].textContent, li.children[0].style.backgroundColor]), [
    ["Nuevo", "#1d4ed8"], ["En proceso", "#7c9fe8"], ["Resuelto", "#0e8a7d"], ["Cerrado", "#a3abbb"]]);

  const sin = montar("Administrador", ok({ ...RESUMEN, atencion: undefined }));
  await sin.sandbox.cargarDepartamentos();
  assert.deepEqual(sin.nodos.get("deptos-atencion").children.map((li) => li.children[0].children[1].textContent), ["0", "0", "0", "0"]);
});

test("debajo de 900 px la lista se anuncia horizontal (y vuelve a vertical al agrandar)", async () => {
  const m = montar("Administrador", ok(RESUMEN));
  let cambio = null;
  const consulta = { matches: true, addEventListener: (_t, fn) => { cambio = fn; } };
  const pedidas = [];
  m.sandbox.window.matchMedia = (q) => { pedidas.push(q); return consulta; };
  await m.sandbox.cargarDepartamentos();
  assert.deepEqual(pedidas, ["(max-width: 900px)"]);
  const lista = m.nodos.get("deptos-lista");
  assert.equal(lista.attrs["aria-orientation"], "horizontal");
  consulta.matches = false;
  cambio();
  assert.equal(lista.attrs["aria-orientation"], "vertical");
});

test("sin abiertos lo dice, y con 403 avisa que el rol no tiene permiso", async () => {
  const a = montar("Administrador", ok(RESUMEN), "#ciberseguridad");
  await a.sandbox.cargarDepartamentos();
  assert.equal(a.nodos.get("depto-abiertos-vacio").hidden, false);
  assert.equal(a.nodos.get("depto-abiertos-vacio").textContent, "No tiene tickets abiertos.");
  assert.equal(a.nodos.get("depto-ver-todos").href, "index.html?area=3");
  const b = montar("Técnico", { ok: false, status: 403, json: async () => ({ detail: "x" }) });
  await b.sandbox.cargarDepartamentos();
  assert.equal(b.nodos.get("estado-carga").textContent, "Su rol no tiene permiso para ver los departamentos.");
  assert.equal(b.nodos.get("deptos-lista").children.length, 0, "no se pinta la lista");
});

test("la lista aplica ?area=&estado= y «abiertos» pide Nuevo y En proceso", () => {
  const nodos = new Map(["state", "area", "search", "category", "priority", "assigned", "fecha",
    "filtro-antiguedad", "filtro-antiguedad-texto"].map((id) => [id, nodo(id)]));
  const opcion = (v) => Object.assign(nodo("option"), { value: v });
  nodos.get("state").children = ["", "abiertos", "Nuevo", "En proceso", "Resuelto", "Cerrado"].map(opcion);
  nodos.get("area").children = ["", "sin", "1", "2"].map(opcion);
  nodos.get("priority").children = ["", "Baja", "Media", "Alta", "Crítica"].map(opcion);
  nodos.get("assigned").children = ["", "sin", "7"].map(opcion);
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

  // Desde «Requieren atención»: prioridad, sin asignar y antigüedad.
  sandbox.aplicarFiltrosDeUrl("?prioridad=Cr%C3%ADtica&estado=abiertos&asignado=sin");
  assert.deepEqual([nodos.get("priority").value, nodos.get("assigned").value], ["Crítica", "sin"]);
  assert.equal(nodos.get("filtro-antiguedad").hidden, true, "sin antigüedad no hay aviso");
  sandbox.aplicarFiltrosDeUrl("?estado=Nuevo&antiguedad=2");
  assert.equal(nodos.get("filtro-antiguedad").hidden, false);
  assert.equal(nodos.get("filtro-antiguedad-texto").textContent, "Solo los creados hace más de 2 días.");
  const url = new URL(sandbox.buildTicketsUrl({ state: "Nuevo", antiguedad: 2 }), "http://x");
  const limite = Date.parse(url.searchParams.get("creado_antes"));
  assert.ok(Math.abs(Date.now() - 2 * 86400000 - limite) < 5000, url.search);
  assert.equal(url.searchParams.get("state"), "Nuevo");
  assert.equal(sandbox.creadoAntesDe(2, Date.parse("2026-11-13T12:00:00Z")), "2026-11-11T12:00:00.000Z");
  assert.equal(new URL(sandbox.buildTicketsUrl({ antiguedad: 0 }), "http://x").searchParams.has("creado_antes"), false);
  for (const malo of ["0", "-3", "1.5", "abc", "9999"]) assert.equal(sandbox.antiguedadValida(malo), 0, malo);
});
