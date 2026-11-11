/* Sesión deslizante, aviso por inactividad y varias pestañas (sesion.js y
   auth.js), con un reloj falso y un localStorage compartido entre pestañas.
   Ejecutar con: node --test frontend/tests/sesion_ui.test.js */

"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const leer = (archivo) => fs.readFileSync(path.join(__dirname, "..", archivo), "utf8");
const MIN = 60 * 1000;
const HORA = 60 * MIN;

/* Un token como los del servidor (la firma no importa en el navegador). */
function token({ iat, exp, ini = iat, max = ini + 10 * 3600 }) {
  const b64 = (o) => Buffer.from(JSON.stringify(o)).toString("base64url");
  return `${b64({ alg: "HS256" })}.${b64({ sub: "1", role: "Técnico", iat, exp, ini, max })}.firma`;
}

function el(tag, doc) {
  return {
    tag, id: "", className: "", textContent: "", type: "", children: [], atributos: {}, listeners: {}, quitado: false,
    setAttribute(k, v) { this.atributos[k] = String(v); },
    addEventListener(t, fn) { (this.listeners[t] = this.listeners[t] || []).push(fn); },
    appendChild(h) { this.children.push(h); return h; },
    append(...hs) { this.children.push(...hs); },
    remove() { this.quitado = true; },
    focus() { doc.activeElement = this; },
  };
}

/* Un navegador: un localStorage (Map) y un reloj compartidos por pestañas. */
function navegador({ host = "localhost" } = {}) {
  const almacen = new Map();
  const nav = { ahora: 1_800_000_000_000, almacen, pestanas: [], pedidos: [], respuesta: null };
  nav.localStorage = {
    getItem: (k) => (almacen.has(k) ? almacen.get(k) : null),
    setItem: (k, v) => { almacen.set(k, String(v)); },
    removeItem: (k) => { almacen.delete(k); },
  };
  nav.abrir = (pagina = "/detalle.html", search = "?id=5") => {
    const doc = { activeElement: null, oyentes: {}, visibilityState: "visible" };
    doc.createElement = (tag) => el(tag, doc);
    doc.body = el("body", doc);
    doc.addEventListener = (t, fn) => { (doc.oyentes[t] = doc.oyentes[t] || []).push(fn); };
    doc.removeEventListener = (t, fn) => { doc.oyentes[t] = (doc.oyentes[t] || []).filter((f) => f !== fn); };
    const win = {
      location: { hostname: host, pathname: pagina, search, href: pagina.slice(1) + search },
      oyentes: {},
      addEventListener(t, fn) { (this.oyentes[t] = this.oyentes[t] || []).push(fn); },
      setInterval: () => 1,
      clearInterval() {},
    };
    const sandbox = {
      console, document: doc, window: win, localStorage: nav.localStorage, URLSearchParams,
      sessionStorage: { removeItem() {} },
      atob: (s) => Buffer.from(s, "base64").toString("binary"),
      escape, decodeURIComponent,
      Date: { now: () => nav.ahora },
      fetch: async (url, opciones = {}) => {
        nav.pedidos.push({ url, opciones });
        return nav.respuesta ? nav.respuesta(url, opciones) : { ok: false, status: 500, json: async () => ({}) };
      },
    };
    vm.createContext(sandbox);
    vm.runInContext(leer("js/auth.js"), sandbox);
    vm.runInContext(leer("js/sesion.js"), sandbox);
    const pestana = { doc, win, sandbox };
    pestana.control = sandbox.iniciarSesion({ doc, win, reloj: () => nav.ahora });
    pestana.ventana = () => doc.body.children.find((c) => !c.quitado && /dialogo-sesion/.test(c.className)) || null;
    pestana.actuar = (tipo = "mousemove") => (doc.oyentes[tipo] || []).forEach((fn) => fn({}));
    nav.pestanas.push(pestana);
    return pestana;
  };
  /* Pasa el tiempo y cada pestaña hace su revisión (el setInterval). */
  nav.avanzar = (ms) => {
    nav.ahora += ms;
    nav.pestanas.forEach((p) => p.control && p.control.revisar());
  };
  nav.iniciarSesion = (horasAtras = 0) => {
    const s = Math.floor(nav.ahora / 1000);
    const ini = s - horasAtras * 3600;
    almacen.set("access_token", token({ iat: s, exp: s + 3600, ini }));
    almacen.set("user", JSON.stringify({ id: 1, name: "Karla", role: "Técnico" }));
  };
  return nav;
}

