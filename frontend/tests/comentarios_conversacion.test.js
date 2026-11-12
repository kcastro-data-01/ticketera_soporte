/* Comentarios del detalle como conversación (detalle.js, renderComentarios):
   todos a la izquierda y a todo el ancho, con una línea azul (IT) o gris a
   la izquierda; cabecera con iniciales, nombre, «IT», «por correo» y la
   hora; seguidos agrupados (< 10 minutos); el motivo de un cambio de
   estado como aviso del sistema centrado.
   Ejecutar con: node --test frontend/tests/comentarios_conversacion.test.js */

"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const leer = (archivo) => fs.readFileSync(path.join(__dirname, "..", archivo), "utf8");
const css = leer("css/estilos.css");
const html = leer("detalle.html");

function nodo(tag) {
  return {
    tag, className: "", textContent: "", title: "", hidden: false, dataset: {}, children: [],
    scrollTop: 0, scrollHeight: 900,
    appendChild(h) { this.children.push(h); return h; },
    replaceChildren(...h) { this.children = h; },
  };
}

const KARLA = { id: 1, name: "Karla Sánchez", role: "Administrador" };

function render(comentarios, usuario = KARLA) {
  const lista = nodo("div");
  const estado = nodo("p");
  const ids = { "lista-comentarios": lista, "comentarios-estado": estado };
  const sandbox = {
    console, Intl, Date, Number, URLSearchParams,
    document: { getElementById: (id) => ids[id] || null, createElement: nodo, addEventListener() {} },
    window: { location: { search: "" } },
    localStorage: { getItem: (k) => (k === "user" && usuario ? JSON.stringify(usuario) : null), setItem() {}, removeItem() {} },
  };
  vm.createContext(sandbox);
  vm.runInContext(leer("js/auth.js"), sandbox);
  vm.runInContext(leer("js/detalle.js"), sandbox);
  sandbox.renderComentarios(comentarios);
  return { lista, estado };
}

const hijo = (n, clase) => n.children.find((h) => String(h.className).split(" ").includes(clase));
const cabecera = (burbuja) => hijo(burbuja, "comentario-cabecera");
const clases = (n) => String(n.className).split(" ");

function comentario(extra) {
  return {
    id: 1, ticket_id: 25, author: "Karla Sánchez", author_id: 1, author_es_it: true,
    content: "Hola", created_at: "2026-11-11T17:15:00Z", origen: "app", estado_nuevo: null, ...extra,
  };
}

test("todos iguales, sin lado propio o ajeno: de IT o de los demás", () => {
  const { lista } = render([
    comentario({ id: 1 }),
    comentario({ id: 2, author: "Ana Mora", author_id: 7, author_es_it: false, created_at: "2026-11-11T17:20:00Z" }),
  ]);
  assert.deepEqual(lista.children.map((c) => c.className), ["comentario de-it", "comentario de-otro"]);
  assert.equal(lista.children[0].tag, "article");
  // Lo mismo sin importar quién está viendo el ticket.
  const { lista: comoAna } = render([comentario({ id: 1 })], { id: 7, name: "Ana Mora", role: "Solicitante" });
  assert.equal(comoAna.children[0].className, "comentario de-it");
  assert.doesNotMatch(leer("js/detalle.js"), /propio|ajeno|esComentarioPropio/);
});

test("cabecera: iniciales y nombre, «IT», «por correo» y la hora en 12 horas; abajo el texto", () => {
  const { lista } = render([
    comentario({ author: "Ana Mora", author_id: 7, author_es_it: false, origen: "correo" }),
    comentario({ id: 2, created_at: "2026-11-11T18:00:00Z" }),
  ]);
  const [ana, karla] = lista.children.map(cabecera);
  const autorAna = hijo(ana, "comentario-autor");
  assert.equal(autorAna.textContent, "Ana Mora");
  assert.ok(clases(autorAna).includes("con-avatar"));
  assert.equal(autorAna.dataset.iniciales, "AM");
  assert.equal(hijo(ana, "comentario-it"), undefined, "el Solicitante no lleva «IT»");
  assert.match(hijo(ana, "comentario-fecha").textContent, /^11\/11\/2026, 11:15\s?a\.\s?m\.$/);
  assert.equal(hijo(ana, "comentario-correo").textContent, "por correo");
  assert.equal(hijo(karla, "comentario-it").textContent, "IT");
  assert.equal(hijo(karla, "comentario-correo"), undefined);
  assert.deepEqual(ana.children.map((h) => clases(h)[0]), ["comentario-autor", "comentario-correo", "comentario-fecha"]);
  assert.deepEqual(karla.children.map((h) => clases(h)[0]), ["comentario-autor", "comentario-it", "comentario-fecha"]);
  assert.deepEqual(lista.children[0].children.map((h) => h.className), ["comentario-cabecera", "comentario-contenido"]);
  assert.equal(hijo(lista.children[0], "comentario-contenido").textContent, "Hola");
});

test("seguidos de la misma persona en menos de 10 minutos: sin repetir nombre ni iniciales", () => {
  const { lista } = render([
    comentario({ id: 1, created_at: "2026-11-11T17:15:00Z" }),
    comentario({ id: 2, created_at: "2026-11-11T17:24:59Z" }),
    comentario({ id: 3, created_at: "2026-11-11T17:35:00Z" }), // 10 min o más: no se agrupa
    comentario({ id: 4, author: "Ana Mora", author_id: 7, author_es_it: false, created_at: "2026-11-11T17:36:00Z" }),
    comentario({ id: 5, created_at: "2026-11-11T17:37:00Z" }), // otra persona en medio
  ]);
  assert.deepEqual(lista.children.map((c) => clases(c).includes("seguido")), [false, true, false, false, false]);
  const seguido = cabecera(lista.children[1]);
  const autor = hijo(seguido, "comentario-autor");
  assert.ok(clases(autor).includes("solo-lector"), "el nombre queda para el lector de pantalla y la impresión");
  assert.ok(!clases(autor).includes("con-avatar"), "sin iniciales");
  assert.equal(hijo(seguido, "comentario-it"), undefined);
  assert.ok(hijo(seguido, "comentario-fecha"), "la hora sí");
});

