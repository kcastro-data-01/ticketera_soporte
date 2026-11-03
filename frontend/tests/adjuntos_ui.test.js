/* Pruebas de los adjuntos en el detalle del ticket (frontend/js/adjuntos.js).
   Ejecutar con: node --test frontend/tests/adjuntos_ui.test.js */

"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const raiz = path.join(__dirname, "..");
const authSource = fs.readFileSync(path.join(raiz, "js", "auth.js"), "utf8");
const adjSource = fs.readFileSync(path.join(raiz, "js", "adjuntos.js"), "utf8");
const detalleHtml = fs.readFileSync(path.join(raiz, "detalle.html"), "utf8");
const detalleJs = fs.readFileSync(path.join(raiz, "js", "detalle.js"), "utf8");

function nodo(tag) {
  return {
    tag, id: "", type: "", className: "", textContent: "", value: "", hidden: false,
    disabled: false, src: "", href: "", download: "", clicked: 0, removed: false,
    attrs: {}, children: [], listeners: {},
    appendChild(h) { this.children.push(h); return h; },
    replaceChildren(...h) { this.children = h; },
    addEventListener(t, fn) { (this.listeners[t] = this.listeners[t] || []).push(fn); },
    setAttribute(k, v) { this.attrs[k] = v; },
    click() { this.clicked += 1; (this.listeners.click || []).forEach((fn) => fn()); },
    remove() { this.removed = true; },
  };
}

function texto(n) {
  return (n.textContent || "") + (n.children || []).map(texto).join("");
}

function buscarTodos(n, pred, out = []) {
  if (pred(n)) out.push(n);
  (n.children || []).forEach((h) => buscarTodos(h, pred, out));
  return out;
}

const botones = (n, etiqueta) => buscarTodos(n, (x) => x.tag === "button" && x.textContent === etiqueta);

function respuesta(status, body) {
  return {
    ok: status >= 200 && status < 300, status,
    json: async () => body,
    blob: async () => ({ size: 3, type: "image/png" }),
  };
}

function adjunto(extra) {
  return {
    id: 1, ticket_id: 7, nombre: "captura.png", tipo: "image/png", tamano: 1536,
    es_imagen: true, subido_por: "Ana Solicitante", subido_por_id: 5,
    creado: "2026-11-03T15:00:00Z", puede_eliminar: true, ...extra,
  };
}

function lista(adjuntos, extra) {
  return { adjuntos, puede_subir: true, cerrado: false, max_archivos: 10, max_bytes: 4 * 1024 * 1024, ...extra };
}

const IDS = ["seccion-adjuntos", "adj-subir", "adj-foto", "adj-archivos", "adj-camara",
  "adj-acciones", "adj-nota", "adj-estado", "adj-lista"];

function crear({ fetchImpl, tactil = false, imagen = null }) {
  const ids = {};
  IDS.forEach((id) => { ids[id] = nodo(id.startsWith("adj-subir") || id === "adj-foto" ? "button" : "div"); });
  ids["adj-acciones"].hidden = true;
  ids["adj-foto"].hidden = true;
  ids["adj-lista"].hidden = true;
  const store = new Map([["access_token", "tok"], ["user", JSON.stringify({ id: 5, name: "Ana", role: "Solicitante" })]]);
  const llamadas = [];
  const avisos = [];
  const creados = [];
  const lienzos = [];
  const body = nodo("body");
  const sandbox = {
    document: {
      getElementById: (id) => ids[id] || null,
      createElement: (tag) => {
        const n = nodo(tag);
        if (tag === "canvas") {
          n.getContext = () => ({ drawImage() {} });
          n.toBlob = (cb, tipo) => cb({ size: 1000, type: tipo });
          lienzos.push(n);
        }
        creados.push(n);
        return n;
      },
      addEventListener() {},
    },
    window: {
      location: { search: "?id=7", href: "" },
      matchMedia: (q) => ({ matches: tactil && q === "(pointer: coarse)" }),
      confirm: () => true,
    },
    localStorage: { getItem: (k) => store.get(k) ?? null, setItem: (k, v) => store.set(k, v), removeItem: (k) => store.delete(k) },
    fetch: (url, options = {}) => {
      llamadas.push({ url, method: options.method || "GET", headers: options.headers || {}, body: options.body });
      return fetchImpl(url, options);
    },
    URL: { createObjectURL: () => "blob:local/1", revokeObjectURL() {} },
    console: { error() {} },
    URLSearchParams, setTimeout: () => 0, clearTimeout() {}, Date, Number, Math, Array, Promise,
    encodeURIComponent,
  };
  if (imagen) sandbox.createImageBitmap = async () => ({ ...imagen, close() {} });
  vm.createContext(sandbox);
  vm.runInContext(authSource, sandbox);
  vm.runInContext(adjSource, sandbox);
  sandbox.document.body = body;
  sandbox.mostrarAviso = (mensaje, tipo) => avisos.push({ mensaje, tipo });
  // Sin DOM real, confirmarAccion usa window.confirm.
  sandbox.document.body = undefined;
  return { sandbox, ids, llamadas, avisos, creados, lienzos };
}

