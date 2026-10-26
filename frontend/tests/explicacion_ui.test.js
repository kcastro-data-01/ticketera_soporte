/* Pruebas de «Explicar con IA» (frontend/js/explicacion.js).
   Ejecutar con: node --test frontend/tests/explicacion_ui.test.js */

"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const authSource = fs.readFileSync(path.join(__dirname, "..", "js", "auth.js"), "utf8");
const iaSource = fs.readFileSync(path.join(__dirname, "..", "js", "explicacion.js"), "utf8");

function nodo(tag) {
  return {
    tag, id: "", type: "", className: "", textContent: "", value: "", hidden: false,
    disabled: false, focused: false, children: [], listeners: {},
    appendChild(h) { this.children.push(h); return h; },
    replaceChildren(...h) { this.children = h; },
    addEventListener(t, fn) { (this.listeners[t] = this.listeners[t] || []).push(fn); },
    focus() { this.focused = true; },
  };
}

function texto(n) {
  return (n.textContent || "") + (n.children || []).map(texto).join("");
}

function buscar(n, pred) {
  if (pred(n)) return n;
  for (const h of n.children || []) {
    const r = buscar(h, pred);
    if (r) return r;
  }
  return null;
}

const DATOS = {
  ticket_id: 7,
  claridad: "poco detalle",
  motivo_claridad: "La descripción tiene 2 palabras.",
  explicacion: {
    explicacion: "Laura Méndez reporta que una impresora no funciona. Lo más común es que no tenga corriente.",
    posibles_causas: ["La impresora está apagada", "Falta papel o tóner"],
    que_revisar_primero: ["Revisar que esté encendida", "Revisar papel y tóner", "Imprimir una página de prueba"],
    certeza: "baja",
    categoria_sugerida: { valor: "Hardware", razon: "Parece un equipo." },
    prioridad_sugerida: null,
  },
  vigente: true,
  generada_en: "2026-10-19T16:00:00Z",
  modelo: "qwen3:0.6b",
  desde_cache: false,
};

function respuesta(status, body) {
  return { ok: status >= 200 && status < 300, status, json: async () => body };
}

function crear({ rol = "Técnico", fetchImpl }) {
  const ids = {};
  for (const id of ["seccion-ia", "ia-explicar", "ia-regenerar", "ia-estado", "ia-panel", "contenido"]) {
    ids[id] = nodo(id === "contenido" ? "textarea" : "div");
  }
  // Como en detalle.html: el panel, el estado y «Volver a explicar» empiezan ocultos.
  ids["ia-regenerar"].hidden = true;
  ids["ia-panel"].hidden = true;
  ids["ia-estado"].hidden = true;
  const store = new Map([["access_token", "t"], ["user", JSON.stringify({ name: "José", role: rol })]]);
  const llamadas = [];
  const sandbox = {
    document: {
      getElementById: (id) => ids[id] || null,
      createElement: nodo,
      createTextNode: (t) => ({ textContent: t, children: [] }),
      addEventListener() {},
    },
    window: { location: { search: "?id=7", href: "" } },
    localStorage: { getItem: (k) => store.get(k) ?? null, setItem: (k, v) => store.set(k, v), removeItem: (k) => store.delete(k) },
    fetch: (url, options = {}) => { llamadas.push({ url, method: options.method || "GET" }); return fetchImpl(url, options); },
    console: { error() {} },
    URLSearchParams, AbortController, setTimeout, clearTimeout, Date, Number,
  };
  vm.createContext(sandbox);
  vm.runInContext(authSource, sandbox);
  vm.runInContext(iaSource, sandbox);
  return { sandbox, ids, llamadas };
}

const click = (n) => n.listeners.click[0]();

test("al abrir el ticket muestra la explicación guardada sin generar una nueva", async () => {
  const ia = crear({ fetchImpl: async () => respuesta(200, DATOS) });
  await ia.sandbox.iniciarExplicacion();
  assert.deepEqual(ia.llamadas, [{ url: "/api/tickets/7/explicacion", method: "GET" }]);
  const panel = texto(ia.ids["ia-panel"]);
  assert.equal(ia.ids["ia-panel"].hidden, false);
  assert.match(panel, /Contenido generado automáticamente\. Revíselo antes de utilizarlo\./);
  assert.match(panel, /poco detalle/);
  assert.match(panel, /Laura Méndez reporta que una impresora no funciona/);
  assert.match(panel, /Categoría sugerida: Hardware — Parece un equipo/);
  assert.doesNotMatch(panel, /Prioridad sugerida/);
  assert.equal(ia.ids["ia-regenerar"].hidden, false);
  assert.equal(ia.ids["ia-explicar"].hidden, true, "un solo botón: Volver a explicar");
});

test("sin explicación guardada el panel queda oculto", async () => {
  const ia = crear({ fetchImpl: async () => respuesta(200, { ...DATOS, explicacion: null }) });
  await ia.sandbox.iniciarExplicacion();
  assert.equal(ia.ids["ia-panel"].hidden, true);
  assert.equal(ia.ids["ia-regenerar"].hidden, true);
  assert.equal(ia.ids["ia-explicar"].hidden, false, "un solo botón: Explicar con IA");
});

test("si el ticket cambió avisa que la explicación está desactualizada", async () => {
  const ia = crear({ fetchImpl: async () => respuesta(200, { ...DATOS, vigente: false }) });
  await ia.sandbox.iniciarExplicacion();
  assert.match(texto(ia.ids["ia-panel"]), /El ticket cambió desde la última explicación/);
});