const esperar = async () => { for (let i = 0; i < 5; i += 1) await new Promise((r) => setImmediate(r)); };

function partes(ventana) {
  const caja = ventana.children[0];
  const [titulo, mensaje, linea, acciones] = caja.children;
  const [salir, seguir] = acciones.children;
  return { caja, titulo, mensaje, linea, cuenta: linea.children[0], salir, seguir };
}

test("los tiempos se cambian en un solo lugar: 30 min de inactividad y 2 min de aviso", () => {
  const nav = navegador({ host: "tickets-americandata.vercel.app" });
  nav.iniciarSesion();
  const p = nav.abrir();
  const tiempos = vm.runInContext("SESION_TIEMPOS", p.sandbox);
  assert.equal(tiempos.INACTIVIDAD_MS, 30 * MIN);
  assert.equal(tiempos.AVISO_MS, 2 * MIN);
  assert.equal(p.control.tiempos, tiempos);
});

test("a los 30 minutos sin actividad aparece «¿Sigue ahí?» con la cuenta regresiva", () => {
  const nav = navegador();
  nav.iniciarSesion();
  const p = nav.abrir();
  nav.avanzar(29 * MIN);
  assert.equal(p.ventana(), null);
  nav.avanzar(1 * MIN);
  const v = partes(p.ventana());
  assert.equal(v.caja.atributos.role, "alertdialog");
  assert.equal(v.caja.atributos["aria-modal"], "true");
  assert.equal(v.titulo.textContent, "¿Sigue ahí?");
  assert.equal(v.mensaje.textContent, "Su sesión se cerrará por inactividad. ¿Desea seguir conectado?");
  assert.equal(v.cuenta.textContent, "2:00");
  assert.equal(v.salir.textContent, "Cerrar sesión");
  assert.equal(v.seguir.textContent, "Seguir conectado");
  assert.equal(p.doc.activeElement, v.seguir, "el foco va a «Seguir conectado»");
  nav.avanzar(45 * 1000);
  assert.equal(v.cuenta.textContent, "1:15");
});

test("cada actividad vuelve a empezar los 30 minutos", () => {
  const nav = navegador();
  nav.iniciarSesion();
  const p = nav.abrir();
  for (let i = 0; i < 4; i += 1) {
    nav.avanzar(20 * MIN);
    p.actuar(["mousemove", "keydown", "mousedown", "touchstart"][i]);
  }
  nav.avanzar(29 * MIN);
  assert.equal(p.ventana(), null);
});

test("con el aviso abierto, mover el mouse no lo cierra: hay que elegir", () => {
  const nav = navegador();
  nav.iniciarSesion();
  const p = nav.abrir();
  nav.avanzar(30 * MIN);
  p.actuar("mousemove");
  nav.avanzar(1000);
  assert.ok(p.ventana());
});

test("si la cuenta llega a cero se cierra por inactividad y va al login", () => {
  const nav = navegador();
  nav.iniciarSesion();
  const p = nav.abrir();
  nav.avanzar(30 * MIN);
  nav.avanzar(2 * MIN);
  assert.equal(nav.almacen.has("access_token"), false);
  assert.equal(nav.almacen.get("sesion_cierre"), "inactividad");
  assert.equal(p.win.location.href, "login.html");
  assert.equal(p.ventana(), null);
});

