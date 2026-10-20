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

/* Abrir y cerrar el panel (solo lo visual: clases y animación). */

function nodoCompleto(tag) {
  const n = nodo(tag);
  const clases = new Set();
  n.dataset = {};
  n.atributos = {};
  n.listeners = {};
  n.setAttribute = (k, v) => { n.atributos[k] = String(v); };
  n.addEventListener = (t, fn) => { (n.listeners[t] = n.listeners[t] || []).push(fn); };
  n.classList = {
    add: (c) => clases.add(c),
    remove: (c) => clases.delete(c),
    toggle: (c, si) => (si ? clases.add(c) : clases.delete(c)),
    contains: (c) => clases.has(c),
  };
  return n;
}

function montarChat({ reducirMovimiento = false, rol = "Técnico" } = {}) {
  const creados = [];
  const store = new Map([["access_token", "t"], ["user", JSON.stringify({ name: "José Solano", role: rol })]]);
  const temporizadores = [];
  const sandbox = {
    document: {
      getElementById: (id) => creados.find((n) => n.id === id) || null,
      createElement: (tag) => { const n = nodoCompleto(tag); creados.push(n); return n; },
      createTextNode: (t) => ({ textContent: t, children: [] }),
      addEventListener() {},
      body: nodoCompleto("body"),
    },
    window: {
      location: { pathname: "/index.html", search: "", href: "" },
      matchMedia: () => ({ matches: reducirMovimiento }),
    },
    localStorage: { getItem: (k) => store.get(k) ?? null, setItem: (k, v) => store.set(k, v), removeItem: (k) => store.delete(k) },
    sessionStorage: { getItem: () => null, setItem() {} },
    console: { error() {}, log() {} },
    URLSearchParams,
    setTimeout: (fn, ms) => { temporizadores.push({ fn, ms }); return temporizadores.length; },
    clearTimeout: (id) => { if (temporizadores[id - 1]) temporizadores[id - 1].fn = () => {}; },
  };
  vm.createContext(sandbox);
  vm.runInContext(authSource, sandbox);
  vm.runInContext(chatSource, sandbox);
  sandbox.crearAsistente();
  const buscar = (clase) => creados.find((n) => n.className.split(" ").includes(clase));
  return {
    store,
    lista: buscar("chat-lista"),
    panel: buscar("chat-panel"),
    contenedor: buscar("chat-asistente"),
    boton: buscar("chat-boton"),
    subtitulo: buscar("chat-subtitulo"),
    temporizadores,
  };
}

const clic = (n) => n.listeners.click.forEach((fn) => fn());

test("cabecera: «Asistente» con el estado «En línea»", () => {
  const chat = montarChat();
  assert.equal(texto(chat.subtitulo), "En línea");
  assert.match(chat.subtitulo.title, /Técnico/);
});

test("abrir muestra el panel; cerrar lo anima y después lo oculta", () => {
  const chat = montarChat();
  assert.equal(chat.panel.hidden, true);

  clic(chat.boton);
  assert.equal(chat.panel.hidden, false);
  assert.equal(chat.contenedor.classList.contains("abierto"), true);
  assert.equal(chat.boton.atributos["aria-expanded"], "true");

  clic(chat.boton);
  assert.equal(chat.panel.classList.contains("cerrando"), true, "animación de salida");
  assert.equal(chat.panel.hidden, false, "sigue visible mientras se anima");
  assert.equal(chat.boton.atributos["aria-expanded"], "false");
  chat.temporizadores.at(-1).fn();
  assert.equal(chat.panel.hidden, true);
  assert.equal(chat.panel.classList.contains("cerrando"), false);
  assert.equal(chat.contenedor.classList.contains("abierto"), false);
});

test("reabrir durante la animación de cierre deja el panel abierto", () => {
  const chat = montarChat();
  clic(chat.boton);
  clic(chat.boton);
  clic(chat.boton);
  chat.temporizadores.forEach((t) => t.fn());
  assert.equal(chat.panel.hidden, false);
  assert.equal(chat.panel.classList.contains("cerrando"), false);
});

test("con «reducir movimiento» se cierra al instante", () => {
  const chat = montarChat({ reducirMovimiento: true });
  clic(chat.boton);
  clic(chat.boton);
  assert.equal(chat.panel.hidden, true);
  assert.equal(chat.temporizadores.length, 0);
});

test("botón: solo el ícono de chispas, sin texto ni latido", () => {
  const chat = montarChat();
  assert.equal(chat.boton.className, "chat-boton");
  assert.match(chat.boton.innerHTML, /M12 3l1\.8 4\.9/, "ícono de chispas");
  assert.doesNotMatch(chat.boton.innerHTML, /M21 12a8 8 0 0 1-11\.6/, "sin el globo de chat");
  assert.doesNotMatch(chat.boton.innerHTML, /Necesitás ayuda|chat-boton-texto/);
  assert.equal(chat.boton.atributos["aria-label"], "Abrir asistente");
  clic(chat.boton);
  assert.equal(chat.boton.className, "chat-boton");
});

test("sin mensajes: saludo y 3 preguntas de ejemplo", () => {
  const chat = montarChat();
  clic(chat.boton);
  assert.match(texto(chat.lista), /¡Hola! Soy tu asistente\. Podés preguntarme cosas como:/);
  const chips = [];
  const juntar = (n) => { if (n.className === "chat-sugerencia") chips.push(n.textContent); (n.children || []).forEach(juntar); };
  juntar(chat.lista);
  assert.deepEqual(chips, ["¿Cuántos tickets pendientes hay?", "¿Qué tickets tengo asignados?", "Explicá el ticket #1"]);

  const solicitante = montarChat({ rol: "Solicitante" });
  clic(solicitante.boton);
  const otros = [];
  const juntar2 = (n) => { if (n.className === "chat-sugerencia") otros.push(n.textContent); (n.children || []).forEach(juntar2); };
  juntar2(solicitante.lista);
  assert.equal(otros.length, 3);
  assert.ok(!otros.includes("¿Qué tickets tengo asignados?"));
});
