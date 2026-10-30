/* Barra de pasos del estado en el detalle (frontend/js/detalle.js).
   Ejecutar con: node --test frontend/tests/pasos_estado.test.js */

"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const leer = (archivo) => fs.readFileSync(path.join(__dirname, "..", archivo), "utf8");

function cargar() {
  const pasos = ["Nuevo", "En proceso", "Resuelto", "Cerrado"].map((paso) => ({
    dataset: { paso }, className: "", atributos: {},
    setAttribute(k, v) { this.atributos[k] = v; },
    removeAttribute(k) { delete this.atributos[k]; },
  }));
  const lista = { querySelectorAll: (sel) => (sel === "li" ? pasos : []) };
  const sandbox = {
    console,
    document: { getElementById: (id) => (id === "pasos-estado" ? lista : null), addEventListener() {} },
    window: { location: { search: "" } },
    localStorage: { getItem: () => null, setItem() {}, removeItem() {} },
    URLSearchParams,
  };
  vm.createContext(sandbox);
  vm.runInContext(leer("js/auth.js"), sandbox);
  vm.runInContext(leer("js/detalle.js"), sandbox);
  return { sandbox, pasos };
}

test("los estados anteriores quedan hechos y el actual marcado", () => {
  const { sandbox, pasos } = cargar();
  sandbox.pintarPasos("Resuelto");
  assert.deepEqual(pasos.map((p) => p.className), ["hecho", "hecho", "actual", ""]);
  assert.equal(pasos[2].atributos["aria-current"], "step");
  assert.equal(pasos[0].atributos["aria-current"], undefined);

  sandbox.pintarPasos("Nuevo");
  assert.deepEqual(pasos.map((p) => p.className), ["actual", "", "", ""]);
  assert.equal(pasos[2].atributos["aria-current"], undefined, "se quita al cambiar de estado");

  sandbox.pintarPasos("Cerrado");
  assert.deepEqual(pasos.map((p) => p.className), ["hecho", "hecho", "hecho", "actual"]);
});

test("detalle.html tiene los cuatro pasos en orden", () => {
  const html = leer("detalle.html");
  const pasos = [...html.matchAll(/<li data-paso="([^"]+)">/g)].map((m) => m[1]);
  assert.deepEqual(pasos, ["Nuevo", "En proceso", "Resuelto", "Cerrado"]);
});

/* Pasos que se pueden tocar: DOM mínimo con createElement y replaceChildren. */
function nodo(tag) {
  return {
    tag, className: "", type: "", title: "", textContent: "", dataset: {}, atributos: {}, children: [],
    setAttribute(k, v) { this.atributos[k] = String(v); },
    removeAttribute(k) { delete this.atributos[k]; },
    append(...hs) { this.children.push(...hs); },
    replaceChildren(...hs) { this.children = hs; },
  };
}

function cargarConDom(usuario) {
  const pasos = ["Nuevo", "En proceso", "Resuelto", "Cerrado"].map((paso) => {
    const li = nodo("li");
    li.dataset.paso = paso;
    return li;
  });
  const lista = { querySelectorAll: (sel) => (sel === "li" ? pasos : []) };
  const guardado = new Map(usuario ? [["user", JSON.stringify(usuario)]] : []);
  const sandbox = {
    console,
    document: {
      getElementById: (id) => (id === "pasos-estado" ? lista : null),
      createElement: nodo,
      addEventListener() {},
    },
    window: { location: { search: "" } },
    localStorage: { getItem: (k) => (guardado.has(k) ? guardado.get(k) : null), setItem() {}, removeItem() {} },
    URLSearchParams,
  };
  vm.createContext(sandbox);
  vm.runInContext(leer("js/auth.js"), sandbox);
  vm.runInContext(leer("js/detalle.js"), sandbox);
  const pintar = (ticket) => {
    vm.runInContext(`ticketActual = ${JSON.stringify(ticket)};`, sandbox);
    sandbox.pintarPasos(ticket.state);
  };
  const botones = () => pasos.map((li) => (li.children[0].tag === "button" ? li.children[0] : null));
  return { pintar, botones, pasos };
}

const tecnico = { id: 7, name: "Carlos", role: "Técnico" };
const solicitante = { id: 9, name: "Pedro", role: "Solicitante" };

test("con permiso, los destinos permitidos son botones accesibles", () => {
  const { pintar, botones } = cargarConDom(tecnico);
  pintar({ id: 4, state: "Nuevo", assigned_to_id: null });
  const [nuevo, enProceso, resuelto, cerrado] = botones();
  assert.equal(nuevo, null, "el estado actual no se toca");
  for (const [boton, nombre] of [[enProceso, "En proceso"], [resuelto, "Resuelto"], [cerrado, "Cerrado"]]) {
    assert.equal(boton.type, "button");
    assert.equal(boton.className, "paso-boton");
    assert.equal(boton.dataset.destino, nombre);
    assert.equal(boton.atributos["aria-label"], `Pasar el ticket a «${nombre}»`);
    assert.deepEqual(boton.children.map((h) => h.className), ["paso-marca", "paso-nombre"]);
    assert.equal(boton.children[0].atributos["aria-hidden"], "true");
  }
});

test("en un ticket Cerrado ningún paso es botón; desde Resuelto se reabre a «En proceso»", () => {
  const { pintar, botones, pasos } = cargarConDom(tecnico);
  pintar({ id: 4, state: "Cerrado", assigned_to_id: null });
  assert.deepEqual(botones(), [null, null, null, null]);
  assert.deepEqual(pasos.map((li) => li.className), ["hecho", "hecho", "hecho", "actual"]);

  pintar({ id: 4, state: "Resuelto", assigned_to_id: null });
  assert.deepEqual(botones().map((b) => (b ? b.dataset.destino : null)), [null, "En proceso", null, "Cerrado"]);
});

test("sin permiso los pasos se ven igual pero ninguno es botón", () => {
  const { pintar, botones, pasos } = cargarConDom(solicitante);
  pintar({ id: 4, state: "En proceso", assigned_to_id: 1 });
  assert.deepEqual(botones(), [null, null, null, null]);
  assert.deepEqual(pasos.map((li) => li.children.map((h) => h.className)),
    Array(4).fill(["paso-marca", "paso-nombre"]));
  assert.deepEqual(pasos.map((li) => li.className), ["hecho", "actual", "", ""]);

  /* El Solicitante asignado sí puede. */
  pintar({ id: 4, state: "En proceso", assigned_to_id: 9 });
  assert.deepEqual(botones().map((b) => (b ? b.dataset.destino : null)), [null, null, "Resuelto", "Cerrado"]);
});

test("detalle.html deja enfocar el recorrido y explica que se puede tocar", () => {
  const html = leer("detalle.html");
  assert.match(html, /id="pasos-estado"[^>]*tabindex="-1"/);
  assert.match(html, /También puede tocar un estado en el recorrido/);
  assert.match(html, /Este ticket está <b>Cerrado<\/b>: es un estado final y no admite más\s+cambios de estado\./);
  const css = leer("css/estilos.css");
  assert.match(css, /\.pasos-estado \.paso-boton/);
});
