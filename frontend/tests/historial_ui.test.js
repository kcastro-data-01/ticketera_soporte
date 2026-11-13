/* Pantalla «Historial» por persona (frontend/js/historial.js): mismo armado
   que Departamentos. A la izquierda «Todas las personas» y las personas con
   cambios (con «Sistema»); a la derecha el detalle con período, búsqueda,
   cajitas y los cambios agrupados por día (50 por vez, «Ver más»). La
   persona y el período quedan en la dirección.
   Se cargan los scripts reales (auth.js + historial.js) en un contexto con
   DOM mínimo y fetch controlado.
   Ejecutar con: node --test frontend/tests/historial_ui.test.js */

"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const carpeta = path.join(__dirname, "..");
const leer = (archivo) => fs.readFileSync(path.join(carpeta, archivo), "utf8").replace(/\?v=[\w-]+"/g, '"');

const TOKEN = "token-de-prueba";

function nodo(tag = "") {
  return {
    tag, id: "", textContent: "", className: "", hidden: false, value: "", href: "", title: "", type: "",
    innerHTML: "", disabled: false, tabIndex: 0, attrs: {}, children: [], style: {}, dataset: {},
    parentNode: null, listeners: {}, enfocado: false,
    setAttribute(k, v) { this.attrs[k] = String(v); },
    getAttribute(k) { return this.attrs[k]; },
    removeAttribute(k) { delete this.attrs[k]; },
    appendChild(h) { this.children.push(h); h.parentNode = this; return h; },
    replaceChildren(...hs) { this.children = []; hs.forEach((h) => this.appendChild(h)); },
    addEventListener(tipo, fn) { this.listeners[tipo] = fn; },
    focus() { this.enfocado = true; },
  };
}

const IDS = ["estado-carga", "hist-layout", "hist-lista", "hist-detalle", "hist-nombre", "hist-rol", "hist-total",
  "hist-periodo", "hist-buscar", "hist-cajas", "hist-cambios", "hist-vacio", "hist-ver-mas"];

const PERSONAS = [
  { clave: "12", user_id: 12, nombre: "Daniel Sáenz", rol: "Técnico", departamento: "Redes e Infraestructura", cambios: 3 },
  { clave: "sistema", user_id: null, nombre: "Sistema", rol: "Cambios automáticos", departamento: null, cambios: 1 },
  { clave: "5", user_id: 5, nombre: "Sofía Solicitante", rol: "Solicitante", departamento: null, cambios: 0 },
];
const CAJAS = { cambios: 4, tickets: 2, comentarios: 1, cambios_estado: 2 };
const resumen = (extra = {}) => ({ periodo: "7", desde: "2026-11-07T06:00:00Z", total: 4, personas: PERSONAS, cajas: CAJAS, ...extra });

/* Hora fija: jueves 12 de noviembre de 2026, 3 p. m. en Costa Rica. */
const AHORA = Date.UTC(2026, 10, 12, 21, 0);

const CAMBIOS = [
  { id: 4, ticket_id: 7, ticket_title: "Impresora sin conexión", action: "commented", field: "comment",
    old_value: null, new_value: "hola", author: "Daniel Sáenz", author_id: 12, created_at: "2026-11-12T19:01:00Z" },
  { id: 3, ticket_id: 7, ticket_title: "Impresora sin conexión", action: "Cambio de estado", field: "state",
    old_value: "Nuevo", new_value: "En proceso", author: "Daniel Sáenz", author_id: 12, created_at: "2026-11-12T15:30:00Z" },
  { id: 2, ticket_id: 9, ticket_title: "Correo no sincroniza", action: "assigned", field: "assigned_to_id",
    old_value: null, new_value: "Daniel Sáenz", author: "Daniel Sáenz", author_id: 12, created_at: "2026-11-11T22:10:00Z" },
  { id: 1, ticket_id: 9, ticket_title: "Correo no sincroniza", action: "Cierre automático", field: "state",
    old_value: "Resuelto", new_value: "Cerrado", author: "Sistema", author_id: null, created_at: "2026-11-09T12:00:00Z" },
];

const ok = (cuerpo) => ({ ok: true, status: 200, json: async () => cuerpo });

/* responder(url) devuelve la respuesta de cada pedido. */
function montar({ hash = "", responder } = {}) {
  const nodos = new Map(IDS.map((id) => [id, Object.assign(nodo(), { id })]));
  nodos.get("hist-periodo").value = "7";
  nodos.get("hist-layout").hidden = true;
  const llamadas = [];
  const direcciones = [];
  const RealDate = Date;
  class FechaFija extends RealDate {
    constructor(...args) { if (args.length) super(...args); else super(AHORA); }
    static now() { return AHORA; }
  }
  const sandbox = {
    document: {
      getElementById: (id) => nodos.get(id) || null,
      createElement: (t) => nodo(t),
      addEventListener() {},
      querySelectorAll: () => [],
    },
    window: { location: { href: "historial.html", search: "", hash },
      history: { replaceState: (_e, _t, url) => direcciones.push(url) }, addEventListener() {} },
    localStorage: { getItem: (k) => (k === "access_token" ? TOKEN : k === "user" ? JSON.stringify({ id: 1, name: "Quien", role: "Administrador" }) : null),
      setItem() {}, removeItem() {} },
    fetch: async (url, opciones) => {
      llamadas.push({ url, opciones });
      return responder ? responder(url) : (url.startsWith("/api/history/resumen") ? ok(resumen()) : ok(CAMBIOS));
    },
    console: { error() {}, log() {} },
    setTimeout: (fn) => { fn(); return 1; },
    clearTimeout() {},
    URLSearchParams, Map, Array, Intl, Date: FechaFija,
  };
  vm.runInNewContext(leer("js/auth.js"), sandbox, { filename: "auth.js" });
  vm.runInNewContext(leer("js/historial.js"), sandbox, { filename: "historial.js" });
  return { sandbox, nodos, llamadas, direcciones, urls: () => llamadas.map((l) => l.url) };
}

const textos = (lista) => lista.map((n) => n.textContent);
const lineas = (nodos) => nodos.get("hist-cambios").children.flatMap((dia) => dia.children[1].children);

test("historial.html: dos columnas como Departamentos, sin código ni estilos inline", () => {
  const html = leer("historial.html");
  assert.doesNotMatch(html, /\sstyle="|<script>(?!<)|<script(?![^>]*src=)[^>]*>|\son[a-z]+="/i);
  assert.match(html, /<script src="js\/guardia.js" data-permiso="historial_global"><\/script>/, "mismos permisos que antes");
  assert.match(html, /data-permiso="historial_global"><svg/, "el enlace del menú sigue igual");
  assert.match(html, /<main class="contenido historial-personas">/);
  assert.match(html, /<div class="deptos-layout" id="hist-layout" hidden>\s*<div class="deptos-columna">\s*<div class="deptos-lista" id="hist-lista" role="tablist" aria-orientation="vertical" aria-label="Personas"/);
  assert.match(html, /<section class="deptos-detalle" id="hist-detalle" role="tabpanel" tabindex="0">/);
  assert.match(html, /<select id="hist-periodo">\s*<option value="hoy">Hoy<\/option>\s*<option value="7" selected>Últimos 7 días<\/option>\s*<option value="30">Últimos 30 días<\/option>/);
  assert.match(html, /<input type="search" id="hist-buscar" placeholder="Número o título"/);
  assert.match(html, /<ul class="depto-cajas hist-cajas" id="hist-cajas"/);
  assert.match(html, /<button type="button" id="hist-ver-mas" class="secundario" hidden>Ver más<\/button>/);
  assert.doesNotMatch(html, /<table/, "sin la tabla de antes");
});

test("historial.js no usa estilos inline y solo usa innerHTML para sus íconos fijos", () => {
  const js = leer("js/historial.js");
  assert.doesNotMatch(js, /\.style\b|setAttribute\(\s*["']style|insertAdjacentHTML/);
  const usos = [...js.matchAll(/innerHTML = ([A-Z_]+);/g)].map((m) => m[1]);
  assert.deepEqual(usos, ["ICONO_TODAS", "ICONO_SISTEMA"]);
  assert.equal((js.match(/innerHTML/g) || []).length, 2);
});

test("CSS: mismas tarjetas que Departamentos, avatar a la izquierda, 4 cajas y líneas sin scroll de costado", () => {
  const css = leer("css/estilos.css");
  assert.match(css, /\.app \.contenido\.departamentos,\s*\.app \.contenido\.historial-personas \{\s*max-width: none;/);
  assert.match(css, /\.depto-boton\.hist-persona \{\s*grid-template-columns: auto minmax\(0, 1fr\) auto;/);
  assert.match(css, /\.hist-persona \.hist-avatar \{\s*grid-column: 1;\s*grid-row: 1 \/ 3;/);
  assert.match(css, /\.hist-persona \.depto-pastilla \{\s*grid-column: 3;/);
  assert.match(css, /\.depto-boton\.hist-todas \+ \.depto-boton \{\s*border-top-color: var\(--color-borde-fuerte\);/);
  assert.match(css, /\.hist-avatar \{[^}]*border-radius: 50%;/);
  assert.match(css, /\.hist-cajas \{\s*grid-template-columns: repeat\(4, minmax\(0, 1fr\)\);/);
  assert.match(css, /\.hist-ticket-titulo \{[^}]*text-overflow: ellipsis;/);
  const celular = css.match(/Celular: cada cambio[\s\S]*?@media \(max-width: 700px\) \{[\s\S]*?\n\}/)[0];
  assert.match(celular, /\.hist-linea,\s*\.hist-linea\.con-autor \{\s*display: flex;\s*flex-wrap: wrap;/);
  assert.match(celular, /\.hist-cajas \{\s*grid-template-columns: repeat\(2, minmax\(0, 1fr\)\);/);
});

test("se piden el resumen y los primeros 50 cambios con el Bearer token", async () => {
  const { sandbox, llamadas, urls } = montar();
  await sandbox.iniciarHistorial();
  assert.deepEqual(urls(), [
    "/api/history/resumen?persona=todas&periodo=7",
    "/api/history?persona=todas&periodo=7&limit=50&offset=0",
  ]);
  for (const { opciones } of llamadas) assert.equal(opciones.headers.Authorization, `Bearer ${TOKEN}`);
});

test("la lista: «Todas las personas» arriba y las personas con cambios, con iniciales, «N cambios» y la pastilla", async () => {
  const { sandbox, nodos, direcciones } = montar();
  await sandbox.iniciarHistorial();
  assert.equal(nodos.get("hist-layout").hidden, false);
  assert.equal(nodos.get("estado-carga").hidden, true);
  const botones = nodos.get("hist-lista").children;
  assert.deepEqual(botones.map((b) => b.children[1].textContent), ["Todas las personas", "Daniel Sáenz", "Sistema"],
    "Sofía no tiene cambios en el período: no aparece");
  const [todas, daniel, sistema] = botones;
  assert.deepEqual(daniel.children.map((h) => h.className.split(" ")[0]),
    ["hist-avatar", "depto-boton-nombre", "depto-boton-abiertos", "depto-pastilla"]);
  assert.equal(daniel.children[0].textContent, "DS");
  assert.match(daniel.children[0].className, /tono-avatar-\d/);
  assert.equal(daniel.children[2].textContent, "3 cambios");
  assert.equal(daniel.children[3].textContent, "3");
  assert.equal(sistema.children[2].textContent, "1 cambio");
  assert.match(sistema.className, /hist-sistema/);
  assert.match(todas.className, /hist-todas/);
  assert.equal(todas.children[3].textContent, "4");
  assert.equal(todas.attrs.role, "tab");
  assert.equal(todas.id, "tab-persona-todas");
  assert.equal(todas.attrs["aria-selected"], "true");
  assert.match(todas.className, /\belegido\b/);
  assert.equal(todas.tabIndex, 0);
  assert.equal(daniel.tabIndex, -1);
  assert.equal(nodos.get("hist-detalle").attrs["aria-labelledby"], "tab-persona-todas");
  assert.deepEqual(direcciones, [], "al entrar no se toca la dirección");
});

test("el detalle con «Todas»: cajas, días con título y una línea por cambio con quién lo hizo", async () => {
  const { sandbox, nodos } = montar();
  await sandbox.iniciarHistorial();
  assert.equal(nodos.get("hist-nombre").textContent, "Todas las personas");
  assert.equal(nodos.get("hist-total").textContent, "4 cambios en el período");
  const cajas = nodos.get("hist-cajas").children;
  assert.deepEqual(cajas.map((c) => [c.children[1].textContent, c.children[0].textContent]),
    [["Cambios", "4"], ["Tickets tocados", "2"], ["Comentarios", "1"], ["Cambios de estado", "2"]]);
  assert.match(cajas[0].className, /depto-caja-abiertos/);

  const dias = nodos.get("hist-cambios").children;
  assert.deepEqual(dias.map((d) => d.children[0].textContent),
    ["Hoy · jueves 12 de noviembre", "Ayer · miércoles 11 de noviembre", "Lunes 9 de noviembre"]);
  assert.match(dias[0].children[0].className, /depto-subtitulo/, "títulos chicos en mayúsculas (CSS)");
  assert.equal(dias[0].children[1].children.length, 2);

  const [primera] = lineas(nodos);
  assert.match(primera.className, /con-autor/);
  assert.equal(primera.children[0].textContent, "1:01 p. m.");
  assert.equal(primera.children[1].textContent, "Daniel Sáenz");
  assert.equal(primera.children[1].dataset.iniciales, "DS");
  const ticket = primera.children[2];
  assert.equal(ticket.children[0].textContent, "#7");
  assert.equal(ticket.children[0].href, "detalle.html?id=7");
  assert.equal(ticket.children[1].textContent, "Impresora sin conexión");
  assert.equal(primera.children[3].textContent, "comentó «hola»");
  assert.deepEqual(lineas(nodos).map((l) => l.children[3].textContent), [
    "comentó «hola»", "cambió el estado: Nuevo → En proceso",
    "asignó el ticket a Daniel Sáenz", "lo cerró automáticamente"]);
  assert.equal(lineas(nodos)[3].children[1].textContent, "Sistema");
  assert.equal(nodos.get("hist-ver-mas").hidden, true, "4 de 4: sin «Ver más»");
  assert.equal(nodos.get("hist-vacio").hidden, true);
});

test("elegir una persona: su rol y departamento, la dirección y las líneas sin el nombre", async () => {
  const { sandbox, nodos, direcciones, urls } = montar();
  await sandbox.iniciarHistorial();
  const daniel = nodos.get("hist-lista").children[1];
  daniel.listeners.click();
  await new Promise((r) => setImmediate(r));
  assert.equal(nodos.get("hist-nombre").textContent, "Daniel Sáenz");
  assert.equal(nodos.get("hist-rol").textContent, "Técnico · Redes e Infraestructura");
  assert.equal(nodos.get("hist-total").textContent, "3 cambios en el período");
  assert.equal(daniel.attrs["aria-selected"], "true");
  assert.deepEqual(direcciones, ["#persona=12&periodo=7"]);
  assert.ok(urls().includes("/api/history?persona=12&periodo=7&limit=50&offset=0"));
  const [primera] = lineas(nodos);
  assert.doesNotMatch(primera.className, /con-autor/);
  assert.deepEqual(primera.children.map((h) => h.className), ["hist-hora", "hist-ticket", "hist-frase"]);
});

test("con teclado: flechas, Inicio y Fin cambian de persona", async () => {
  const { sandbox, nodos } = montar();
  await sandbox.iniciarHistorial();
  const botones = nodos.get("hist-lista").children;
  const tecla = (boton, key) => { let evitado = false; boton.listeners.keydown({ key, preventDefault() { evitado = true; } }); return evitado; };
  assert.equal(tecla(botones[0], "ArrowDown"), true);
  assert.equal(botones[1].attrs["aria-selected"], "true");
  assert.equal(botones[1].enfocado, true);
  tecla(botones[1], "End");
  assert.equal(botones[2].attrs["aria-selected"], "true");
  tecla(botones[2], "ArrowDown");
  assert.equal(botones[0].attrs["aria-selected"], "true", "vuelve al primero");
  tecla(botones[0], "ArrowUp");
  assert.equal(botones[2].attrs["aria-selected"], "true");
  tecla(botones[2], "Home");
  assert.equal(botones[0].attrs["aria-selected"], "true");
  assert.equal(tecla(botones[0], "a"), false, "otras teclas no hacen nada");
});

test("al recargar con #persona=sistema&periodo=30 se mantienen; lo inválido vuelve a lo de siempre", async () => {
  const { sandbox, nodos, urls } = montar({ hash: "#persona=sistema&periodo=30" });
  await sandbox.iniciarHistorial();
  assert.equal(urls()[0], "/api/history/resumen?persona=sistema&periodo=30");
  assert.equal(nodos.get("hist-periodo").value, "30");
  assert.equal(nodos.get("hist-nombre").textContent, "Sistema");
  assert.equal(nodos.get("hist-rol").textContent, "Cambios automáticos");
  assert.deepEqual({ ...sandbox.leerHash("#persona=abc&periodo=90") }, { persona: "todas", periodo: "7" });
  assert.deepEqual({ ...sandbox.leerHash("#persona=5&periodo=hoy") }, { persona: "5", periodo: "hoy" });
  assert.equal(sandbox.armarHash("12", "hoy"), "#persona=12&periodo=hoy");

  const sofia = montar({ hash: "#persona=5" });
  await sofia.sandbox.iniciarHistorial();
  assert.deepEqual(textos(sofia.nodos.get("hist-lista").children.map((b) => b.children[1])),
    ["Todas las personas", "Daniel Sáenz", "Sistema", "Sofía Solicitante"], "la elegida aparece aunque no tenga cambios");
  assert.equal(sofia.nodos.get("hist-total").textContent, "0 cambios en el período");

  const borrada = montar({ hash: "#persona=99" });
  await borrada.sandbox.iniciarHistorial();
  await new Promise((r) => setImmediate(r));
  assert.equal(borrada.nodos.get("hist-nombre").textContent, "Todas las personas");
  assert.equal(borrada.direcciones.at(-1), "#persona=todas&periodo=7");
});

test("cambiar el período o buscar vuelve a pedir con el filtro", async () => {
  const { sandbox, nodos, urls, direcciones } = montar();
  await sandbox.iniciarHistorial();
  const periodo = nodos.get("hist-periodo");
  periodo.value = "hoy";
  periodo.listeners.change();
  await new Promise((r) => setImmediate(r));
  assert.ok(urls().includes("/api/history/resumen?persona=todas&periodo=hoy"));
  assert.equal(direcciones.at(-1), "#persona=todas&periodo=hoy");

  const buscar = nodos.get("hist-buscar");
  buscar.value = " #7 ";
  buscar.listeners.input();
  await new Promise((r) => setImmediate(r));
  assert.ok(urls().includes("/api/history?persona=todas&periodo=hoy&buscar=%237&limit=50&offset=0"));
  assert.ok(urls().includes("/api/history/resumen?persona=todas&periodo=hoy&buscar=%237"));
});

test("«Ver más» trae los 50 siguientes y sigue en el mismo día", async () => {
  const pagina = (desde, n) => Array.from({ length: n }, (_, i) => ({ ...CAMBIOS[0], id: 1000 - desde - i }));
  const { sandbox, nodos, urls } = montar({
    responder: (url) => {
      if (url.startsWith("/api/history/resumen")) return ok(resumen({ cajas: { ...CAJAS, cambios: 70 } }));
      return ok(url.includes("offset=50") ? pagina(50, 20) : pagina(0, 50));
    },
  });
  await sandbox.iniciarHistorial();
  const verMas = nodos.get("hist-ver-mas");
  assert.equal(verMas.hidden, false);
  assert.equal(verMas.attrs["aria-label"], "Ver más cambios (faltan 20)");
  assert.equal(lineas(nodos).length, 50);
  await verMas.listeners.click();
  assert.equal(urls().at(-1), "/api/history?persona=todas&periodo=7&limit=50&offset=50");
  assert.equal(lineas(nodos).length, 70);
  assert.equal(nodos.get("hist-cambios").children.length, 1, "mismo día: un solo título");
  assert.equal(verMas.hidden, true);
});

test("sin cambios en el período o sin coincidencias, un aviso", async () => {
  const vacio = montar({
    responder: (url) => ok(url.startsWith("/api/history/resumen")
      ? resumen({ total: 0, cajas: { cambios: 0, tickets: 0, comentarios: 0, cambios_estado: 0 } }) : []),
  });
  await vacio.sandbox.iniciarHistorial();
  assert.equal(vacio.nodos.get("hist-vacio").hidden, false);
  assert.equal(vacio.nodos.get("hist-vacio").textContent, "No hay cambios en este período.");
  const buscar = vacio.nodos.get("hist-buscar");
  buscar.value = "zzz";
  buscar.listeners.input();
  await new Promise((r) => setImmediate(r));
  assert.equal(vacio.nodos.get("hist-vacio").textContent, "Ningún cambio en el período coincide con «zzz».");
});

test("frases de cada tipo de cambio", () => {
  const { sandbox } = montar();
  const f = (entry) => sandbox.fraseCambio(entry);
  assert.equal(f({ action: "commented", new_value: "hola" }), "comentó «hola»");
  assert.equal(f({ action: "Cambio de estado", old_value: "Nuevo", new_value: "En proceso" }), "cambió el estado: Nuevo → En proceso");
  assert.equal(f({ action: "assigned", new_value: "Daniel Sáenz" }), "asignó el ticket a Daniel Sáenz");
  assert.equal(f({ action: "assigned", old_value: "Ana", new_value: null }), "quitó la asignación");
  assert.equal(f({ action: "area_changed", old_value: null, new_value: "Redes" }), "cambió el departamento a Redes");
  assert.equal(f({ action: "attachment_added", field: "adjunto", new_value: "foto.jpg" }), "adjuntó foto.jpg");
  assert.equal(f({ action: "attachment_added", field: "correo", new_value: "foto.jpg" }), "adjuntó foto.jpg (por correo)");
  assert.equal(f({ action: "attachment_deleted", old_value: "viejo.pdf" }), "eliminó el adjunto viejo.pdf");
  assert.equal(f({ action: "Cierre automático", old_value: "Resuelto", new_value: "Cerrado" }), "lo cerró automáticamente");
  assert.equal(f({ action: "Reabierto por respuesta" }), "lo reabrió por la respuesta del solicitante");
  assert.equal(f({ action: "created", field: null, new_value: null }), "creó el ticket");
  assert.equal(f({ action: "created", field: "correo", new_value: "Ticket creado desde correo…" }), "creó el ticket desde un correo");
  assert.equal(f({ action: "created", field: "assigned_to_id", new_value: "Karla" }), "creó el ticket (asignado automáticamente a Karla)");
  assert.equal(f({ action: "updated", field: "priority", old_value: "Media", new_value: "Alta" }), "cambió la prioridad: Media → Alta");
  assert.equal(f({ action: "updated", field: "title", old_value: "A", new_value: "B" }), "cambió el título: «A» → «B»");
  assert.equal(f({ action: "assigned", new_value: "4" }), "asignó el ticket a Usuario #4", "registros viejos con id");
  assert.equal(f({ action: "commented", new_value: "x".repeat(200) }).length, "comentó «»".length + 80);
});

test("registros viejos con autor «Anónimo» o vacío se muestran como Sistema", () => {
  const { sandbox } = montar();
  assert.equal(sandbox.formatAutor({ author: "Anónimo" }), "Sistema");
  assert.equal(sandbox.formatAutor({ author: null }), "Sistema");
  assert.equal(sandbox.formatAutor({ author: "  " }), "Sistema");
  assert.equal(sandbox.formatAutor({ author: "Ana Pérez" }), "Ana Pérez");
});

test("títulos de día: hoy, ayer, días de la semana y otro año", () => {
  const { sandbox } = montar();
  assert.equal(sandbox.tituloDia("2026-11-13T05:59:00Z").texto, "Hoy · jueves 12 de noviembre", "11:59 p. m. en Costa Rica");
  assert.equal(sandbox.tituloDia("2026-11-12T05:59:00Z").texto, "Ayer · miércoles 11 de noviembre");
  assert.equal(sandbox.tituloDia("2026-11-01T18:00:00Z").texto, "Domingo 1 de noviembre");
  assert.equal(sandbox.tituloDia("2025-12-31T18:00:00Z").texto, "Miércoles 31 de diciembre de 2025");
});

test("errores: sin permiso, error de la API y sin conexión", async () => {
  const prohibido = montar({ responder: async () => ({ ok: false, status: 403, json: async () => ({}) }) });
  await prohibido.sandbox.iniciarHistorial();
  assert.equal(prohibido.nodos.get("estado-carga").textContent, "Su rol no tiene permiso para ver el historial.");
  assert.equal(prohibido.nodos.get("hist-layout").hidden, true);

  const falla = montar({ responder: async () => ({ ok: false, status: 500, json: async () => ({}) }) });
  await falla.sandbox.iniciarHistorial();
  assert.equal(falla.nodos.get("estado-carga").textContent, "No se pudo cargar el historial (500).");
  assert.match(falla.nodos.get("estado-carga").className, /error/);

  const sinRed = montar({ responder: async () => { throw new TypeError("Failed to fetch"); } });
  await sinRed.sandbox.iniciarHistorial();
  assert.match(sinRed.nodos.get("estado-carga").className, /error/);
  assert.equal(sinRed.nodos.get("estado-carga").textContent,
    "No se pudo conectar con el servidor. Verifique que esté en funcionamiento.");
  assert.equal(sinRed.nodos.get("hist-layout").hidden, true);
});
