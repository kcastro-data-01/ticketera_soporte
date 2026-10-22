/* Mejoras visuales del chat del asistente (frontend/js/asistente.js):
   formato de las respuestas armado con nodos (nunca innerHTML con texto de
   la IA) y demás detalles de la ventana.
   Ejecutar con: node --test frontend/tests/chat_mejoras.test.js */

"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const leer = (archivo) => fs.readFileSync(path.join(__dirname, "..", archivo), "utf8");
const authSource = leer("js/auth.js");
const chatSource = leer("js/asistente.js");
const css = leer("css/estilos.css");

function nodo(tag) {
  const clases = new Set();
  const n = {
    tag, textContent: "", innerHTML: "", value: "", hidden: false, disabled: false, style: {},
    scrollHeight: 0, scrollTop: 0, clientHeight: 0, children: [], dataset: {}, atributos: {}, listeners: {}, href: "",
    get className() { return [...clases].join(" "); },
    set className(v) { clases.clear(); String(v).split(/\s+/).filter(Boolean).forEach((c) => clases.add(c)); },
    classList: {
      add: (c) => clases.add(c), remove: (c) => clases.delete(c), contains: (c) => clases.has(c),
      toggle: (c, si) => ((si ?? !clases.has(c)) ? clases.add(c) : clases.delete(c)),
    },
    setAttribute(k, v) { this.atributos[k] = String(v); },
    addEventListener(t, fn) { (this.listeners[t] = this.listeners[t] || []).push(fn); },
    appendChild(h) { this.children.push(h); return h; },
    append(...hs) { hs.forEach((h) => this.appendChild(h)); },
    replaceChildren(...hs) { this.children = hs; },
    remove() {}, focus() {},
  };
  return n;
}

/* Crea el chat con el rol indicado; `api` responde GET /api/tickets/{id}. */
function montar({ rol = "Técnico", api = {}, guardado = null, extra = {} } = {}) {
  const creados = [];
  const store = new Map([["access_token", "t"], ["user", JSON.stringify({ name: "José Solano", role: rol })]]);
  const sesion = new Map(guardado ? [["asistente_chat", JSON.stringify(guardado)]] : []);
  const pedidos = [];
  const temporizadores = [];
  const sandbox = {
    document: {
      getElementById: (id) => creados.find((n) => n.id === id) || null,
      createElement: (tag) => { const n = nodo(tag); creados.push(n); return n; },
      createTextNode: (t) => ({ tag: "#text", textContent: t, children: [] }),
      addEventListener() {},
      body: nodo("body"),
    },
    window: { location: { pathname: "/index.html", search: "", href: "" } },
    localStorage: { getItem: (k) => store.get(k) ?? null, setItem: (k, v) => store.set(k, v), removeItem: (k) => store.delete(k) },
    sessionStorage: { getItem: (k) => sesion.get(k) ?? null, setItem: (k, v) => sesion.set(k, v) },
    fetch: async (url) => {
      pedidos.push(url);
      const id = Number(/\/api\/tickets\/(\d+)$/.exec(url)?.[1]);
      const ticket = api[id];
      return { ok: Boolean(ticket), status: ticket ? 200 : 403, json: async () => ticket };
    },
    console: { error() {}, log() {} },
    URLSearchParams, Date,
    setTimeout: (fn, ms) => { temporizadores.push({ fn, ms }); return temporizadores.length; },
    clearTimeout() {},
    ...extra,
  };
  vm.createContext(sandbox);
  vm.runInContext(authSource, sandbox);
  vm.runInContext(chatSource, sandbox);
  sandbox.crearAsistente();
  const buscar = (clase) => creados.find((n) => n.className.split(" ").includes(clase));
  return { sandbox, creados, buscar, store, pedidos, temporizadores, lista: buscar("chat-lista"), boton: buscar("chat-boton") };
}

const esperar = async () => { for (let i = 0; i < 10; i += 1) await new Promise((r) => setImmediate(r)); };
const clic = (n) => (n.listeners.click || []).forEach((fn) => fn());
const texto = (n) => (n.textContent || "") + (n.children || []).map(texto).join("");
function todos(n, clase, out = []) {
  if (n.className && String(n.className).split(" ").includes(clase)) out.push(n);
  (n.children || []).forEach((h) => todos(h, clase, out));
  return out;
}

/* ---------- 1. Formato en las respuestas ---------- */

test("formato: negrita, listas con «-» y «1.», y «Resumen:» como título", () => {
  const { sandbox } = montar();
  const el = nodo("div");
  sandbox.pintarTexto(el, "Resumen:\nEl ticket **#7** está en **En proceso**.\n- Revisar la VPN\n- Reiniciar\n\n1. Primero\n2. Segundo\nFin.");
  const [titulo, parrafo, vinetas, numerada, fin] = el.children;
  assert.equal(titulo.tag, "strong");
  assert.equal(titulo.className, "chat-titulo-respuesta");
  assert.equal(titulo.textContent, "Resumen:");
  assert.equal(parrafo.tag, "p");
  const negritas = parrafo.children.filter((h) => h.tag === "strong");
  assert.equal(negritas.length, 2);
  assert.equal(negritas[0].children[0].tag, "a", "el #N sigue siendo enlace dentro de la negrita");
  assert.equal(negritas[0].children[0].href, "detalle.html?id=7");
  assert.equal(texto(negritas[1]), "En proceso");
  assert.equal(vinetas.tag, "ul");
  assert.deepEqual(vinetas.children.map(texto), ["Revisar la VPN", "Reiniciar"]);
  assert.equal(numerada.tag, "ol");
  assert.deepEqual(numerada.children.map(texto), ["Primero", "Segundo"]);
  assert.equal(texto(fin), "Fin.");
  assert.doesNotMatch(texto(el), /\*\*/, "no quedan los asteriscos");
});

test("formato: el texto de la IA nunca va a innerHTML", () => {
  const { sandbox } = montar();
  const el = nodo("div");
  sandbox.pintarTexto(el, "<img src=x onerror=alert(1)> **<b>hola</b>**");
  assert.equal(el.innerHTML, "");
  assert.match(texto(el), /<img src=x onerror=alert\(1\)>/, "se muestra como texto");
  const cuerpo = chatSource.slice(chatSource.indexOf("function pintarLinea"), chatSource.indexOf("/* Fila del asistente"));
  assert.doesNotMatch(cuerpo, /innerHTML/);
});

test("formato: frases comunes con dos puntos no se vuelven títulos", () => {
  const { sandbox } = montar();
  const el = nodo("div");
  sandbox.pintarTexto(el, "Buen día. ¿En qué le puedo ayudar? Puede consultar, por ejemplo:");
  assert.equal(el.children[0].tag, "p");
});

test("formato: CSS sin degradados y respetando los saltos", () => {
  assert.match(css, /\.chat-mensaje\.chat-formato \{\s*white-space: normal;/);
  assert.match(css, /\.chat-titulo-respuesta \{[^}]*font-weight: 600;/);
  const bloque = css.slice(css.indexOf("/* ---------- Asistente virtual"), css.indexOf("/* ---------- Nuevo ticket"));
  assert.doesNotMatch(bloque, /gradient/);
});
