/* Avisos flotantes (js/avisos.js, avisar(texto, tipo)): arriba a la
   derecha, éxito verde que se va a los 4 segundos, error rojo que queda
   hasta cerrarlo con la ✕; se apilan, se anuncian (aria-live) y pueden
   quedar pendientes para la página siguiente.
   Ejecutar con: node --test frontend/tests/avisos_ui.test.js */

"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const leer = (archivo) => fs.readFileSync(path.join(__dirname, "..", archivo), "utf8");
const avisosSource = leer("js/avisos.js");

function nodo(tag) {
  const n = {
    tag, id: "", className: "", textContent: "", type: "", children: [], atributos: {}, parentNode: null,
    listeners: {}, style: { props: {}, setProperty(k, v) { this.props[k] = v; } },
    classList: { add(c) { n.className += ` ${c}`; } },
    setAttribute(k, v) { n.atributos[k] = v; },
    appendChild(h) {
      if (h.parentNode) h.parentNode.children = h.parentNode.children.filter((x) => x !== h);
      h.parentNode = n;
      n.children.push(h);
      return h;
    },
    remove() {
      if (n.parentNode) n.parentNode.children = n.parentNode.children.filter((x) => x !== n);
      n.parentNode = null;
    },
    addEventListener(tipo, fn) { (n.listeners[tipo] = n.listeners[tipo] || []).push(fn); },
    disparar(tipo, evento = {}) { (n.listeners[tipo] || []).forEach((fn) => fn(evento)); },
  };
  return n;
}

function buscar(raiz, id) {
  if (raiz.id === id) return raiz;
  for (const h of raiz.children) {
    const r = buscar(h, id);
    if (r) return r;
  }
  return null;
}

function cargar({ cabeceraAbajo = 80 } = {}) {
  const almacen = new Map();
  let reloj = 0;
  const timers = new Map();
  const body = nodo("body");
  const cabecera = nodo("header");
  cabecera.getBoundingClientRect = () => ({ bottom: cabeceraAbajo });
  let modal = null;
  const doc = {
    body,
    createElement: nodo,
    getElementById: (id) => buscar(body, id) || (modal && buscar(modal, id)) || null,
    querySelector: (sel) => (sel === "dialog[open]" ? modal : sel === ".cabecera" ? cabecera : null),
    addEventListener() {},
  };
  const sandbox = {
    console, Array, Math, JSON,
    document: doc,
    sessionStorage: {
      getItem: (k) => (almacen.has(k) ? almacen.get(k) : null),
      setItem: (k, v) => almacen.set(k, String(v)),
      removeItem: (k) => almacen.delete(k),
    },
    setTimeout: (fn, ms) => { reloj += 1; timers.set(reloj, { fn, ms }); return reloj; },
    clearTimeout: (id) => timers.delete(id),
  };
  vm.runInNewContext(avisosSource, sandbox, { filename: "avisos.js" });
  const correr = (ms) => {
    for (const [id, t] of [...timers]) {
      if (t.ms === ms) { timers.delete(id); t.fn(); }
    }
  };
  return {
    s: sandbox, doc, body, timers, almacen, correr,
    zona: () => doc.getElementById("avisos"),
    abrirModal() { modal = nodo("dialog"); return modal; },
    cerrarModal() { const m = modal; modal = null; m.disparar("close"); },
  };
}

const cerrarDe = (aviso) => aviso.children.find((h) => h.className === "aviso-cerrar");
const textoDe = (aviso) => aviso.children.find((h) => h.className === "aviso-texto").textContent;

test("éxito: aviso verde con el texto y la ✕, que se va solo a los 4 segundos", () => {
  const p = cargar();
  const aviso = p.s.avisar("Comentario agregado correctamente.");
  const zona = p.zona();
  assert.equal(zona.parentNode, p.body);
  assert.equal(zona.className, "avisos");
  assert.equal(zona.atributos["aria-live"], "polite", "el lector de pantalla lo anuncia");
  assert.equal(aviso.className, "aviso exito");
  assert.equal(aviso.atributos.role, undefined);
  assert.equal(textoDe(aviso), "Comentario agregado correctamente.");
  const cerrar = cerrarDe(aviso);
  assert.equal(cerrar.tag, "button", "la ✕ es un botón: se llega con Tab y se usa con Enter");
  assert.equal(cerrar.type, "button");
  assert.equal(cerrar.atributos["aria-label"], "Cerrar aviso");
  assert.equal(cerrar.textContent, "✕");

  assert.deepEqual([...p.timers.values()].map((t) => t.ms), [4000]);
  p.correr(4000);
  assert.match(aviso.className, /saliendo/, "sale con una transición corta");
  assert.equal(aviso.parentNode, zona);
  p.correr(200);
  assert.equal(aviso.parentNode, null);
});

