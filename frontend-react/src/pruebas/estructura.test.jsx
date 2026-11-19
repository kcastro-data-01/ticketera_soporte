/* La pantalla se arma con body.app como contenedor flex de .barra-lateral y
   .app-principal (estilos.css): el <div id="raiz"> de React no debe generar
   caja (display: contents), o el contenido cae debajo del menú. */
import fs from "node:fs";
import path from "node:path";
import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { conSesion, renderApp, respuesta, simularFetch } from "./ayudas.jsx";

const SRC = path.resolve(__dirname, "..");

describe("estructura de la página", () => {
  it("#raiz usa display: contents y se carga después de estilos.css", () => {
    expect(fs.readFileSync(path.join(SRC, "raiz.css"), "utf8")).toMatch(/#raiz\s*\{\s*display:\s*contents;/);
    const main = fs.readFileSync(path.join(SRC, "main.jsx"), "utf8");
    expect(main.indexOf("frontend/css/estilos.css")).toBeGreaterThan(-1);
    expect(main.indexOf("./raiz.css")).toBeGreaterThan(main.indexOf("frontend/css/estilos.css"));
  });

  it("mismo árbol que index.html: body.app > aside.barra-lateral + .app-principal > cabecera, main.contenido, pie", async () => {
    conSesion("Administrador");
    simularFetch([["/api/", respuesta([])]]);
    const { container } = renderApp("/");
    await screen.findByRole("heading", { name: "Tickets" });
    expect(document.body).toHaveClass("app");
    const hijos = [...container.children].map((el) => `${el.tagName.toLowerCase()}.${el.className}`);
    expect(hijos).toEqual(["aside.barra-lateral", "div.app-principal"]);
    const principal = container.querySelector(".app-principal");
    expect([...principal.children].map((el) => el.tagName.toLowerCase() + "." + el.className.split(" ")[0]))
      .toEqual(["header.cabecera", "main.contenido", "footer.pie"]);
    const barra = container.querySelector(".barra-lateral");
    expect([...barra.children].map((el) => el.className)).toEqual(["marca", "boton-plegar", "menu", "menu-usuario"]);
    const contenido = principal.querySelector("main.contenido");
    expect(contenido.querySelector(":scope > form#form-filtros.filtros")).not.toBeNull();
    expect(contenido.querySelector(":scope > #tabla-tickets.tabla-scroll > table.listado > thead")).not.toBeNull();
  });
});
