/* Formularios de usuarios (usuarios.html + usuarios.js): ayuda gris, campos
   alineados y errores debajo del campo.
   Ejecutar con: node --test frontend/tests/usuarios_form.test.js */

"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const leer = (archivo) => fs.readFileSync(path.join(__dirname, "..", archivo), "utf8");
const html = leer("usuarios.html");

function cargar() {
  const nodos = new Map();
  const nodo = (id) => {
    if (!nodos.has(id)) {
      nodos.set(id, {
        id, textContent: "", hidden: id.startsWith("error-"), atributos: {},
        setAttribute(k, v) { this.atributos[k] = v; }, removeAttribute(k) { delete this.atributos[k]; },
        focus() { this.enfocado = true; },
      });
    }
    return nodos.get(id);
  };
  const sandbox = {
    console,
    document: { getElementById: nodo, addEventListener() {}, querySelectorAll: () => [] },
    window: { location: {} },
    localStorage: { getItem: () => null, setItem() {}, removeItem() {} },
  };
  vm.createContext(sandbox);
  vm.runInContext(leer("js/auth.js"), sandbox);
  vm.runInContext(leer("js/usuarios.js"), sandbox);
  return { sandbox, nodo };
}

test("cada mensaje va al campo que corresponde", () => {
  const { sandbox } = cargar();
  assert.equal(sandbox.campoDelError("El nombre no puede estar vacío."), "nombre");
  assert.equal(sandbox.campoDelError("Ese correo electrónico ya está registrado."), "email");
  assert.equal(sandbox.campoDelError("La contraseña debe tener al menos 6 caracteres.", "editar-"), "editar-password");
  assert.equal(sandbox.campoDelError("Seleccione un rol válido."), "rol");
  assert.equal(sandbox.campoDelError("Error de API (500)."), "", "sin campo: queda el aviso general");
});

test("el error se muestra debajo del campo y se limpia", () => {
  const { sandbox, nodo } = cargar();
  assert.equal(sandbox.mostrarErrorCampo("El correo electrónico no tiene un formato válido."), true);
  assert.equal(nodo("error-email").hidden, false);
  assert.equal(nodo("error-email").textContent, "El correo electrónico no tiene un formato válido.");
  assert.equal(nodo("email").atributos["aria-invalid"], "true");
  assert.equal(nodo("email").enfocado, true);
  sandbox.limpiarErroresCampo();
  assert.equal(nodo("error-email").hidden, true);
  assert.equal(nodo("email").atributos["aria-invalid"], undefined);
});

test("los dos formularios tienen ayuda gris, error por campo y botón secundario", () => {
  for (const id of ["nombre", "email", "password", "rol", "editar-nombre", "editar-email", "editar-password", "editar-rol"]) {
    assert.match(html, new RegExp(`<small id="ayuda-${id}" class="ayuda-campo">`), id);
    assert.match(html, new RegExp(`<small id="error-${id}" class="error-campo" role="alert" hidden></small>`), id);
    assert.match(html, new RegExp(`id="${id}"[^>]*aria-describedby="ayuda-${id} error-${id}"`), id);
  }
  assert.match(html, /<button type="reset" id="limpiar-usuario" class="secundario">Limpiar<\/button>/);
  assert.equal((html.match(/class="filtros formulario formulario-crear"/g) || []).length, 2);
});