test("«Seguir conectado» renueva la sesión y vuelve a contar 30 minutos", async () => {
  const nav = navegador();
  nav.iniciarSesion();
  const p = nav.abrir();
  nav.respuesta = (url) => {
    const s = Math.floor(nav.ahora / 1000);
    return { ok: true, status: 200, json: async () => ({ access_token: token({ iat: s, exp: s + 3600, ini: s - 1800 }) }) };
  };
  nav.avanzar(30 * MIN);
  partes(p.ventana()).seguir.listeners.click[0]();
  await esperar();
  assert.equal(p.ventana(), null);
  const renovar = nav.pedidos.filter((x) => x.url === "/api/auth/renovar");
  assert.equal(renovar.length, 1);
  assert.equal(renovar[0].opciones.method, "POST");
  assert.match(renovar[0].opciones.headers.Authorization, /^Bearer /);
  assert.equal(p.sandbox.datosToken().iat, Math.floor(nav.ahora / 1000), "guardó el token nuevo");
  nav.avanzar(29 * MIN);
  assert.equal(p.ventana(), null);
});

test("«Cerrar sesión» del aviso cierra la sesión", () => {
  const nav = navegador();
  nav.iniciarSesion();
  const p = nav.abrir();
  nav.avanzar(30 * MIN);
  partes(p.ventana()).salir.listeners.click[0]();
  assert.equal(nav.almacen.has("access_token"), false);
  assert.equal(nav.almacen.get("sesion_cierre"), "manual");
  assert.equal(p.win.location.href, "login.html");
});

test("sesión deslizante: con actividad se renueva sola, sin pedidos de más", async () => {
  const nav = navegador({ host: "tickets-americandata.vercel.app" });
  nav.iniciarSesion();
  nav.respuesta = () => {
    const s = Math.floor(nav.ahora / 1000);
    return { ok: true, status: 200, json: async () => ({ access_token: token({ iat: s, exp: s + 3600 }) }) };
  };
  const p = nav.abrir();
  nav.avanzar(4 * MIN);
  assert.equal(nav.pedidos.length, 0, "todavía no hace falta");
  p.actuar();
  nav.avanzar(1 * MIN);
  await esperar();
  assert.equal(nav.pedidos.length, 1);
  nav.avanzar(1000);
  await esperar();
  assert.equal(nav.pedidos.length, 1, "una vez por intervalo");
  // Sin actividad nueva no se renueva aunque pase el intervalo.
  nav.avanzar(6 * MIN);
  await esperar();
  assert.equal(nav.pedidos.length, 1);
});

test("si la renovación responde 401 por el máximo de horas, se cierra con ese motivo", async () => {
  const nav = navegador();
  const s = Math.floor(nav.ahora / 1000);
  // Empezó hace 9 h 59 min: vence a las 10 h aunque el token diga más.
  nav.almacen.set("access_token", token({ iat: s - 600, exp: s + 60, ini: s - 10 * 3600 + 60 }));
  nav.respuesta = () => ({ ok: false, status: 401, json: async () => ({}) });
  const p = nav.abrir();
  nav.avanzar(61 * 1000);
  await esperar();
  assert.equal(nav.almacen.get("sesion_cierre"), "maxima");
  assert.equal(nav.almacen.has("sesion_inicio"), false, "no se vuelve a entrar en silencio");
  assert.equal(p.win.location.href, "login.html");
});

test("un token vencido manda al login con la página para volver", () => {
  const nav = navegador();
  nav.iniciarSesion();
  const p = nav.abrir();
  nav.almacen.set("sesion_actividad", String(nav.ahora + 2 * HORA)); // actividad reciente
  nav.ahora += 2 * HORA;
  nav.pestanas[0].control.revisar();
  assert.equal(nav.almacen.get("sesion_cierre"), "vencida");
  assert.equal(p.win.location.href, `login.html?volver=${encodeURIComponent("detalle.html?id=5")}`);
});

test("varias pestañas: la actividad en una cuenta para todas", () => {
  const nav = navegador();
  nav.iniciarSesion();
  const a = nav.abrir("/index.html", "");
  const b = nav.abrir("/detalle.html", "?id=7");
  nav.avanzar(25 * MIN);
  a.actuar("keydown");
  nav.avanzar(25 * MIN);
  assert.equal(a.ventana(), null);
  assert.equal(b.ventana(), null, "la otra pestaña no avisa");
});

