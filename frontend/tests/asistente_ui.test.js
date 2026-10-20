/* Pruebas del chat del asistente (frontend/js/asistente.js): envía el ticket
   abierto en pantalla, corta si tarda demasiado y nunca muestra un texto
   inventado cuando la IA no responde.
   Ejecutar con: node --test frontend/tests/asistente_ui.test.js */

"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const authSource = fs.readFileSync(path.join(__dirname, "..", "js", "auth.js"), "utf8");
const chatSource = fs.readFileSync(path.join(__dirname, "..", "js", "asistente.js"), "utf8");

function nodo(tag) {
  return {
    tag,
    className: "",
    textContent: "",
    innerHTML: "",
    value: "",
    disabled: false,
    hidden: false,
    style: {},
    scrollHeight: 0,
    scrollTop: 0,
    children: [],
    appendChild(hijo) { this.children.push(hijo); return hijo; },
    append(...hijos) { this.children.push(...hijos); },
    replaceChildren(...hijos) { this.children = hijos; },
    remove() {},
    focus() {},
    setAttribute() {},
    addEventListener() {},
  };
}

function texto(n) {
  return (n.textContent || "") + n.children.map(texto).join("");
}

function crearChat({ pathname = "/detalle.html", search = "?id=7", fetchImpl, relojRapido = false }) {
  const ids = { "chat-lista": nodo("div"), "chat-entrada": nodo("textarea"), "chat-enviar": nodo("button") };
  const store = new Map([["access_token", "t"], ["user", JSON.stringify({ name: "José Solano", role: "Técnico" })]]);
  const llamadas = [];
  const sandbox = {
    document: {
      getElementById: (id) => ids[id] || null,
      createElement: nodo,
      createTextNode: (t) => ({ textContent: t, children: [] }),
      addEventListener() {},
    },
    window: { location: { pathname, search, href: "" } },
    localStorage: { getItem: (k) => store.get(k) ?? null, setItem: (k, v) => store.set(k, v), removeItem: (k) => store.delete(k) },
    sessionStorage: { getItem: () => null, setItem() {} },
    fetch: (url, options) => { llamadas.push({ url, options }); return fetchImpl(url, options); },
    console: { error() {}, log() {} },
    URLSearchParams,
    AbortController,
    TextDecoder,
    // Con relojRapido, los plazos (como el límite de 200 s) vencen enseguida.
    setTimeout: relojRapido ? (fn) => setTimeout(fn, 1) : setTimeout,
    clearTimeout,
  };
  vm.createContext(sandbox);
  vm.runInContext(authSource, sandbox);
  vm.runInContext(chatSource, sandbox);
  return { sandbox, ids, llamadas };
}

function ndjson(eventos) {
  const datos = new TextEncoder().encode(eventos.map((e) => JSON.stringify(e)).join("\n") + "\n");
  let leido = false;
  return {
    ok: true,
    status: 200,
    body: { getReader: () => ({ read: async () => (leido ? { done: true } : ((leido = true), { value: datos, done: false })) }) },
  };
}

test("ticketEnPantalla(): solo en detalle.html con un id válido", () => {
  assert.equal(crearChat({ fetchImpl: () => {} }).sandbox.ticketEnPantalla(), 7);
  assert.equal(crearChat({ pathname: "/index.html", fetchImpl: () => {} }).sandbox.ticketEnPantalla(), null);
  assert.equal(crearChat({ search: "?id=abc", fetchImpl: () => {} }).sandbox.ticketEnPantalla(), null);
});

test("en el detalle se envía el ticket abierto; en el listado no", async () => {
  const detalle = crearChat({ fetchImpl: async () => ndjson([{ t: "Hola" }, { fin: true, fuente: "ia" }]) });
  await detalle.sandbox.enviarPregunta("¿Qué hago con este ticket?");
  const cuerpo = JSON.parse(detalle.llamadas[0].options.body);
  assert.equal(cuerpo.ticket_id, 7);
  assert.equal(cuerpo.messages.at(-1).content, "¿Qué hago con este ticket?");

  const listado = crearChat({ pathname: "/index.html", search: "", fetchImpl: async () => ndjson([{ t: "Hola" }, { fin: true }]) });
  await listado.sandbox.enviarPregunta("hola");
  assert.equal("ticket_id" in JSON.parse(listado.llamadas[0].options.body), false);
});

