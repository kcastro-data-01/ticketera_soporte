/* Menú lateral moderno (mismo CSS en todas las páginas, mismos colores de
   la marca): secciones separadas solo con espacio, títulos tenues, página
   actual como píldora, encabezado compacto en una fila, usuario como
   tarjeta y contador discreto; plegado, celular y modo oscuro sin código
   inline (CSP). */
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const RAIZ = path.join(__dirname, "..");
const leer = (archivo) => fs.readFileSync(path.join(RAIZ, archivo), "utf8");
const css = leer("css/estilos.css");
const PAGINAS_CON_MENU = fs.readdirSync(RAIZ).filter((f) => f.endsWith(".html") && leer(f).includes('class="barra-lateral"'));

/* Regla de primer nivel exacta (empieza al comienzo de una línea). */
const regla = (selector) => {
  const inicio = css.indexOf(`\n${selector} {`);
  assert.ok(inicio >= 0, selector);
  return css.slice(inicio, css.indexOf("\n}", inicio + 1));
};
/* Todo el CSS que toca el menú lateral. */
const bloqueMenu = css.slice(css.indexOf("/* ---------- Estructura de la aplicación"), css.indexOf(".icono {", css.indexOf("/* ---------- Estructura de la aplicación")));
const bloqueUsuario = css.slice(css.indexOf("/* ===== Usuario abajo del menú lateral"), css.indexOf("/* ===== Ventana de confirmación"));
const celular = css.slice(css.indexOf("@media (max-width: 900px)"), css.indexOf("\n}\n", css.indexOf("@media (max-width: 900px)")));

