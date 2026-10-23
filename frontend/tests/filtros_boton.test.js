/* Botón «Filtros» del listado (app.js + index.html): muestra u oculta el
   recuadro de filtros, se recuerda en localStorage (por defecto, cerrado) y
   con filtros aplicados dice cuántos y queda resaltado. No cambia cómo se
   filtra.
   Ejecutar con: node --test frontend/tests/filtros_boton.test.js */

"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const leer = (archivo) => fs.readFileSync(path.join(__dirname, "..", archivo), "utf8");
const indexHtml = leer("index.html");
const css = leer("css/estilos.css");

const IDS = [
  "form-filtros", "search", "category", "priority", "state", "limpiar", "estado-carga", "lista-tickets",
  "paginacion", "pagina-anterior", "pagina-siguiente", "pagina-info", "tabla-tickets", "tablero",
  "filtros-boton", "filtros-texto",
];

function nodo(tag) {
  const clases = new Set();
  return {
    tag, value: "", textContent: "", children: [], dataset: {}, atributos: {}, listeners: {}, hidden: false,
    classList: {
      add: (c) => clases.add(c), remove: (c) => clases.delete(c), contains: (c) => clases.has(c),
      toggle: (c, si) => ((si ?? !clases.has(c)) ? clases.add(c) : clases.delete(c)),
    },
    setAttribute(k, v) { this.atributos[k] = String(v); },
    addEventListener(t, fn) { (this.listeners[t] = this.listeners[t] || []).push(fn); },
    appendChild(h) { this.children.push(h); return h; },
    append(...hs) { hs.forEach((h) => this.appendChild(h)); },
    replaceChildren(...hs) { this.children = hs; },
    reset() { ["search", "category", "priority", "state"].forEach((id) => { this.campos.get(id).value = ""; }); },
  };
}

async function montar({ guardado = null } = {}) {
  const nodos = new Map(IDS.map((id) => [id, nodo(id)]));
  nodos.get("form-filtros").campos = nodos;
  nodos.get("form-filtros").hidden = true; // como en index.html
  const store = new Map(guardado === null ? [] : [["filtros_abiertos", guardado]]);
  const pedidos = [];
  const sandbox = {
    document: {
      title: "",
      getElementById: (id) => nodos.get(id) || null,
      querySelector: () => null,
      querySelectorAll: () => [],
      createElement: nodo,
      addEventListener() {},
    },
    window: { location: { href: "", search: "" } },
    localStorage: {
      getItem: (k) => (k === "user" ? JSON.stringify({ id: 9, name: "José", role: "Técnico" })
        : k === "access_token" ? "t" : store.get(k) ?? null),
      setItem: (k, v) => store.set(k, v), removeItem: (k) => store.delete(k),
    },
    fetch: async (url) => {
      pedidos.push(url);
      return { ok: true, status: 200, headers: { get: () => "0" }, json: async () => (url.includes("summary") ? {} : []) };
    },
    console: { error() {}, log() {} },
    URLSearchParams, Map, Number, Object, String, Boolean, Date,
  };
  vm.createContext(sandbox);
  vm.runInContext(leer("js/auth.js"), sandbox);
  vm.runInContext(leer("js/app.js"), sandbox);
  sandbox.init();
  await esperar();
  return { nodos, store, pedidos };
}

const esperar = async () => { for (let i = 0; i < 10; i += 1) await new Promise((r) => setImmediate(r)); };
const clic = (n) => n.listeners.click.forEach((fn) => fn());
const enviar = (n) => n.listeners.submit.forEach((fn) => fn({ preventDefault() {} }));

test("index.html: botón Filtros con embudo antes de Tabla/Tablero y «Buscar» en el recuadro", () => {
  const barra = indexHtml.slice(indexHtml.indexOf('<div class="listado-barra">'), indexHtml.indexOf('<form id="form-filtros"'));
  assert.match(barra, /<div class="vista-tabs">\s*<button type="button" id="filtros-boton" class="vista-tab filtros-boton" aria-expanded="false" aria-controls="form-filtros"[^>]*><svg class="icono"[^>]*><path d="M3 5h18l-7 8\.5V19l-4 2v-7\.5z"\/><\/svg><span id="filtros-texto">Filtros<\/span><\/button>/);
  assert.ok(barra.indexOf('id="filtros-boton"') < barra.indexOf('id="ver-tabla"'));
  assert.doesNotMatch(barra.slice(barra.lastIndexOf("<div", barra.indexOf('id="filtros-boton"')), barra.indexOf('id="filtros-boton"')), /data-vista/, "también lo ve el Solicitante");
  assert.match(indexHtml, /<form id="form-filtros" class="filtros" hidden>/, "por defecto, cerrado");
  // «Buscar» (primario, el de siempre) junto a «Limpiar filtros», dentro del recuadro.
  const form = indexHtml.slice(indexHtml.indexOf('<form id="form-filtros"'), indexHtml.indexOf("</form>"));
  assert.match(form, /<button type="submit" id="buscar">Buscar<\/button>\s*<button type="button" id="limpiar" class="secundario">Limpiar filtros<\/button>/);
  // Enter en «Buscar» envía el formulario: el campo está dentro y hay un botón submit.
  assert.match(form, /<input\s+type="search"\s+id="search"/);
  assert.match(css, /\.vista-tabs \.filtros-boton \{\s*gap: 0\.4rem;/);
});

test("por defecto cerrado; el botón lo abre y lo cierra y se recuerda", async () => {
  const { nodos, store } = await montar();
  const form = nodos.get("form-filtros");
  const boton = nodos.get("filtros-boton");
  assert.equal(form.hidden, true);
  assert.equal(boton.atributos["aria-expanded"], "false");

  clic(boton);
  assert.equal(form.hidden, false);
  assert.equal(boton.atributos["aria-expanded"], "true");
  assert.equal(store.get("filtros_abiertos"), "1");

  clic(boton);
  assert.equal(form.hidden, true);
  assert.equal(store.get("filtros_abiertos"), "0");

  const abierto = await montar({ guardado: "1" });
  assert.equal(abierto.nodos.get("form-filtros").hidden, false, "se abre como quedó");
});

test("Buscar (o Enter en el campo) envía el formulario y pide el listado filtrado", async () => {
  const { nodos, pedidos } = await montar({ guardado: "1" });
  const antes = pedidos.length;
  nodos.get("search").value = "impresora";
  enviar(nodos.get("form-filtros"));
  await esperar();
  assert.equal(pedidos.length, antes + 1);
  assert.match(pedidos.at(-1), /search=impresora/);
});

test("con filtros aplicados dice cuántos y queda resaltado; sin filtros vuelve a «Filtros»", async () => {
  const { nodos, pedidos } = await montar({ guardado: "1" });
  const boton = nodos.get("filtros-boton");
  const texto = nodos.get("filtros-texto");
  assert.equal(texto.textContent, "Filtros");
  assert.equal(boton.classList.contains("activa"), false);

  nodos.get("search").value = "vpn";
  nodos.get("priority").value = "Alta";
  enviar(nodos.get("form-filtros"));
  await esperar();
  assert.equal(texto.textContent, "Filtros (2)");
  assert.equal(boton.classList.contains("activa"), true);
  assert.equal(boton.atributos["aria-pressed"], "true");
  // Filtra igual que antes: los mismos parámetros.
  assert.match(pedidos.at(-1), /search=vpn/);
  assert.match(pedidos.at(-1), /priority=Alta/);

  clic(nodos.get("limpiar"));
  await esperar();
  assert.equal(texto.textContent, "Filtros");
  assert.equal(boton.classList.contains("activa"), false);
});
