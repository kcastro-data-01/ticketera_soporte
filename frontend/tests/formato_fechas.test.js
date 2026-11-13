/* Una sola función de fecha y hora para toda la app (formatearFechaHora en
   auth.js): «11/11/2026, 3:40 p. m.», hora de Costa Rica, 12 horas, sin
   segundos. Ejecutar con: node --test frontend/tests/formato_fechas.test.js */

"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const JS = path.join(__dirname, "..", "js");
const leer = (archivo) => fs.readFileSync(path.join(JS, archivo), "utf8");

function cargar() {
  const sandbox = {
    console, Intl, Date, URLSearchParams,
    document: { getElementById: () => null, addEventListener() {} },
    window: { location: { search: "" } },
    localStorage: { getItem: () => null, setItem() {}, removeItem() {} },
  };
  vm.createContext(sandbox);
  vm.runInContext(leer("auth.js"), sandbox);
  return sandbox;
}

test("12 horas con a. m. y p. m., sin segundos, en hora de Costa Rica", () => {
  const { formatearFechaHora } = cargar();
  assert.equal(formatearFechaHora("2026-11-11T17:15:00Z"), "11/11/2026, 11:15 a. m.");
  assert.equal(formatearFechaHora("2026-11-11T21:40:09Z"), "11/11/2026, 3:40 p. m.");
  assert.equal(formatearFechaHora("2026-11-12T18:00:00Z"), "12/11/2026, 12:00 p. m.", "mediodía");
  assert.equal(formatearFechaHora("2026-11-12T06:05:00Z"), "12/11/2026, 12:05 a. m.", "medianoche");
  assert.equal(formatearFechaHora("2026-11-12T05:59:00Z"), "11/11/2026, 11:59 p. m.", "en UTC ya es 12; en Costa Rica, 11");
  assert.equal(formatearFechaHora(new Date("2026-11-11T21:40:00Z")), "11/11/2026, 3:40 p. m.", "también con un Date");
});

test("partes sueltas y valores vacíos", () => {
  const { formatearFechaHora } = cargar();
  assert.equal(formatearFechaHora("2026-11-11T21:40:00Z", { parte: "fecha" }), "11/11/2026");
  assert.equal(formatearFechaHora("2026-11-11T21:40:00Z", { parte: "hora" }), "3:40 p. m.");
  for (const vacio of [null, undefined, "", "no es fecha"]) assert.equal(formatearFechaHora(vacio), "—");
});

test("ningún otro script tiene su propio formato de fecha u hora", () => {
  for (const archivo of fs.readdirSync(JS).filter((f) => f.endsWith(".js") && f !== "auth.js")) {
    const codigo = leer(archivo)
      // Tamaños de archivo («12,5 KB»): números, no fechas.
      .replace(/\.toLocaleString\("es-CR", \{ maximumFractionDigits: \d \}\)/g, "");
    assert.doesNotMatch(codigo, /toLocaleString\(|toLocaleTimeString\(|getHours\(\)|function formatFecha/, archivo);
    assert.doesNotMatch(codigo, /hour:\s*"/, `${archivo}: la hora sale de formatearFechaHora`);
  }
});

test("listado, detalle, historial, comentarios, adjuntos, IA, impresión y chat la usan", () => {
  assert.match(leer("app.js"), /formatearFechaHora\(ticket\.created_at\)/);
  const detalle = leer("detalle.js");
  for (const uso of ["formatearFechaHora(ticket.created_at)", "formatearFechaHora(ticket.updated_at)",
    "formatearFechaHora(comment.created_at)", "formatearFechaHora(entry.created_at)",
    "Impreso el ${formatearFechaHora(", 'formatearFechaHora(fecha, { parte: "hora" })']) {
    assert.ok(detalle.includes(uso), uso);
  }
  assert.match(leer("historial.js"), /formatearFechaHora\(entry\.created_at, \{ parte: "hora" \}\)/);
  assert.match(leer("adjuntos.js"), /formatearFechaHora\(valor\)/);
  assert.match(leer("explicacion.js"), /formatearFechaHora\(valor\)/);
  assert.match(leer("asistente.js"), /formatearFechaHora\(mensaje\.hora, \{ parte: "hora" \}\)/);
});