test("error: aviso rojo con role=alert que no se va solo; se cierra con la ✕ o con Escape", () => {
  const p = cargar();
  const aviso = p.s.avisar("Error al comunicarse con la API.", "error");
  assert.equal(aviso.className, "aviso error");
  assert.equal(aviso.atributos.role, "alert");
  assert.equal(p.timers.size, 0, "queda hasta que se cierre");
  cerrarDe(aviso).disparar("click");
  p.correr(200);
  assert.equal(aviso.parentNode, null);

  const otro = p.s.avisar("No se pudo eliminar el adjunto.", "error");
  let detenido = 0;
  otro.disparar("keydown", { key: "Escape", preventDefault() { detenido += 1; }, stopPropagation() { detenido += 1; } });
  assert.match(otro.className, /saliendo/);
  assert.equal(detenido, 2, "Escape no cierra además la ventana de abajo");
});

test("se apilan en una sola zona; el mismo aviso repetido no se duplica", () => {
  const p = cargar();
  p.s.avisar("Estado actualizado a «En proceso».");
  p.s.avisar("No se pudo asignar.", "error");
  assert.equal(p.body.children.length, 1, "una sola zona para todos los avisos");
  assert.deepEqual(p.zona().children.map((a) => a.className), ["aviso exito", "aviso error"]);
  const primero = p.zona().children[1];
  p.s.avisar("No se pudo asignar.", "error");
  assert.match(primero.className, /saliendo/, "el anterior igual se va");
  p.correr(200);
  assert.equal(p.zona().children.length, 2);
});

test("con el mouse o el foco encima el aviso de éxito no se va", () => {
  const p = cargar();
  const aviso = p.s.avisar("Cambios guardados correctamente.");
  aviso.disparar("mouseenter");
  assert.equal(p.timers.size, 0);
  aviso.disparar("mouseleave");
  assert.deepEqual([...p.timers.values()].map((t) => t.ms), [4000]);
  aviso.disparar("focusin");
  assert.equal(p.timers.size, 0);
});

test("queda justo debajo de la barra del título", () => {
  const p = cargar({ cabeceraAbajo: 96 });
  p.s.avisar("Usuario agregado correctamente.");
  assert.equal(p.zona().style.props["--avisos-arriba"], "108px");
  const bajado = cargar({ cabeceraAbajo: -300 });
  bajado.s.avisar("Usuario agregado correctamente.");
  assert.equal(bajado.zona().style.props["--avisos-arriba"], "12px", "si ya se bajó, arriba con un margen");
});

test("con una ventana modal abierta el aviso va adentro y al cerrarla vuelve a la página", () => {
  const p = cargar();
  const modal = p.abrirModal();
  p.s.avisar("El email ya está registrado", "error");
  assert.equal(p.zona().parentNode, modal, "se ve y se puede cerrar encima del fondo oscuro");
  p.cerrarModal();
  assert.equal(p.zona().parentNode, p.body);
});

test("un aviso pendiente se muestra una sola vez en la página siguiente", () => {
  const p = cargar();
  p.s.avisoPendiente("Ticket #4 eliminado correctamente.");
  assert.ok(p.almacen.has("aviso_pendiente"));
  p.s.mostrarAvisoPendiente();
  assert.equal(textoDe(p.zona().children[0]), "Ticket #4 eliminado correctamente.");
  assert.equal(p.almacen.has("aviso_pendiente"), false);
  p.s.mostrarAvisoPendiente();
  assert.equal(p.zona().children.length, 1);
});

