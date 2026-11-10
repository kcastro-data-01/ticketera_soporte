/* Formulario de nuevo ticket (frontend/js/crear.js): la prioridad elegida
   con los botones es la que se envía, y los adjuntos elegidos se suben uno
   por uno después de crear el ticket.
   Ejecutar con: node --test frontend/tests/crear_ui.test.js */

"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const authSource = fs.readFileSync(path.join(__dirname, "..", "js", "auth.js"), "utf8");
const crearSource = fs.readFileSync(path.join(__dirname, "..", "js", "crear.js"), "utf8");
const adjSource = fs.readFileSync(path.join(__dirname, "..", "js", "adjuntos.js"), "utf8");
const crearHtml = fs.readFileSync(path.join(__dirname, "..", "crear.html"), "utf8").replace(/\?v=[\w-]+"/g, '"');

function nodo(extra = {}) {
  return {
    value: "", textContent: "", className: "", hidden: false, disabled: false, listeners: {},
    addEventListener(t, fn) { (this.listeners[t] = this.listeners[t] || []).push(fn); },
    ...extra,
  };
}

function montar() {
  const ids = {
    "form-crear": nodo(), title: nodo({ value: "Impresora" }), description: nodo({ value: "No imprime" }),
    category: nodo({ value: "Hardware" }), priority: nodo({ value: "Media" }), guardar: nodo(), "estado-carga": nodo(),
  };
  const opciones = ["Baja", "Media", "Alta", "Crítica"].map((v) => nodo({ value: v, checked: v === "Media" }));
  const enviados = [];
  const sandbox = {
    document: {
      getElementById: (id) => ids[id] || null,
      querySelectorAll: (sel) => (sel.includes("opcion-prioridad") ? opciones : []),
      addEventListener() {},
    },
    window: { location: { href: "" } },
    localStorage: { getItem: (k) => (k === "access_token" ? "t" : null), setItem() {}, removeItem() {} },
    fetch: async (url, o) => { enviados.push(JSON.parse(o.body)); return { ok: true, status: 201, json: async () => ({ id: 7 }) }; },
    setTimeout() {}, console: { error() {} },
  };
  vm.createContext(sandbox);
  vm.runInContext(authSource, sandbox);
  vm.runInContext(crearSource, sandbox);
  sandbox.init();
  return { sandbox, ids, opciones, enviados };
}

const elegir = (opcion, todas) => {
  todas.forEach((o) => { o.checked = o === opcion; });
  opcion.listeners.change.forEach((fn) => fn());
};

test("la prioridad empieza en Media y cambia con los botones", async () => {
  const f = montar();
  assert.equal(f.ids.priority.value, "Media");
  elegir(f.opciones[3], f.opciones);
  assert.equal(f.ids.priority.value, "Crítica");
  await f.sandbox.createTicket();
  assert.equal(f.enviados[0].priority, "Crítica");
  assert.equal(f.enviados[0].title, "Impresora");
});

test("el formulario: ejemplos en el placeholder, ayuda solo donde hace falta y botones de prioridad", () => {
  const html = fs.readFileSync(path.join(__dirname, "..", "crear.html"), "utf8");
  assert.doesNotMatch(html, /<select id="priority"/);
  assert.match(html, /<input type="hidden" id="priority" name="priority" value="Media">/);
  for (const v of ["Baja", "Media", "Alta", "Crítica"]) {
    assert.match(html, new RegExp(`name="opcion-prioridad" value="${v}"`));
  }
  // Debajo, solo lo imprescindible: prioridad y adjuntos; el departamento
  // lleva su guía de qué atiende cada uno. Los ejemplos, en el placeholder.
  assert.equal((html.match(/class="ayuda-campo"/g) || []).length, 2);
  assert.match(html, /<small id="ayuda-prioridad" class="ayuda-campo">Crítica: nadie puede trabajar o el servicio está caído\.<\/small>/);
  assert.match(html, /<small id="ayuda-adjuntos" class="ayuda-campo">Hasta 4 MB cada uno y 10 por ticket\.<\/small>/);
  assert.match(html, /id="title"[\s\S]*?placeholder="Ej\.: La impresora del 2\.º piso no imprime"/);
  assert.match(html, /id="description"[\s\S]*?placeholder="Qué sucede, desde cuándo, qué mensaje aparece y qué intentó\."/);
  assert.doesNotMatch(html, /ayuda-titulo|ayuda-descripcion|ayuda-categoria/);
  assert.match(html, /<ul id="ayuda-area" class="ayuda-campo ayuda-areas">/);
  assert.match(html, /<select id="area" name="area" required aria-describedby="ayuda-area">/);
});

// --- Adjuntos al crear el ticket ----------------------------------------------

let enfocado = null;

function elemento(tag = "div", extra = {}) {
  return {
    tag, id: "", type: "", value: "", textContent: "", className: "", hidden: false, disabled: false,
    href: "", clicked: 0, attrs: {}, children: [], listeners: {},
    addEventListener(t, fn) { (this.listeners[t] = this.listeners[t] || []).push(fn); },
    appendChild(h) { this.children.push(h); return h; },
    replaceChildren(...h) { this.children = h; },
    setAttribute(k, v) { this.attrs[k] = v; },
    focus() { enfocado = this; },
    click() { this.clicked += 1; },
    ...extra,
  };
}

const textoDe = (n) => (n.textContent || "") + (n.children || []).map(textoDe).join("");

const IDS_ADJ = ["crear-adj-subir", "crear-adj-foto", "crear-adj-archivos", "crear-adj-camara",
  "crear-adj-estado", "crear-adj-lista", "crear-resultado", "crear-resultado-titulo",
  "crear-resultado-texto", "crear-resultado-fallas", "crear-resultado-detalle"];

function respuesta(status, body) {
  return { ok: status >= 200 && status < 300, status, json: async () => body };
}

/* fetchAdjunto(nombre) → respuesta del POST de ese adjunto. */
function montarAdj({ tactil = false, imagen = null, fetchAdjunto = () => respuesta(201, {}), crear = () => respuesta(201, { id: 7 }) } = {}) {
  const ids = {
    "form-crear": elemento("form"), title: elemento("input", { value: "Impresora" }),
    description: elemento("textarea", { value: "No imprime" }), category: elemento("select", { value: "Hardware" }),
    priority: elemento("input", { value: "Media" }), guardar: elemento("button"), "estado-carga": elemento("p"),
  };
  IDS_ADJ.forEach((id) => { ids[id] = elemento(id.includes("subir") || id.includes("foto") ? "button" : "div"); });
  ["crear-adj-foto", "crear-adj-estado", "crear-adj-lista", "crear-resultado"].forEach((id) => { ids[id].hidden = true; });
  const llamadas = [];
  const avisos = [];
  const pendientes = [];
  const temporizadores = [];
  const lienzos = [];
  const sandbox = {
    document: {
      getElementById: (id) => ids[id] || null,
      querySelectorAll: () => [],
      createElement: (tag) => {
        const n = elemento(tag);
        if (tag === "canvas") {
          n.getContext = () => ({ drawImage() {} });
          n.toBlob = (cb, tipo) => cb({ size: 1000, type: tipo });
          lienzos.push(n);
        }
        return n;
      },
      createTextNode: (t) => ({ textContent: t, children: [] }),
      addEventListener() {},
    },
    window: { location: { href: "", search: "" }, matchMedia: (q) => ({ matches: tactil && q === "(pointer: coarse)" }) },
    localStorage: { getItem: (k) => (k === "access_token" ? "t" : null), setItem() {}, removeItem() {} },
    fetch: async (url, o = {}) => {
      llamadas.push({ url, method: o.method || "GET", headers: o.headers || {}, body: o.body });
      if (url === "/api/tickets") return crear();
      const nombre = decodeURIComponent(url.split("nombre=")[1] || "");
      return fetchAdjunto(nombre);
    },
    setTimeout: (fn) => { temporizadores.push(fn); return 0; },
    URLSearchParams, Date, Number, Math, Array, Promise, encodeURIComponent, decodeURIComponent,
    console: { error() {} },
  };
  if (imagen) sandbox.createImageBitmap = async () => ({ ...imagen, close() {} });
  vm.createContext(sandbox);
  vm.runInContext(authSource, sandbox);
  vm.runInContext(adjSource, sandbox);
  vm.runInContext(crearSource, sandbox);
  sandbox.mostrarAviso = (mensaje, tipo) => avisos.push({ mensaje, tipo });
  sandbox.avisoPendiente = (mensaje) => pendientes.push(mensaje);
  sandbox.init();
  return { sandbox, ids, llamadas, avisos, pendientes, temporizadores, lienzos };
}

const pdf = (nombre = "factura.pdf", size = 2000) => ({ name: nombre, size, type: "application/pdf" });
const filas = (f) => f.ids["crear-adj-lista"].children;
const postsAdjuntos = (f) => f.llamadas.filter((l) => l.method === "POST" && l.url.includes("/adjuntos"));

test("crear.html tiene «Adjuntar archivos», «Sacar foto», la lista y el resultado; carga adjuntos.js antes", () => {
  assert.match(crearHtml, /<button type="button" id="crear-adj-subir" class="secundario"[^>]*>Adjuntar archivos<\/button>/);
  assert.match(crearHtml, /id="crear-adj-foto" class="secundario" hidden>Sacar foto<\/button>/);
  assert.match(crearHtml, /id="crear-adj-archivos" multiple hidden\s+accept="\.jpg,\.jpeg,\.png,\.pdf,\.docx,\.xlsx,\.txt/);
  assert.match(crearHtml, /id="crear-adj-camara" accept="image\/\*" capture="environment" hidden/);
  assert.match(crearHtml, /<ul id="crear-adj-lista" class="adjuntos-lista adjuntos-elegidos" aria-label="Archivos elegidos" hidden><\/ul>/);
  assert.match(crearHtml, /Hasta 4 MB cada uno y 10 por ticket/);
  assert.match(crearHtml, /<section id="crear-resultado"[^>]*hidden>/);
  assert.match(crearHtml, /id="crear-resultado-detalle"[^>]*>Ir al ticket y reintentar<\/a>/);
  assert.ok(crearHtml.indexOf('src="js/adjuntos.js"') < crearHtml.indexOf('src="js/crear.js"'));
  // Los adjuntos van dentro del formulario, antes de «Crear ticket».
  assert.ok(crearHtml.indexOf('id="crear-adj-subir"') < crearHtml.indexOf('id="guardar"'));
});

test("«Adjuntar archivos» abre el selector; «Sacar foto» solo en pantallas táctiles", () => {
  const escritorio = montarAdj();
  assert.equal(escritorio.ids["crear-adj-foto"].hidden, true);
  escritorio.ids["crear-adj-subir"].listeners.click[0]();
  assert.equal(escritorio.ids["crear-adj-archivos"].clicked, 1);
  const celular = montarAdj({ tactil: true });
  assert.equal(celular.ids["crear-adj-foto"].hidden, false);
  celular.ids["crear-adj-foto"].listeners.click[0]();
  assert.equal(celular.ids["crear-adj-camara"].clicked, 1);
});

test("lo elegido se lista con su tamaño y un ✕ para quitarlo", async () => {
  const f = montarAdj();
  await f.sandbox.agregarElegidos([pdf("factura.pdf", 1536), { name: "log.txt", size: 900, type: "text/plain" }]);
  assert.equal(f.ids["crear-adj-lista"].hidden, false);
  assert.equal(filas(f).length, 2);
  assert.match(textoDe(filas(f)[0]), /factura\.pdf1,5 KB/);
  assert.match(textoDe(filas(f)[1]), /log\.txt900 B/);
  const quitar = filas(f)[0].children.at(-1);
  assert.equal(quitar.tag, "button");
  assert.equal(quitar.textContent, "✕");
  assert.equal(quitar.className, "adjunto-quitar");
  assert.equal(quitar.attrs["aria-label"], "Quitar factura.pdf");
});

test("✕ quita el archivo y el foco pasa al siguiente ✕ (o a «Adjuntar archivos»)", async () => {
  const f = montarAdj();
  await f.sandbox.agregarElegidos([pdf("a.pdf"), pdf("b.pdf")]);
  filas(f)[0].children.at(-1).listeners.click[0]();
  assert.deepEqual(filas(f).map((n) => textoDe(n.children[0].children[0])), ["b.pdf"]);
  assert.equal(enfocado, filas(f)[0].children.at(-1));
  filas(f)[0].children.at(-1).listeners.click[0]();
  assert.equal(f.ids["crear-adj-lista"].hidden, true);
  assert.equal(enfocado, f.ids["crear-adj-subir"]);
});

test("tipo no permitido o más de 4 MB: no se agregan y se explica", async () => {
  const f = montarAdj();
  await f.sandbox.agregarElegidos([
    { name: "programa.exe", size: 10, type: "application/x-msdownload" },
    pdf("enorme.pdf", 4 * 1024 * 1024 + 1),
    pdf("bien.pdf"),
  ]);
  assert.equal(filas(f).length, 1);
  const estado = f.ids["crear-adj-estado"];
  assert.equal(estado.hidden, false);
  assert.equal(estado.className, "estado error");
  assert.match(estado.textContent, /«programa\.exe»: tipo no permitido\. Se aceptan jpg, png, pdf, docx, xlsx o txt\./);
  assert.match(estado.textContent, /«enorme\.pdf» pesa más de 4 MB\./);
});

test("como máximo 10 por ticket", async () => {
  const f = montarAdj();
  await f.sandbox.agregarElegidos(Array.from({ length: 12 }, (_, i) => pdf(`a${i}.pdf`)));
  assert.equal(filas(f).length, 10);
  assert.match(f.ids["crear-adj-estado"].textContent, /Se pueden adjuntar hasta 10 archivos por ticket\./);
  assert.equal(f.ids["crear-adj-subir"].disabled, true, "con 10 no se eligen más");
});

test("una foto grande se achica a 2000 px al elegirla", async () => {
  const f = montarAdj({ imagen: { width: 4000, height: 3000 } });
  await f.sandbox.agregarElegidos([{ name: "IMG_1.heic", size: 3_000_000, type: "image/heic" }]);
  assert.equal(f.lienzos[0].width, 2000);
  assert.equal(f.lienzos[0].height, 1500);
  assert.match(textoDe(filas(f)[0]), /IMG_1\.jpg1000 B/);
});

test("sin adjuntos se crea el ticket como siempre", async () => {
  const f = montarAdj();
  await f.sandbox.createTicket();
  assert.deepEqual(f.llamadas.map((l) => l.url), ["/api/tickets"]);
  assert.deepEqual(f.pendientes, ["Ticket #7 guardado correctamente."]);
  assert.equal(f.temporizadores.length, 1, "redirige al listado");
});

test("primero se crea el ticket y después se sube cada archivo, uno por uno", async () => {
  const f = montarAdj();
  const a = pdf("Factura año.pdf");
  const b = { name: "log.txt", size: 10, type: "text/plain" };
  await f.sandbox.agregarElegidos([a, b]);
  await f.sandbox.createTicket();
  assert.deepEqual(f.llamadas.map((l) => `${l.method} ${l.url}`), [
    "POST /api/tickets",
    "POST /api/tickets/7/adjuntos?nombre=Factura%20a%C3%B1o.pdf",
    "POST /api/tickets/7/adjuntos?nombre=log.txt",
  ]);
  assert.equal(postsAdjuntos(f)[0].headers["Content-Type"], "application/octet-stream");
  assert.equal(postsAdjuntos(f)[0].body, a);
  assert.deepEqual(f.pendientes, ["Ticket #7 guardado correctamente con 2 adjuntos."]);
  assert.equal(f.temporizadores.length, 1);
  assert.equal(f.ids.guardar.disabled, true);
});

test("si un archivo falla el ticket queda creado: dice cuál y por qué, con el enlace para reintentar", async () => {
  const f = montarAdj({
    fetchAdjunto: (nombre) => (nombre === "dañado.pdf"
      ? respuesta(422, { detail: "«dañado.pdf»: el contenido no corresponde a un archivo PDF válido." })
      : respuesta(201, {})),
  });
  await f.sandbox.agregarElegidos([pdf("bien.pdf"), pdf("dañado.pdf"), pdf("otro.pdf")]);
  await f.sandbox.createTicket();

  assert.equal(postsAdjuntos(f).length, 3, "sigue con los demás");
  assert.equal(f.ids["form-crear"].hidden, true);
  assert.equal(f.ids["crear-resultado"].hidden, false);
  assert.equal(f.ids["crear-resultado-titulo"].textContent, "Ticket #7 creado");
  assert.equal(enfocado, f.ids["crear-resultado-titulo"]);
  assert.equal(f.ids["crear-resultado-texto"].textContent,
    "No se pudo subir 1 adjunto; los otros 2 quedaron guardados. Puede reintentarlos desde el detalle del ticket.");
  assert.equal(textoDe(f.ids["crear-resultado-fallas"]), "dañado.pdf: El contenido no corresponde a un archivo PDF válido.");
  assert.equal(f.ids["crear-resultado-detalle"].href, "detalle.html?id=7");
  assert.equal(f.temporizadores.length, 0, "no redirige");
  assert.deepEqual(f.pendientes, []);
  assert.deepEqual(f.avisos.at(-1), { mensaje: "Ticket #7 creado. No se pudo subir 1 adjunto.", tipo: "error" });
  assert.equal(f.ids.guardar.disabled, true, "el ticket ya existe: no se vuelve a crear");
});

test("si fallan todos o se corta la conexión, también lo dice", async () => {
  const f = montarAdj({ fetchAdjunto: () => { throw new Error("sin red"); } });
  await f.sandbox.agregarElegidos([pdf("a.pdf"), pdf("b.pdf")]);
  await f.sandbox.createTicket();
  assert.equal(f.ids["crear-resultado-texto"].textContent,
    "No se pudieron subir 2 adjuntos. Puede reintentarlos desde el detalle del ticket.");
  assert.match(textoDe(f.ids["crear-resultado-fallas"]), /^a\.pdf: No se pudo subir «a\.pdf»\./);
});

test("si el ticket no se crea no se sube nada y los archivos siguen elegidos", async () => {
  const f = montarAdj({ crear: () => respuesta(500, {}) });
  await f.sandbox.agregarElegidos([pdf("a.pdf")]);
  await f.sandbox.createTicket();
  assert.equal(postsAdjuntos(f).length, 0);
  assert.equal(filas(f).length, 1);
  assert.equal(f.ids.guardar.disabled, false);
  assert.equal(f.ids["crear-resultado"].hidden, true);
});

test("los nombres se pintan como texto, no como HTML", async () => {
  const f = montarAdj();
  await f.sandbox.agregarElegidos([pdf("<img src=x onerror=alert(1)>.pdf")]);
  assert.equal(filas(f)[0].children[0].children[0].textContent, "<img src=x onerror=alert(1)>.pdf");
  assert.ok(!crearSource.includes("innerHTML"));
});

// --- Área de IT ------------------------------------------------------------------

function cargarCrear(valores) {
  const nodos = {};
  const el = (id) => (nodos[id] = nodos[id] || { id, value: valores[id] || "", required: false, options: [],
    replaceChildren() { this.options = []; }, appendChild(o) { this.options.push(o); return o; },
    addEventListener() {} });
  const sandbox = {
    console,
    document: { getElementById: el, createElement: () => ({}), addEventListener() {} },
  };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, "..", "js", "crear.js"), "utf8"), sandbox);
  return { sandbox, nodos };
}