const esperar = () => new Promise((r) => setImmediate(r));

test("detalle.html tiene la sección Adjuntos con sus botones y carga adjuntos.js", () => {
  assert.match(detalleHtml, /<section id="seccion-adjuntos"[^>]*>\s*<h2 id="adjuntos-titulo">Adjuntos<\/h2>/);
  assert.match(detalleHtml, /<button type="button" id="adj-subir">Adjuntar archivos<\/button>/);
  assert.match(detalleHtml, /id="adj-foto"[^>]*hidden>Sacar foto<\/button>/);
  assert.match(detalleHtml, /id="adj-archivos" multiple hidden\s+accept="\.jpg,\.jpeg,\.png,\.pdf,\.docx,\.xlsx,\.txt/);
  assert.match(detalleHtml, /id="adj-camara" accept="image\/\*" capture="environment" hidden/);
  assert.match(detalleHtml, /<script src="js\/adjuntos\.js" defer><\/script>/);
  assert.match(detalleJs, /adjuntosTicketActualizado\(ticket\)/);
});

test("lista nombre, tamaño, quién y cuándo; miniatura en imágenes pedida con la sesión", async () => {
  const datos = lista([adjunto(), adjunto({ id: 2, nombre: "factura.pdf", tipo: "application/pdf", es_imagen: false, tamano: 900, puede_eliminar: false, subido_por: "Carlos" })]);
  const a = crear({ fetchImpl: async (url) => respuesta(200, url.endsWith("/adjuntos") ? datos : null) });
  await a.sandbox.iniciarAdjuntos();
  await esperar();
  const ul = a.ids["adj-lista"];
  assert.equal(ul.hidden, false);
  assert.equal(ul.children.length, 2);
  const [png, pdf] = ul.children;
  assert.match(texto(png), /captura\.png/);
  assert.match(texto(png), /1,5 KB · Ana Solicitante · /);
  assert.match(texto(pdf), /900 B · Carlos/);

  const img = buscarTodos(png, (n) => n.tag === "img")[0];
  assert.equal(img.src, "blob:local/1");
  const pedida = a.llamadas.find((l) => l.url === "/api/tickets/7/adjuntos/1/archivo");
  assert.equal(pedida.headers.Authorization, "Bearer tok");
  assert.equal(buscarTodos(pdf, (n) => n.tag === "img").length, 0, "sin miniatura en el PDF");
  assert.equal(buscarTodos(pdf, (n) => n.className === "adjunto-icono")[0].textContent, "PDF");

  assert.equal(botones(png, "Descargar").length, 1);
  assert.equal(botones(png, "Eliminar").length, 1);
  assert.equal(botones(pdf, "Descargar").length, 1);
  assert.equal(botones(pdf, "Eliminar").length, 0, "solo quien lo subió o el Administrador");
  assert.equal(a.ids["adj-acciones"].hidden, false);
  assert.match(a.ids["adj-nota"].textContent, /hasta 4 MB cada uno y 10 por ticket \(2 de 10\)/);
});

test("sin adjuntos muestra el aviso vacío", async () => {
  const a = crear({ fetchImpl: async () => respuesta(200, lista([])) });
  await a.sandbox.iniciarAdjuntos();
  assert.equal(a.ids["adj-lista"].hidden, true);
  assert.equal(a.ids["adj-estado"].textContent, "Todavía no hay adjuntos.");
});

test("en Cerrado no hay botones para subir ni eliminar", async () => {
  const datos = lista([adjunto({ puede_eliminar: false })], { puede_subir: false, cerrado: true });
  const a = crear({ fetchImpl: async () => respuesta(200, datos) });
  await a.sandbox.iniciarAdjuntos();
  assert.equal(a.ids["adj-acciones"].hidden, true);
  assert.match(a.ids["adj-nota"].textContent, /Cerrado: no se agregan ni se eliminan adjuntos/);
  assert.equal(botones(a.ids["adj-lista"], "Eliminar").length, 0);
  assert.equal(botones(a.ids["adj-lista"], "Descargar").length, 1);
});

test("«Sacar foto» solo en pantallas táctiles", async () => {
  const escritorio = crear({ fetchImpl: async () => respuesta(200, lista([])) });
  await escritorio.sandbox.iniciarAdjuntos();
  assert.equal(escritorio.ids["adj-foto"].hidden, true);
  const celular = crear({ tactil: true, fetchImpl: async () => respuesta(200, lista([])) });
  await celular.sandbox.iniciarAdjuntos();
  assert.equal(celular.ids["adj-foto"].hidden, false);
  celular.ids["adj-foto"].listeners.click[0]();
  assert.equal(celular.ids["adj-camara"].clicked, 1);
});

test("sube cada archivo en su propia llamada, con el nombre en ?nombre=", async () => {
  const a = crear({ fetchImpl: async (url, o) => respuesta(o.method === "POST" ? 201 : 200, lista([])) });
  await a.sandbox.iniciarAdjuntos();
  const pdf = { name: "Factura año.pdf", size: 2000, type: "application/pdf" };
  const txt = { name: "log.txt", size: 10, type: "text/plain" };
  await a.sandbox.subirArchivos([pdf, txt]);
  const posts = a.llamadas.filter((l) => l.method === "POST");
  assert.deepEqual(posts.map((l) => l.url), [
    "/api/tickets/7/adjuntos?nombre=Factura%20a%C3%B1o.pdf",
    "/api/tickets/7/adjuntos?nombre=log.txt",
  ]);
  assert.equal(posts[0].headers["Content-Type"], "application/octet-stream");
  assert.equal(posts[0].body, pdf);
  assert.deepEqual(a.avisos.at(-1), { mensaje: "2 archivos adjuntados.", tipo: "exito" });
  assert.equal(a.llamadas.at(-1).url, "/api/tickets/7/adjuntos", "vuelve a cargar la lista");
});

test("tipo no permitido o más de 4 MB: no se envía y se explica", async () => {
  const a = crear({ fetchImpl: async () => respuesta(200, lista([])) });
  await a.sandbox.iniciarAdjuntos();
  await a.sandbox.subirArchivos([
    { name: "programa.exe", size: 10, type: "application/x-msdownload" },
    { name: "enorme.pdf", size: 4 * 1024 * 1024 + 1, type: "application/pdf" },
  ]);
  assert.equal(a.llamadas.filter((l) => l.method === "POST").length, 0);
  assert.match(a.ids["adj-estado"].textContent, /«programa\.exe»: tipo no permitido\. Se aceptan jpg, png, pdf, docx, xlsx o txt\./);
  assert.match(a.ids["adj-estado"].textContent, /«enorme\.pdf» pesa más de 4 MB\./);
  assert.equal(a.ids["adj-estado"].className, "estado error");
});

test("respeta el máximo de 10: con 9 solo sube uno más", async () => {
  const nueve = Array.from({ length: 9 }, (_, i) => adjunto({ id: i + 1, es_imagen: false, nombre: `a${i}.txt` }));
  const a = crear({ fetchImpl: async (url, o) => respuesta(o.method === "POST" ? 201 : 200, lista(nueve)) });
  await a.sandbox.iniciarAdjuntos();
  const f = (n) => ({ name: `${n}.txt`, size: 5, type: "text/plain" });
  await a.sandbox.subirArchivos([f("x"), f("y"), f("z")]);
  assert.equal(a.llamadas.filter((l) => l.method === "POST").length, 1);
  assert.match(a.ids["adj-estado"].textContent, /Solo se pueden agregar 1 archivo\(s\) más \(máximo 10 por ticket\)/);
});

test("el error del servidor se muestra tal cual", async () => {
  const a = crear({
    fetchImpl: async (url, o) => (o.method === "POST"
      ? respuesta(422, { detail: "«a.png»: el contenido no corresponde a un archivo PNG válido." })
      : respuesta(200, lista([]))),
  });
  await a.sandbox.iniciarAdjuntos();
  await a.sandbox.subirArchivos([{ name: "a.png", size: 50, type: "text/plain" }]);
  assert.match(a.ids["adj-estado"].textContent, /no corresponde a un archivo PNG válido/);
});

test("una foto grande se achica a 2000 px de lado antes de subirla", async () => {
  const a = crear({
    imagen: { width: 4000, height: 3000 },
    fetchImpl: async (url, o) => respuesta(o.method === "POST" ? 201 : 200, lista([])),
  });
  await a.sandbox.iniciarAdjuntos();
  await a.sandbox.subirArchivos([{ name: "IMG_1234.jpg", size: 3500000, type: "image/jpeg" }]);
  assert.equal(a.lienzos.length, 1);
  assert.equal(a.lienzos[0].width, 2000);
  assert.equal(a.lienzos[0].height, 1500);
  const post = a.llamadas.find((l) => l.method === "POST");
  assert.equal(post.url, "/api/tickets/7/adjuntos?nombre=IMG_1234.jpg");
  assert.deepEqual(post.body, { size: 1000, type: "image/jpeg" });
});

test("una foto HEIC de la cámara se convierte a JPG; una PNG chica se sube tal cual", async () => {
  const a = crear({
    imagen: { width: 1200, height: 900 },
    fetchImpl: async (url, o) => respuesta(o.method === "POST" ? 201 : 200, lista([])),
  });
  await a.sandbox.iniciarAdjuntos();
  await a.sandbox.subirArchivos([{ name: "foto.heic", size: 900000, type: "image/heic" }]);
  assert.equal(a.llamadas.find((l) => l.method === "POST").url, "/api/tickets/7/adjuntos?nombre=foto.jpg");

  const png = { name: "captura.png", size: 80000, type: "image/png" };
  await a.sandbox.subirArchivos([png]);
  assert.equal(a.lienzos.length, 1, "la PNG chica no pasa por el canvas");
  assert.equal(a.llamadas.filter((l) => l.method === "POST").at(-1).body, png);
});

test("Eliminar pide confirmación y llama a DELETE", async () => {
  const a = crear({ fetchImpl: async (url, o) => respuesta(o.method === "DELETE" ? 204 : 200, lista([adjunto()])) });
  await a.sandbox.iniciarAdjuntos();
  await botones(a.ids["adj-lista"], "Eliminar")[0].listeners.click[0]();
  await esperar();
  assert.ok(a.llamadas.some((l) => l.method === "DELETE" && l.url === "/api/tickets/7/adjuntos/1"));
  assert.deepEqual(a.avisos.at(-1), { mensaje: "«captura.png» eliminado.", tipo: "exito" });
});

test("Descargar baja el archivo con la sesión y lo guarda con su nombre", async () => {
  const a = crear({ fetchImpl: async () => respuesta(200, lista([adjunto({ es_imagen: false, nombre: "informe.docx" })])) });
  await a.sandbox.iniciarAdjuntos();
  a.sandbox.document.body = { appendChild() {} };
  await botones(a.ids["adj-lista"], "Descargar")[0].listeners.click[0]();
  const enlace = a.creados.find((n) => n.tag === "a");
  assert.equal(enlace.download, "informe.docx");
  assert.equal(enlace.href, "blob:local/1");
  assert.equal(enlace.clicked, 1);
  assert.equal(a.llamadas.at(-1).headers.Authorization, "Bearer tok");
});

test("los nombres se pintan como texto, no como HTML", async () => {
  const malicioso = "<img src=x onerror=alert(1)>.txt";
  const a = crear({ fetchImpl: async () => respuesta(200, lista([adjunto({ nombre: malicioso, es_imagen: false })])) });
  await a.sandbox.iniciarAdjuntos();
  const nombre = buscarTodos(a.ids["adj-lista"], (n) => n.className === "adjunto-nombre")[0];
  assert.equal(nombre.textContent, malicioso);
  assert.ok(!adjSource.includes("innerHTML"));
});

test("un ticket que no se ve esconde la sección", async () => {
  const a = crear({ fetchImpl: async () => respuesta(404, { detail: "Ticket 7 no encontrado" }) });
  await a.sandbox.iniciarAdjuntos();
  assert.equal(a.ids["seccion-adjuntos"].hidden, true);
});

test("si el ticket cambia de estado vuelve a pedir los adjuntos", async () => {
  const a = crear({ fetchImpl: async () => respuesta(200, lista([])) });
  a.sandbox.adjuntosTicketActualizado({ state: "En proceso" });
  const antes = a.llamadas.length;
  a.sandbox.adjuntosTicketActualizado({ state: "En proceso" });
  assert.equal(a.llamadas.length, antes, "mismo estado: no pide de nuevo");
  a.sandbox.adjuntosTicketActualizado({ state: "Cerrado" });
  assert.equal(a.llamadas.at(-1).url, "/api/tickets/7/adjuntos");
});

test("el historial nombra las subidas y los borrados", () => {
  const sandbox = { localStorage: { getItem: () => null }, document: undefined };
  vm.createContext(sandbox);
  vm.runInContext(authSource, sandbox);
  assert.deepEqual(
    { ...sandbox.describirHistorial({ action: "attachment_added", new_value: "factura.pdf" }) },
    { accion: "Adjuntó un archivo", detalle: "«factura.pdf»" },
  );
  assert.deepEqual(
    { ...sandbox.describirHistorial({ action: "attachment_deleted", old_value: "factura.pdf" }) },
    { accion: "Eliminó un adjunto", detalle: "«factura.pdf»" },
  );
});