test("los avisos reemplazan los mensajes de éxito de las acciones", () => {
  const detalle = leer("js/detalle.js");
  for (const texto of ["Cambios guardados correctamente.", "Comentario agregado correctamente.", "Estado actualizado a"]) {
    assert.match(detalle, new RegExp(`avisar\\(\\s*\`?"?${texto}`), texto);
  }
  assert.match(detalle, /avisoPendiente\(`Ticket #\$\{ticketId\} eliminado correctamente.`\)/);
  const crear = leer("js/crear.js");
  assert.match(crear, /avisoPendiente\(`Ticket #\$\{ticket\.id\} guardado correctamente\$\{conAdjuntos\}\.`\)/);
  assert.doesNotMatch(detalle + crear, /\balert\(/);
});

test("una sola función: avisar() en js/avisos.js, cargado en todas las páginas antes que el resto", () => {
  const archivos = fs.readdirSync(path.join(__dirname, "..")).filter((f) => f.endsWith(".html"));
  assert.ok(archivos.length >= 12);
  for (const archivo of archivos) {
    const html = leer(archivo);
    const avisos = html.indexOf('<script src="js/avisos.js?v=');
    assert.ok(avisos > 0, `${archivo} carga avisos.js`);
    const auth = html.indexOf('<script src="js/auth.js?v=');
    if (auth > 0) assert.ok(avisos < auth, `${archivo}: avisos.js antes que auth.js`);
  }
  const js = ["auth", "detalle", "crear", "usuarios", "adjuntos", "explicacion", "app", "departamentos", "asistente"]
    .map((n) => leer(`js/${n}.js`)).join("\n");
  assert.doesNotMatch(js, /function (avisar|mostrarAviso|avisoPendiente|adjAvisar|avisarPagina)\(/, "sin copias propias");
  assert.doesNotMatch(js, /mostrarAviso\(/);
});

test("ningún mensaje de éxito queda fijo en la página", () => {
  for (const archivo of ["detalle", "crear", "usuarios", "adjuntos", "explicacion"]) {
    const js = leer(`js/${archivo}.js`);
    assert.doesNotMatch(js, /(showStatus|adjMostrarEstado|iaEstado|mostrarEdicionEstado)\([^;]*"exito"\)/s, archivo);
  }
});

test("CSS: arriba a la derecha, colores de la app (claro y oscuro), ✕ visible con teclado y a todo el ancho en el celular", () => {
  const css = leer("css/estilos.css");
  const inicio = css.indexOf("/* ===== Avisos flotantes (js/avisos.js)");
  const bloque = css.slice(inicio, css.indexOf("/* ===== Esqueletos de carga", inicio));
  assert.ok(inicio > 0);
  const zona = bloque.slice(bloque.indexOf(".avisos {"), bloque.indexOf("}", bloque.indexOf(".avisos {")));
  assert.match(zona, /position: fixed;/);
  assert.match(zona, /top: var\(--avisos-arriba, 5\.5rem\);/);
  assert.match(zona, /right: 1\.5rem;/);
  assert.doesNotMatch(zona, /bottom:|left:/, "lejos del botón del chat (abajo a la derecha)");
  assert.match(bloque, /\.aviso \{[^}]*background: var\(--color-exito-fondo\);[^}]*color: var\(--color-exito\);/);
  assert.match(bloque, /\.aviso\.error \{[^}]*background: var\(--color-error-fondo\);[^}]*color: var\(--color-error\);/);
  assert.match(bloque, /\.aviso-cerrar:focus-visible \{\s*outline: 2px solid currentColor;/);
  assert.match(bloque, /@keyframes aviso-entrada/);
  assert.match(bloque, /0\.18s/, "entrada corta");
  assert.match(bloque, /@media \(prefers-reduced-motion: reduce\) \{\s*\.aviso \{\s*animation: none;\s*transition: none;/);
  assert.match(bloque, /@media \(max-width: 600px\) \{\s*\.avisos \{\s*right: 0\.75rem;\s*left: 0\.75rem;\s*width: auto;/);
  assert.match(bloque, /\.aviso-texto \{[^}]*overflow-wrap: anywhere;/, "sin scroll horizontal en el celular");
  // La sombra flotante existe en el tema claro y en el oscuro.
  assert.equal((css.match(/--sombra-aviso:/g) || []).length, 2);
});