test("el motivo de un cambio de estado es un aviso del sistema, no una burbuja", () => {
  const { lista } = render([
    comentario({ id: 1 }),
    comentario({ id: 2, origen: "estado", estado_nuevo: "Resuelto", content: "se cambió el tóner", created_at: "2026-11-11T17:16:00Z" }),
    comentario({ id: 3, created_at: "2026-11-11T17:17:00Z" }),
  ]);
  const sistema = lista.children[1];
  assert.equal(sistema.tag, "p");
  assert.equal(sistema.className, "comentario-sistema");
  assert.equal(hijo(sistema, "comentario-sistema-texto").textContent, "Pasó a Resuelto · se cambió el tóner");
  assert.match(hijo(sistema, "comentario-sistema-meta").textContent, /^Karla Sánchez · 11\/11\/2026, 11:16\s?a\.\s?m\.$/);
  assert.ok(!clases(lista.children[2]).includes("seguido"), "el aviso corta el grupo");
});

test("del más antiguo al más reciente, y al abrir se ve el último", () => {
  const { lista, estado } = render([
    comentario({ id: 1, content: "Primero" }),
    comentario({ id: 2, content: "Segundo", author_id: 7, author: "Ana", created_at: "2026-11-11T19:00:00Z" }),
  ]);
  assert.deepEqual(lista.children.map((c) => hijo(c, "comentario-contenido").textContent), ["Primero", "Segundo"]);
  assert.equal(lista.scrollTop, 900, "la lista baja hasta el último");
  assert.equal(lista.hidden, false);
  assert.equal(estado.hidden, true);
});

test("sin comentarios sigue la línea «Todavía no hay comentarios.»", () => {
  const { lista, estado } = render([]);
  assert.equal(lista.hidden, true);
  assert.equal(estado.textContent, "Todavía no hay comentarios.");
});

test("detalle.html: la conversación arriba y «Nuevo comentario» abajo, sin código inline", () => {
  const seccion = html.slice(html.indexOf('<section id="seccion-comentarios"'), html.indexOf("</section>", html.indexOf('<section id="seccion-comentarios"')));
  assert.ok(seccion.indexOf('id="lista-comentarios"') < seccion.indexOf('id="form-comentario"'));
  assert.match(seccion, /<div id="lista-comentarios" class="comentarios" aria-label="Conversación del ticket" tabindex="0" hidden><\/div>/);
  assert.doesNotMatch(html, /\sstyle="|\son[a-z]+="/);
});

function bloqueCss() {
  const inicio = css.indexOf("/* Comentarios como conversación");
  return css.slice(inicio, css.indexOf("/* Línea y puntos de la línea de tiempo del historial", inicio));
}

function regla(bloque, selector) {
  const i = bloque.indexOf(`${selector} {`);
  assert.ok(i >= 0, selector);
  return bloque.slice(i, bloque.indexOf("}", i));
}

test("CSS: a todo el ancho, fondo de tarjeta, borde suave y la línea azul (IT) o gris a la izquierda", () => {
  const bloque = bloqueCss();
  assert.ok(bloque.length > 100);
  const tarjeta = regla(bloque, ".comentario");
  assert.match(tarjeta, /border: 1px solid var\(--color-borde\);/);
  assert.match(tarjeta, /border-left: 3px solid var\(--color-borde-fuerte\);/);
  assert.match(tarjeta, /background: var\(--color-superficie-alta\);/);
  assert.doesNotMatch(tarjeta, /max-width|align-self/, "sin burbujas a los costados");
  assert.match(regla(bloque, ".comentario.de-it"), /border-left-color: var\(--color-primario\);/);
  assert.doesNotMatch(bloque, /\.propio|\.ajeno|box-shadow|max-width: 75%/);
  assert.match(regla(bloque, ".comentarios"), /flex-direction: column;/);
  assert.match(regla(bloque, ".comentarios"), /overflow-x: hidden;/, "sin scroll horizontal");
  assert.match(regla(bloque, ".comentario-contenido"), /overflow-wrap: anywhere;/);
  assert.match(regla(bloque, ".comentario-autor"), /overflow-wrap: anywhere;/);
  assert.match(regla(bloque, ".comentario-sistema"), /justify-content: center;[\s\S]*color: var\(--color-tenue\);/);
  // Claro y oscuro: solo variables de la app (sin colores fijos ni tokens de burbujas).
  assert.doesNotMatch(bloque, /#[0-9a-fA-F]{3,6}\b|rgba?\(/);
  assert.doesNotMatch(css, /--burbuja-/);
});

test("CSS: al imprimir es una lista simple, con el nombre en cada uno", () => {
  const bloque = bloqueCss();
  const impresion = bloque.slice(bloque.indexOf("@media print {"));
  assert.match(impresion, /\.comentarios \{\s*max-height: none;\s*overflow: visible;/);
  assert.match(impresion, /\.comentario \{\s*margin-top: 0;/);
  assert.match(impresion, /\.comentario \.solo-lector \{\s*position: static !important;/);
  assert.match(impresion, /\.comentario-sistema \{\s*justify-content: flex-start;/);
});