test("tokens del menú: mismos colores de la marca y títulos con contraste AA", () => {
  const raiz = css.slice(css.indexOf(":root {"), css.indexOf("\n}", css.indexOf(":root {")));
  assert.match(raiz, /--color-marino: #0b184d;/);
  assert.match(raiz, /--color-marca: #0041ff;/);
  assert.match(raiz, /--color-menu-titulo: #7488cf;/);
  assert.match(raiz, /--color-menu-activo: rgba\(125, 155, 255, 0\.18\);/);
  assert.match(raiz, /--radio-menu: 8px;/);
  const lum = (hex) => {
    const c = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
      .map((x) => (x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4));
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
  };
  const contraste = (a, b) => (Math.max(lum(a), lum(b)) + 0.05) / (Math.min(lum(a), lum(b)) + 0.05);
  for (const fondo of ["#0b184d", "#0a0f1d"]) {
    assert.ok(contraste("#7488cf", fondo) >= 4.5, `títulos sobre ${fondo}`);
  }
});

test("1. sin líneas divisorias entre secciones ni arriba del usuario (ni en la marca)", () => {
  assert.doesNotMatch(regla(".menu-seccion + .menu-seccion"), /border/);
  assert.doesNotMatch(regla(".marca"), /border/);
  assert.doesNotMatch(regla(".menu-usuario"), /border|padding-top/);
  assert.doesNotMatch(bloqueMenu, /border-(top|bottom): 1px solid/);
  assert.doesNotMatch(bloqueUsuario.slice(0, bloqueUsuario.indexOf(".menu-usuario-lista {")), /border-top: 1px solid/);
});

test("2. títulos de sección más chicos, tenues y con menos peso", () => {
  const titulo = regla(".menu-titulo");
  assert.match(titulo, /font-size: 0\.625rem;/);
  assert.match(titulo, /font-weight: 500;/);
  assert.match(titulo, /color: var\(--color-menu-titulo\);/);
});

test("3. página actual como píldora de 8 px, texto e ícono claros, sin barra a la izquierda", () => {
  assert.match(regla(".menu-enlace"), /border-radius: var\(--radio-menu\);/);
  const activo = regla(".menu-enlace.activo");
  assert.match(activo, /background: var\(--color-menu-activo\);/);
  assert.match(activo, /color: var\(--color-texto-inverso\);/);
  assert.match(css, /\.menu-enlace:hover \.icono,\n\.menu-enlace\.activo \.icono \{\s*color: var\(--color-texto-inverso\);/);
  assert.doesNotMatch(css, /\.menu-enlace\.activo::before|\.menu-usuario-boton\.activo::before/);
});

test("4. más espacio entre opciones, íconos iguales y efecto suave al pasar el mouse", () => {
  assert.match(regla(".menu-seccion"), /gap: 0\.3rem;/);
  const enlace = regla(".menu-enlace");
  assert.match(enlace, /min-height: 40px;/);
  assert.match(enlace, /transition: background-color 0\.18s ease, color 0\.18s ease;/);
  const icono = regla(".menu-enlace .icono");
  assert.match(icono, /width: 20px;\s*height: 20px;/);
  assert.match(icono, /transition: color 0\.18s ease;/);
  assert.match(regla(".icono"), /flex-shrink: 0;/);
  assert.match(regla(".menu-enlace:hover"), /background: var\(--color-menu-hover\);/);
});

test("5. encabezado compacto: logo, nombre y botón en una fila; «Sistema de tickets» debajo, más chico", () => {
  const marca = regla(".marca");
  assert.match(marca, /display: flex;\s*align-items: center;/);
  assert.match(marca, /padding: 0 calc\(24px \+ 0\.4rem\) 0 0\.25rem;/, "lugar para el botón a la derecha");
  assert.match(regla(".marca-logo"), /width: 30px;\s*height: 30px;/);
  assert.match(regla(".marca-nombre"), /font-size: 0\.8rem;[^}]*white-space: nowrap;/);
  assert.match(regla(".marca-sub"), /font-size: 0\.62rem;/);
  const boton = regla(".boton-plegar");
  assert.match(boton, /position: absolute;\s*top: calc\(1rem \+ 3px\);\s*right: 0\.75rem;/);
  assert.match(boton, /width: 24px;\s*height: 24px;/);
  assert.match(regla(".barra-lateral"), /position: sticky;/, "posicionada: el botón se ubica respecto de ella");
  assert.match(regla(".barra-lateral"), /padding: 1rem 0\.75rem;/);
  for (const pagina of PAGINAS_CON_MENU) {
    assert.match(leer(pagina), /<a href="index\.html" class="marca">\s*<img src="images\/logo-circular\.jpg" alt="" class="marca-logo">\s*<span class="marca-texto">\s*<span class="marca-nombre">American Data Networks<\/span>\s*<span class="marca-sub">Sistema de tickets<\/span>/, pagina);
  }
});

test("6. usuario abajo como tarjeta redondeada, apenas más clara que el menú", () => {
  const boton = regla(".menu-usuario-boton");
  assert.match(boton, /border-radius: 10px;/);
  assert.match(boton, /background: var\(--color-menu-tarjeta\);/);
  assert.match(css, /--color-menu-tarjeta: rgba\(255, 255, 255, 0\.05\);/);
});

test("7. contador de «Tickets» discreto: pastilla chica", () => {
  const contador = regla(".menu-enlace .menu-contador");
  assert.match(contador, /min-width: 18px;\s*height: 18px;/);
  assert.match(contador, /border-radius: var\(--radio-pill\);/);
  assert.match(contador, /background: rgba\(255, 255, 255, 0\.12\);/);
  assert.match(contador, /font-size: 0\.66rem;/);
});

test("8. plegado: logo y botón centrados uno debajo del otro, solo íconos", () => {
  const plegado = css.slice(css.indexOf("@media (min-width: 901px)"), css.indexOf(".menu-enlace:focus-visible"));
  assert.match(plegado, /body\.menu-plegado \.marca \{\s*justify-content: center;\s*min-height: 0;\s*margin-bottom: 0\.6rem;\s*padding: 0;/);
  assert.match(plegado, /body\.menu-plegado \.boton-plegar \{\s*position: static;\s*align-self: center;/);
  assert.match(plegado, /body\.menu-plegado \.marca-texto,\n  body\.menu-plegado \.menu-enlace span,\n  body\.menu-plegado \.menu-titulo \{\n    display: none;/);
});

test("8. celular: menú arriba, sin barra de color abajo y sin fondo de tarjeta junto a la marca", () => {
  assert.doesNotMatch(celular, /::before/);
  assert.match(celular, /\.barra-lateral \.menu-usuario-boton \{\s*width: auto;\s*background: transparent;/);
  assert.match(celular, /\.boton-plegar \{\s*display: none;/);
});

test("8. modo oscuro: el menú usa los mismos tokens (sin colores fijos nuevos en las reglas)", () => {
  for (const sel of [".menu-titulo", ".menu-enlace.activo", ".menu-enlace:hover", ".menu-usuario-boton"]) {
    assert.doesNotMatch(regla(sel), /#[0-9a-f]{3,6}\b/i, sel);
  }
});

test("8. sin código inline (CSP): ni style= ni <style> ni manejadores en las páginas con menú", () => {
  assert.ok(PAGINAS_CON_MENU.length >= 9, PAGINAS_CON_MENU.join(", "));
  for (const pagina of PAGINAS_CON_MENU) {
    const html = leer(pagina);
    assert.doesNotMatch(html, /\sstyle="|<style[\s>]|\son[a-z]+="/i, pagina);
  }
});