test("varias pestañas: «Seguir conectado» en una cierra el aviso en las demás", async () => {
  const nav = navegador();
  nav.iniciarSesion();
  nav.respuesta = () => {
    const s = Math.floor(nav.ahora / 1000);
    return { ok: true, status: 200, json: async () => ({ access_token: token({ iat: s, exp: s + 3600 }) }) };
  };
  const a = nav.abrir("/index.html", "");
  const b = nav.abrir("/detalle.html", "?id=7");
  nav.avanzar(30 * MIN);
  assert.ok(a.ventana() && b.ventana(), "las dos avisan");
  partes(a.ventana()).seguir.listeners.click[0]();
  await esperar();
  // La otra se entera por el evento «storage» (o en su próxima revisión).
  (b.win.oyentes.storage || []).forEach((fn) => fn({ key: "sesion_actividad" }));
  assert.equal(a.ventana(), null);
  assert.equal(b.ventana(), null);
});

test("varias pestañas: «Cerrar sesión» en una cierra en todas", () => {
  const nav = navegador();
  nav.iniciarSesion();
  const a = nav.abrir("/index.html", "");
  const b = nav.abrir("/detalle.html", "?id=7");
  a.sandbox.logout();
  (b.win.oyentes.storage || []).forEach((fn) => fn({ key: "access_token" }));
  assert.equal(a.win.location.href, "login.html");
  assert.equal(b.win.location.href, "login.html");
  assert.equal(nav.almacen.get("sesion_cierre"), "manual");
});

test("modo rápido solo en localhost: ?sesion_rapida=1 baja a 2 min y 30 s", () => {
  const local = navegador();
  local.iniciarSesion();
  const p = local.abrir("/index.html", "?sesion_rapida=1");
  assert.equal(p.control.tiempos.INACTIVIDAD_MS, 2 * MIN);
  assert.equal(p.control.tiempos.AVISO_MS, 30 * 1000);
  assert.equal(local.abrir("/index.html", "").control.tiempos.INACTIVIDAD_MS, 2 * MIN, "se recuerda");
  assert.equal(local.abrir("/index.html", "?sesion_rapida=0").control.tiempos.INACTIVIDAD_MS, 30 * MIN);

  const vercel = navegador({ host: "tickets-americandata.vercel.app" });
  vercel.iniciarSesion();
  assert.equal(vercel.abrir("/index.html", "?sesion_rapida=1").control.tiempos.INACTIVIDAD_MS, 30 * MIN);
});

test("las páginas con sesión cargan sesion.js después de auth.js; el login no", () => {
  for (const pagina of ["index.html", "detalle.html", "crear.html", "historial.html", "metricas.html",
    "usuarios.html", "departamentos.html", "cuenta.html", "ayuda.html"]) {
    const html = leer(pagina);
    const auth = html.indexOf('src="js/auth.js');
    const sesion = html.indexOf('src="js/sesion.js');
    assert.ok(auth > 0 && sesion > auth, pagina);
    assert.match(html, /<script src="js\/sesion\.js\?v=[\w-]+" defer><\/script>/, pagina);
  }
  assert.doesNotMatch(leer("login.html"), /sesion\.js/);
});

test("la cuenta regresiva tiene estilo propio (claro y oscuro por variables)", () => {
  const css = leer("css/estilos.css");
  assert.match(css, /\.dialogo-sesion\s*\{[^}]*z-index/);
  assert.match(css, /\.dialogo-cuenta-tiempo\s*\{[^}]*var\(--color-titulo\)/);
});

test("una sesión de antes (token sin ini) recuerda su inicio por iat", () => {
  const nav = navegador();
  const s = Math.floor(nav.ahora / 1000);
  const b64 = (o) => Buffer.from(JSON.stringify(o)).toString("base64url");
  nav.almacen.set("access_token", `${b64({ alg: "HS256" })}.${b64({ sub: "1", iat: s - 600, exp: s + 3000 })}.f`);
  nav.abrir();
  assert.equal(nav.almacen.get("sesion_inicio"), String((s - 600) * 1000));
});

test("con un token que no se puede leer no se renueva (no se sabe su edad)", async () => {
  const nav = navegador();
  nav.almacen.set("access_token", "token-de-prueba");
  const p = nav.abrir();
  p.actuar();
  nav.avanzar(10 * MIN);
  await esperar();
  assert.equal(nav.pedidos.length, 0);
});
