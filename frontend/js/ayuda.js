// Ayuda — Ticketera de Soporte
// El contenido es estático. Los botones de «Temas» son pestañas
// (role="tablist"/"tab"/"tabpanel"): al tocar uno se muestra solo ese tema y
// los demás se ocultan. Al entrar se ve «Crear un ticket»; una dirección con
// #tema (ayuda.html#correo, enlaces de la app y del chat) abre ese, y al
// cambiar de pestaña la dirección se actualiza. Cada pestaña lleva su tema
// en data-tema («correo») y su panel se llama «tema-correo»: así el
// navegador no salta hasta el panel y las pestañas quedan a la vista.
// Sin código inline (CSP).

const TEMA_INICIAL = "crear";

function pestanasAyuda(doc = document) {
  if (!doc || typeof doc.querySelectorAll !== "function") return [];
  return Array.from(doc.querySelectorAll('.ayuda-temas [role="tab"]'));
}

/* El id del tema (#correo → "correo"), sin el numeral. */
function temaDeDireccion(hash) {
  try {
    return decodeURIComponent(String(hash || "").replace(/^#/, ""));
  } catch (error) {
    return "";
  }
}

function actualizarDireccion(id) {
  try {
    if (typeof window !== "undefined" && window.history && typeof window.history.replaceState === "function") {
      window.history.replaceState(null, "", `#${id}`);
    }
  } catch (error) {
    // Sin historial (pruebas o navegadores viejos): solo cambia la pestaña.
  }
}

/* Muestra el tema `id` (o «Crear un ticket» si no existe) y oculta los
   demás. Devuelve el id que quedó abierto, o null si no hay pestañas. */
function mostrarTema(id, doc = document, { enfocar = false, direccion = false } = {}) {
  const pestanas = pestanasAyuda(doc);
  if (!pestanas.length) return null;
  const tema = (pestana) => pestana.getAttribute("data-tema");
  const elegida = pestanas.find((p) => tema(p) === id)
    || pestanas.find((p) => tema(p) === TEMA_INICIAL)
    || pestanas[0];
  pestanas.forEach((pestana) => {
    const activa = pestana === elegida;
    pestana.setAttribute("aria-selected", String(activa));
    pestana.tabIndex = activa ? 0 : -1;
    const panel = doc.getElementById(pestana.getAttribute("aria-controls"));
    if (panel) panel.hidden = !activa;
  });
  if (enfocar && typeof elegida.focus === "function") elegida.focus();
  if (direccion) actualizarDireccion(tema(elegida));
  return tema(elegida);
}

/* Teclado (patrón de pestañas): flechas pasan a la vecina (en la
   cuadrícula, derecha/abajo = siguiente, izquierda/arriba = anterior),
   Inicio y Fin a la primera y la última. */
const PASOS_TECLADO = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 };

function teclaEnPestana(evento, pestana, doc = document) {
  const pestanas = pestanasAyuda(doc);
  const indice = pestanas.indexOf(pestana);
  if (indice < 0) return null;
  let destino;
  if (evento.key in PASOS_TECLADO) {
    destino = pestanas[(indice + PASOS_TECLADO[evento.key] + pestanas.length) % pestanas.length];
  } else if (evento.key === "Home") {
    destino = pestanas[0];
  } else if (evento.key === "End") {
    destino = pestanas[pestanas.length - 1];
  } else {
    return null;
  }
  if (typeof evento.preventDefault === "function") evento.preventDefault();
  return mostrarTema(destino.getAttribute("data-tema"), doc, { enfocar: true, direccion: true });
}

function iniciarAyuda(doc = document) {
  pestanasAyuda(doc).forEach((pestana) => {
    pestana.addEventListener("click", () =>
      mostrarTema(pestana.getAttribute("data-tema"), doc, { direccion: true }));
    pestana.addEventListener("keydown", (evento) => teclaEnPestana(evento, pestana, doc));
  });
  mostrarTema(temaDeDireccion(window.location.hash), doc);
  /* Un enlace a otro tema estando ya en la ayuda (o atrás/adelante). */
  if (typeof window.addEventListener === "function") {
    window.addEventListener("hashchange", () => mostrarTema(temaDeDireccion(window.location.hash), doc));
  }
}

if (typeof document !== "undefined" && typeof document.addEventListener === "function") {
  document.addEventListener("DOMContentLoaded", () => iniciarAyuda());
}
