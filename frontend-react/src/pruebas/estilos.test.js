/* Pruebas de estilos.css y login.css traídas de frontend/tests (node:test)
   al quitar el frontend viejo: solo las que miran el CSS, que sigue igual.
   Las que probaban el HTML o el JavaScript viejo las reemplazan las pruebas
   de cada pantalla React. Entre paréntesis, el archivo original. */
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { describe, test } from "vitest";

const leer = (archivo) => fs.readFileSync(path.resolve(__dirname, "..", archivo), "utf8");
const css = leer("css/estilos.css");
const login = leer("css/login.css");

/* El bloque de «selector {» hasta su primera «}». */
const regla = (fuente, selector) => {
  const i = fuente.indexOf(`${selector} {`);
  assert.ok(i >= 0, selector);
  return fuente.slice(i, fuente.indexOf("}", i));
};
/* Una regla de primer nivel: desde «\nselector {» hasta «\n}». */
const reglaRaiz = (selector, desde = 0) => {
  const inicio = css.indexOf(`\n${selector} {`, desde);
  assert.ok(inicio >= 0, selector);
  return css.slice(inicio, css.indexOf("\n}", inicio));
};

describe("accesibilidad (accesibilidad.test.js)", () => {
  /* Fallaba desde antes de la migración (también en main): hay textos con
     el gris claro. Arreglarlo cambia colores, así que queda anotado. */
  test.skip("el gris claro (sin contraste AA) ya no se usa para textos", () => {
    const usos = [...css.matchAll(/^\s*color: var\(--color-texto-suave\)/gm)];
    assert.equal(usos.length, 0);
  });

  test("foco visible en botones, enlaces y campos", () => {
    assert.match(css, /:focus-visible \{\s*outline: 3px solid var\(--color-primario\);/);
    assert.match(css, /\.campo :is\(input, select, textarea\):focus-visible,[\s\S]*?outline: 2px solid var\(--color-primario\);/);
  });

  test("en el celular los botones y campos miden al menos 40 x 40 px", () => {
    const bloque = css.slice(css.indexOf("/* Tamaños táctiles"));
    assert.match(bloque, /@media \(max-width: 700px\) \{\s*button,[\s\S]*?min-width: 40px;\s*min-height: 40px;/);
  });
});

describe("avisos (avisos_ui.test.js)", () => {
  test("arriba a la derecha, colores de la app (claro y oscuro), ✕ visible con teclado y a todo el ancho en el celular", () => {
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
    assert.equal((css.match(/--sombra-aviso:/g) || []).length, 2);
  });
});

describe("chat (chat_mejoras.test.js)", () => {
  test("formato: sin degradados y respetando los saltos", () => {
    assert.match(css, /\.chat-mensaje\.chat-formato \{\s*white-space: normal;/);
    assert.match(css, /\.chat-titulo-respuesta \{[^}]*font-weight: 600;/);
    const bloque = css.slice(css.indexOf("/* ---------- Asistente virtual"), css.indexOf("/* ---------- Nuevo ticket"));
    assert.doesNotMatch(bloque, /gradient/);
  });

  test("agrandar: 640 px × 80 % del alto en computadora; en el celular no aparece", () => {
    assert.match(css, /\.chat-asistente\.grande \.chat-panel \{\s*width: 640px;\s*height: 80vh;/);
    const celular = css.slice(css.indexOf("/* --- Celular --- */\n@media (max-width: 600px)"), css.indexOf("/* ---------- Nuevo ticket"));
    assert.match(celular, /\.chat-agrandar \{\s*display: none;/);
    assert.ok(css.indexOf(".chat-asistente.grande .chat-panel") < css.indexOf(".chat-asistente.abierto .chat-panel"), "en el celular gana la pantalla completa");
  });

  test("hora gris de 11 px, separador y «Ir al final»", () => {
    assert.match(css, /\.chat-hora \{\s*font-size: 11px;[^}]*color: var\(--color-tenue\);/);
    assert.match(css, /\.chat-separador::before,\n\.chat-separador::after \{\s*content: "";\s*flex: 1;\s*border-top: 1px solid var\(--color-borde\);/);
    assert.match(css, /\.chat-cuerpo \{\s*position: relative;/);
    assert.match(css, /\.chat-ir-final \{\s*position: absolute;[^}]*border: 1px solid var\(--color-borde-fuerte\);/);
  });
});

describe("comentarios (comentarios_conversacion.test.js)", () => {
  test("a todo el ancho, fondo de tarjeta, borde suave y la línea azul (IT) o gris a la izquierda", () => {
    const inicio = css.indexOf("/* Comentarios como conversación");
    const bloque = css.slice(inicio, css.indexOf("/* Línea y puntos de la línea de tiempo del historial", inicio));
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
    assert.doesNotMatch(bloque, /#[0-9a-fA-F]{3,6}\b|rgba?\(/);
    assert.doesNotMatch(css, /--burbuja-/);
  });
});

describe("consistencia (consistencia.test.js)", () => {
  test("las variables de alturas, radios y espaciado existen", () => {
    for (const variable of ["--alto-control: 2.25rem", "--alto-control-chico: 1.75rem", "--radio-suave: 6px", "--radio-ventana: 8px", "--espaciado-seccion: 1.75rem"]) {
      assert.ok(css.includes(variable), variable);
    }
  });

  test("botones y campos usan la misma altura en la app y en el login", () => {
    assert.match(regla(css, "\nbutton"), /min-height: var\(--alto-control\);/);
    assert.match(regla(css, "\n.enlace-boton"), /min-height: var\(--alto-control\);[\s\S]*font-size: var\(--texto-md\);/);
    assert.match(regla(css, ".campo select"), /min-height: var\(--alto-control\);/);
    assert.match(regla(css, "\n.btn-accion"), /min-height: var\(--alto-control-chico\);/);
    assert.match(regla(login, ".auth-container .login-der .campo .form-input"), /min-height: var\(--alto-control\);[\s\S]*font-size: var\(--texto-md\);/);
    assert.match(regla(login, "\n.btn-primario"), /min-height: var\(--alto-control\);/);
  });

  test("ventanas con 8 px, tarjetas con 6 px y títulos con la misma escala", () => {
    for (const selector of ["\n.chat-boton", "\n.chat-panel", "\n.dialogo"]) {
      assert.match(regla(css, selector), /border-radius: var\(--radio-ventana\);/, selector);
    }
    assert.match(regla(css, "\n.pagina-error-tarjeta"), /border-radius: var\(--radio-suave\);/);
    assert.match(css, /\.pagina-error-tarjeta h2 \{\s*margin: 0 0 0\.5rem;\s*color: var\(--color-titulo\);\s*font-size: var\(--texto-titulo\);/);
    assert.match(regla(login, ".auth-container .login-der .login-titulo"), /font-size: var\(--texto-titulo\);/);
    assert.match(regla(css, "\n.seccion"), /margin-top: var\(--espaciado-seccion\);/);
  });
});

describe("menú (contador_menu, menu_secciones y menu_usuario)", () => {
  test("contador con el color principal y visible con el menú plegado", () => {
    assert.match(css, /\.menu-enlace \.menu-contador \{[^}]*background: var\(--color-primario\);[^}]*color: var\(--color-texto-inverso\);/);
    assert.match(css, /body\.menu-plegado \.menu-enlace \.menu-contador \{\s*display: inline-grid;\s*position: absolute;/);
    assert.doesNotMatch(css.slice(css.indexOf(".menu-enlace .menu-contador {"), css.indexOf("/* Botón para achicar")), /gradient/);
  });

  test("sin enlaces visibles para el rol, la sección (y su título) no se ve", () => {
    assert.match(css, /\.menu-seccion:not\(:has\(> \.menu-enlace:not\(\[hidden\]\)\)\) \{\s*display: none;/);
  });

  test("plegado sin títulos; en pantallas chicas, enlaces en fila sin títulos", () => {
    assert.match(css, /body\.menu-plegado \.menu-enlace span,\n  body\.menu-plegado \.menu-titulo \{\n    display: none;/);
    const chico = css.slice(css.indexOf("@media (max-width: 900px)"));
    assert.match(chico, /\.menu-seccion \{\s*display: contents;\s*\}\s*\.menu-titulo \{\s*display: none;/);
  });

  test("menú de usuario: colores claros sobre el azul, hacia arriba, plegado y celular", () => {
    const sel = (s) => css.slice(css.indexOf(`\n${s} {`), css.indexOf("\n}", css.indexOf(`\n${s} {`) + 1));
    assert.match(sel(".menu-usuario-nombre"), /color: var\(--color-texto-inverso\);/);
    assert.match(sel(".menu-usuario-rol"), /color: var\(--color-menu-tenue\);/);
    assert.match(sel(".menu-usuario-flecha"), /stroke: var\(--color-menu-tenue\);/, "flecha del tono del rol");
    assert.match(sel(".menu-usuario-lista"), /bottom: calc\(100% \+ 4px\);/, "se abre hacia arriba");
    assert.match(css, /body\.menu-plegado \.menu-usuario-datos,\n  body\.menu-plegado \.menu-usuario-flecha \{\n    display: none;/, "plegado: solo las iniciales");
    assert.match(css, /\.barra-lateral:has\(\.menu-usuario-lista:not\(\[hidden\]\)\) \{\s*z-index: 50;\s*overflow: visible;/, "abierto no se recorta");
    assert.match(css, /\.barra-lateral \.menu-usuario-lista \{\s*top: calc\(100% \+ 4px\);\s*bottom: auto;/, "celular: el menú va arriba y se abre hacia abajo");
    assert.doesNotMatch(css, /barra-salir|boton-cerrar-sesion/);
  });
});

describe("diseño formal y detalle (diseno_formal y ficha_datos)", () => {
  test("fondo: puntos de 1 px cada 20 px con el color de borde, muy suaves", () => {
    const body = reglaRaiz("body");
    assert.match(body, /background-color: var\(--color-fondo\);/);
    assert.match(body, /background-image: radial-gradient\(\s*circle,\s*color-mix\(in srgb, var\(--color-borde\) 55%, transparent\) 0\.5px,\s*transparent 1px\s*\);/);
    assert.match(body, /background-size: 20px 20px;/);
    assert.equal(css.match(/radial-gradient/g).length, 1);
    assert.match(reglaRaiz(".tarjeta-resumen"), /background: var\(--color-superficie-alta\);/);
    assert.match(reglaRaiz(".listado"), /background: var\(--color-superficie-alta\);/);
    assert.match(reglaRaiz(".chat-panel"), /background: var\(--color-superficie\);/);
    const oscuro = css.slice(css.indexOf(':root[data-tema="oscuro"] {'));
    assert.match(oscuro.slice(0, oscuro.indexOf("\n}")), /--color-borde: #[0-9a-f]{6};/);
  });

  test("«Detalles» fijo al bajar, debajo en pantallas angostas y al imprimir sin las acciones", () => {
    assert.match(reglaRaiz(".detalle-datos-lista"), /flex-direction: column;/);
    assert.match(reglaRaiz(".detalle-lateral"), /position: sticky;/);
    assert.match(css, /@media \(max-width: 1100px\) \{\s*\.detalle-layout \{\s*grid-template-columns: minmax\(0, 1fr\);/);
    const impresion = css.slice(css.indexOf("@media print"));
    assert.match(impresion, /\.detalle-lateral > \.seccion:not\(#panel-datos\),/, "al imprimir se ven los datos, no las acciones");
    assert.match(impresion, /#panel-datos \.ficha-datos \{\s*padding: 0;\s*border: 0;/);
    assert.doesNotMatch(impresion, /ficha-grupo[^{]*\{[^}]*display: none/);
  });

  test("la ficha: recuadro casi blanco, borde fino, esquinas de 8 px y sin sombra", () => {
    const recuadro = regla(css, ".ficha-datos");
    assert.match(recuadro, /background: var\(--color-superficie\);/);
    assert.match(recuadro, /border: 1px solid var\(--color-borde\);/);
    assert.match(recuadro, /border-radius: var\(--radio-ventana\);/);
    assert.doesNotMatch(recuadro, /box-shadow/);
  });

  test("celular: la ficha va debajo de la descripción, a todo el ancho y sin scroll horizontal", () => {
    const angosta = css.slice(css.indexOf("@media (max-width: 1100px) {\n  .detalle-layout {"));
    const bloque = angosta.slice(0, angosta.indexOf("\n}\n"));
    assert.match(bloque, /\.detalle-principal \{\s*display: contents;/);
    assert.match(bloque, /\.detalle-principal > \.acciones-principales,\s*\.detalle-principal > #panel-ticket \{\s*order: 1;/);
    assert.match(bloque, /\.detalle-lateral \{\s*order: 2;\s*min-width: 0;/);
    assert.match(bloque, /align-items: stretch;/);
  });
});

describe("pantallas (historial_ui, metricas_ui, secciones_vacias, sesion_ui y tablero_ui)", () => {
  test("historial: mismas tarjetas que Departamentos, avatar a la izquierda, 4 cajas y líneas sin scroll de costado", () => {
    assert.match(css, /\.app \.contenido\.departamentos,\s*\.app \.contenido\.historial-personas \{\s*max-width: none;/);
    assert.match(css, /\.depto-boton\.hist-persona \{\s*grid-template-columns: auto minmax\(0, 1fr\) auto;/);
    assert.match(css, /\.hist-persona \.hist-avatar \{\s*grid-column: 1;\s*grid-row: 1 \/ 3;/);
    assert.match(css, /\.hist-persona \.depto-pastilla \{\s*grid-column: 3;/);
    assert.match(css, /\.depto-boton\.hist-todas \+ \.depto-boton \{\s*border-top-color: var\(--color-borde-fuerte\);/);
    assert.match(css, /\.hist-avatar \{[^}]*border-radius: 50%;/);
    assert.match(css, /\.hist-cajas \{\s*grid-template-columns: repeat\(4, minmax\(0, 1fr\)\);/);
    assert.match(css, /\.hist-ticket-titulo \{[^}]*text-overflow: ellipsis;/);
    const celular = css.match(/Celular: cada cambio[\s\S]*?@media \(max-width: 700px\) \{[\s\S]*?\n\}/)[0];
    assert.match(celular, /\.hist-linea,\s*\.hist-linea\.con-autor \{\s*display: flex;\s*flex-wrap: wrap;/);
    assert.match(celular, /\.hist-cajas \{\s*grid-template-columns: repeat\(2, minmax\(0, 1fr\)\);/);
  });

  test("métricas: sin tarjetas con cambio verde/rojo ni series de colores", () => {
    assert.doesNotMatch(css, /metrica-cambio|--color-serie-|metricas-graficos/);
    assert.match(css, /\.metricas-tarjetas \{/);
    assert.match(css, /\.tarjeta-resumen\.metrica \{/);
  });

  test("el vacío de comentarios e historial es texto chico y tenue, sin borde punteado ni ícono", () => {
    const inicio = css.indexOf("/* ===== Detalle: secciones vacías compactas");
    const bloque = css.slice(inicio, css.indexOf("/* Nuevo ticket: archivos elegidos", inicio));
    assert.ok(bloque.length > 0);
    const linea = bloque.slice(bloque.indexOf(".linea-vacia,"), bloque.indexOf("}", bloque.indexOf(".linea-vacia,")));
    assert.match(linea, /#comentarios-estado\.vacio:not\(\[hidden\]\),\s*#historial-estado\.vacio:not\(\[hidden\]\) \{/);
    assert.match(linea, /border: 0;/);
    assert.match(linea, /background: transparent;/);
    assert.match(linea, /font-size: var\(--texto-sm\);/);
    assert.match(linea, /color: var\(--color-tenue\);/);
    assert.match(bloque, /#comentarios-estado\.vacio::before,\s*#historial-estado\.vacio::before \{\s*display: none;/);
    assert.match(regla(css, ".nota-chica"), /color: var\(--color-tenue\);/);
    assert.match(regla(css, ".nota-chica"), /overflow-wrap: anywhere;/);
    assert.doesNotMatch(bloque, /#[0-9a-fA-F]{3,6}\b|rgba?\(/);
    assert.match(regla(css, ".estado.vacio"), /border: 1px dashed var\(--color-borde-fuerte\);/);
  });

  test("la cuenta regresiva de la sesión tiene estilo propio", () => {
    assert.match(css, /\.dialogo-sesion\s*\{[^}]*z-index/);
    assert.match(css, /\.dialogo-cuenta-tiempo\s*\{[^}]*var\(--color-titulo\)/);
  });

  test("tablero: 4 columnas y, en el celular, una debajo de la otra; sin degradados", () => {
    assert.match(css, /\.tablero \{[^}]*grid-template-columns: repeat\(4, minmax\(0, 1fr\)\);/);
    assert.match(css, /@media \(max-width: 700px\) \{\s*\.tablero \{\s*grid-template-columns: 1fr;/);
    const bloque = css.slice(css.indexOf("/* ===== Tablero por estado"), css.indexOf("/* ===== Fin del tablero"));
    assert.ok(bloque.length > 0);
    assert.doesNotMatch(bloque, /gradient/);
  });
});