test("crear.js envía el área elegida y la exige cuando hay áreas", async () => {
  const { sandbox, nodos } = cargarCrear({ title: "VPN caída", description: "No conecta", category: "Red",
    priority: "Media", area: "3" });
  assert.deepEqual(JSON.parse(JSON.stringify(sandbox.getPayload())),
    { title: "VPN caída", description: "No conecta", category: "Red", priority: "Media", area_id: 3 });
  sandbox.cargarAreas = async () => [{ id: 3, name: "Redes", is_active: true }];
  sandbox.llenarSelectAreas = (select, areas, opciones) => { select.lista = areas; select.primera = opciones.primera; };
  await sandbox.iniciarAreas();
  assert.equal(nodos.area.required, true);
  assert.equal(nodos.area.primera, "Elija un departamento");
  nodos.area.value = "";
  assert.equal(sandbox.validatePayload(sandbox.getPayload()), "Elija el departamento del ticket.");
});

test("sin áreas activas el ticket se crea «Sin área» (no se exige)", async () => {
  const { sandbox, nodos } = cargarCrear({ title: "VPN caída", description: "No conecta", area: "" });
  sandbox.cargarAreas = async () => [];
  sandbox.llenarSelectAreas = (select, areas, opciones) => { select.primera = opciones.primera; };
  await sandbox.iniciarAreas();
  assert.equal(nodos.area.required, false);
  assert.equal(sandbox.validatePayload(sandbox.getPayload()), "");
  assert.equal(sandbox.formatValidation({ detail: "Elija el área de IT del ticket." }), "Elija el área de IT del ticket.");
});