test("Explicar con IA: indicador de carga, botones bloqueados y resultado", async () => {
  let soltar;
  const ia = crear({
    fetchImpl: (url, o) => (o.method === "POST" ? new Promise((r) => { soltar = r; }) : respuesta(200, { ...DATOS, explicacion: null })),
  });
  await ia.sandbox.iniciarExplicacion();
  const pendiente = click(ia.ids["ia-explicar"]);
  assert.equal(ia.ids["ia-explicar"].disabled, true);
  assert.equal(ia.ids["ia-regenerar"].disabled, true);
  assert.match(ia.ids["ia-estado"].textContent, /Analizando el ticket/);
  assert.match(ia.ids["ia-estado"].className, /ia-cargando/);
  soltar(respuesta(200, DATOS));
  await pendiente;
  assert.equal(ia.ids["ia-explicar"].disabled, false);
  assert.equal(ia.ids["ia-estado"].hidden, true);
  assert.equal(ia.llamadas.at(-1).url, "/api/tickets/7/explicacion");
  assert.equal(ia.llamadas.at(-1).method, "POST");
});

test("Volver a explicar pide una nueva con regenerar=true", async () => {
  const ia = crear({ fetchImpl: async () => respuesta(200, DATOS) });
  await ia.sandbox.iniciarExplicacion();
  await click(ia.ids["ia-regenerar"]);
  assert.deepEqual(ia.llamadas.at(-1), { url: "/api/tickets/7/explicacion?regenerar=true", method: "POST" });
});

test("errores: IA caída, JSON inválido y rol sin permiso", async () => {
  for (const [status, detail, esperado] of [
    [502, "La IA no está disponible en este momento", /La IA no está disponible/],
    [502, "La IA no pudo generar una explicación válida. Intente de nuevo.", /explicación válida/],
    [403, "No autorizado", /Su rol no tiene permiso para usar/],
  ]) {
    const ia = crear({
      fetchImpl: async (url, o) => (o.method === "POST" ? respuesta(status, { detail }) : respuesta(200, { ...DATOS, explicacion: null })),
    });
    await ia.sandbox.iniciarExplicacion();
    await click(ia.ids["ia-explicar"]);
    assert.match(ia.ids["ia-estado"].textContent, esperado);
    assert.equal(ia.ids["ia-estado"].className, "estado error");
    assert.equal(ia.ids["ia-explicar"].disabled, false);
  }
});

test("el Solicitante no activa la sección ni llama a la API", async () => {
  const ia = crear({ rol: "Solicitante", fetchImpl: async () => respuesta(200, DATOS) });
  await ia.sandbox.iniciarExplicacion();
  assert.deepEqual(ia.llamadas, []);
});

test("lo que llega de la IA se pinta como texto, no como HTML", async () => {
  const malicioso = { ...DATOS, explicacion: { ...DATOS.explicacion, explicacion: "<img src=x onerror=alert(1)>" } };
  const ia = crear({ fetchImpl: async () => respuesta(200, malicioso) });
  await ia.sandbox.iniciarExplicacion();
  const parrafo = buscar(ia.ids["ia-panel"], (n) => n.textContent === "<img src=x onerror=alert(1)>");
  assert.ok(parrafo && !("innerHTML" in parrafo && parrafo.innerHTML));
});

test("muestra la explicación, la certeza, las causas y qué revisar primero numerado", async () => {
  const ia = crear({ fetchImpl: async () => respuesta(200, DATOS) });
  await ia.sandbox.iniciarExplicacion();
  const hijos = ia.ids["ia-panel"].children;
  const primera = hijos.findIndex((n) => n.className === "ia-explicacion");
  assert.equal(hijos[primera].textContent, DATOS.explicacion.explicacion);
  // Antes solo puede ir el aviso de que la generó la IA.
  assert.deepEqual(hijos.slice(0, primera).map((n) => n.className), ["ia-aviso"]);
  // La certeza, como etiqueta chica justo debajo.
  const etiqueta = buscar(hijos[primera + 1], (n) => /ia-certeza/.test(n.className));
  assert.equal(etiqueta.className, "ia-certeza baja");
  assert.equal(etiqueta.textContent, "baja");

  const titulos = hijos.filter((n) => n.tag === "h3").map((n) => n.textContent);
  assert.deepEqual(titulos.slice(0, 2), ["Posibles causas", "Qué revisar primero"]);
  const causas = hijos[hijos.findIndex((n) => n.textContent === "Posibles causas") + 1];
  assert.equal(causas.tag, "ul");
  assert.deepEqual(causas.children.map((n) => n.textContent), DATOS.explicacion.posibles_causas);
  const pasos = hijos[hijos.findIndex((n) => n.textContent === "Qué revisar primero") + 1];
  assert.equal(pasos.tag, "ol", "los pasos van numerados");
  assert.deepEqual(pasos.children.map((n) => n.textContent), DATOS.explicacion.que_revisar_primero);
});

test("no hay sección de preguntas ni botón para copiarlas", async () => {
  const ia = crear({ fetchImpl: async () => respuesta(200, DATOS) });
  await ia.sandbox.iniciarExplicacion();
  assert.equal(buscar(ia.ids["ia-panel"], (n) => n.id === "ia-copiar"), null);
  assert.doesNotMatch(texto(ia.ids["ia-panel"]), /Pregunta|Usar preguntas|Siguiente paso|Qué pide/);
  assert.equal(typeof ia.sandbox.iaUsarPreguntas, "undefined");
});