test("mientras espera, el botón de enviar queda deshabilitado", async () => {
  let soltar;
  const chat = crearChat({ fetchImpl: () => new Promise((r) => { soltar = r; }) });
  const pendiente = chat.sandbox.enviarPregunta("hola");
  await new Promise((r) => setImmediate(r));
  assert.equal(chat.ids["chat-enviar"].disabled, true);
  assert.ok(chat.llamadas[0].options.signal, "la petición se puede cortar");
  soltar(ndjson([{ t: "listo" }, { fin: true, fuente: "ia" }]));
  await pendiente;
  assert.match(texto(chat.ids["chat-lista"]), /listo/);
});

test("si tarda demasiado se corta y muestra que la IA no está disponible", async () => {
  const chat = crearChat({
    fetchImpl: (url, options) => new Promise((_, rechazar) => {
      options.signal.addEventListener("abort", () => {
        const error = new Error("abortado");
        error.name = "AbortError";
        rechazar(error);
      });
    }),
    relojRapido: true,  // el límite real es de 200 s
  });
  await chat.sandbox.enviarPregunta("hola");
  assert.match(texto(chat.ids["chat-lista"]), /La IA no está disponible en este momento/);
});

test("un error o una respuesta vacía no se reemplaza por un texto inventado", async () => {
  const conError = crearChat({ fetchImpl: async () => ndjson([{ error: "La IA no está disponible en este momento" }]) });
  await conError.sandbox.enviarPregunta("hola");
  assert.match(texto(conError.ids["chat-lista"]), /La IA no está disponible en este momento/);

  const vacia = crearChat({ fetchImpl: async () => ndjson([{ fin: true, fuente: "ia" }]) });
  await vacia.sandbox.enviarPregunta("hola");
  const mostrado = texto(vacia.ids["chat-lista"]);
  assert.match(mostrado, /La IA no está disponible en este momento/);
  assert.doesNotMatch(mostrado, /No tengo una respuesta/);
});

test("«Generada con IA» solo cuando respondió el modelo, no en las respuestas del servidor", async () => {
  const ia = crearChat({ fetchImpl: async () => ndjson([{ t: "En este ticket, Laura reporta…" }, { fin: true, fuente: "ia" }]) });
  await ia.sandbox.enviarPregunta("explicar tickete #3");
  assert.match(texto(ia.ids["chat-lista"]), /Generada con IA/);

  const plantilla = crearChat({
    fetchImpl: async () => ndjson([{ t: "El ticket #3 «Impresora» está en estado Nuevo." }, { fin: true, fuente: "directa" }]),
  });
  await plantilla.sandbox.enviarPregunta("¿en qué estado está el #3?");
  const mostrado = texto(plantilla.ids["chat-lista"]);
  assert.match(mostrado, /Respuesta del sistema/);
  assert.doesNotMatch(mostrado, /Generada con IA/);

  const error = crearChat({ fetchImpl: async () => ndjson([{ error: "La IA no está disponible en este momento" }]) });
  await error.sandbox.enviarPregunta("explicar ticket #3");
  assert.doesNotMatch(texto(error.ids["chat-lista"]), /Generada con IA/);
});

test("«Generada con IA (datos del sistema)» cuando la IA redactó los datos del servidor", async () => {
  const chat = crearChat({
    fetchImpl: async () => ndjson([{ t: "Hay 2 tickets en proceso: el #4 y el #7." }, { fin: true, fuente: "ia_datos" }]),
  });
  await chat.sandbox.enviarPregunta("¿cuántos tickets en proceso hay?");
  const mostrado = texto(chat.ids["chat-lista"]);
  assert.match(mostrado, /Generada con IA \(datos del sistema\)/);
  assert.doesNotMatch(mostrado, /Respuesta del sistema/);
});