// --- Dos columnas que usan todo el ancho ---------------------------------------

test("crear.html: a la izquierda título y descripción; a la derecha departamento, categoría, prioridad y adjuntos", () => {
  const html = fs.readFileSync(path.join(__dirname, "..", "crear.html"), "utf8");
  assert.match(html, /<form id="form-crear" class="filtros formulario formulario-crear formulario-ticket" novalidate>/);
  const izquierda = html.slice(html.indexOf('<div class="crear-columna crear-principal">'), html.indexOf('<div class="crear-columna crear-lateral">'));
  const derecha = html.slice(html.indexOf('<div class="crear-columna crear-lateral">'), html.indexOf('<div class="acciones acciones-crear">'));
  assert.ok(izquierda && derecha);
  assert.match(izquierda, /id="title"[\s\S]*<label class="campo campo-descripcion">[\s\S]*id="description"/);
  const orden = ['id="area"', 'id="category"', 'campo-prioridad', 'campo-adjuntos'].map((t) => derecha.indexOf(t));
  assert.ok(orden.every((i) => i >= 0), "todo a la derecha");
  assert.deepEqual([...orden].sort((a, b) => a - b), orden, "en ese orden");
  // «Crear ticket» después de las dos columnas, abajo a la derecha.
  assert.match(html, /<div class="acciones acciones-crear">\s*<button type="submit" id="guardar">Crear ticket<\/button>\s*<\/div>\s*<\/form>/);
  // El departamento se llama «Soporte IT», también en la guía.
  assert.match(derecha, /<li><strong>Soporte IT<\/strong>: computadoras, impresoras, programas\.<\/li>/);
  assert.doesNotMatch(html.replace(/<p class="menu-titulo" id="menu-soporte">Soporte<\/p>/, ""), /\bSoporte\b(?! IT| de la empresa)/);
});

test("CSS: dos columnas a todo el ancho; una en tablet y celular; guía compacta", () => {
  const css = fs.readFileSync(path.join(__dirname, "..", "css", "estilos.css"), "utf8");
  assert.match(css, /\.formulario-ticket \{\s*max-width: none;/);
  assert.match(css, /\.crear-columnas \{\s*display: grid;\s*grid-template-columns: minmax\(0, 3fr\) minmax\(0, 2fr\);/);
  assert.match(css, /\.campo-descripcion textarea \{\s*flex: 1;\s*min-height: 300px;/, "descripción más alta");
  assert.match(css, /\.acciones-crear \{\s*justify-content: flex-end;/, "botón a la derecha");
  assert.match(css, /@media \(max-width: 900px\) \{\s*\.crear-columnas \{\s*grid-template-columns: minmax\(0, 1fr\);/);
  assert.match(css, /\.ayuda-campo\.ayuda-areas \{[^}]*background: var\(--color-fondo-neutro\);[^}]*font-size: 0\.78rem;/);
});
