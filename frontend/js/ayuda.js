// Ayuda — Ticketera de Soporte
// El contenido es estático. Los temas son <details> que se abren y cierran;
// los botones del índice (y una dirección con #tema) bajan hasta el tema
// elegido y lo abren si está cerrado. Sin código inline (CSP).

function sinMovimiento() {
  try {
    return typeof window !== "undefined" && typeof window.matchMedia === "function"
      && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  } catch (error) {
    return false;
  }
}

function abrirTema(id, doc = document, { suave = false } = {}) {
  if (!id) return null;
  const tema = doc.getElementById(id);
  if (!tema || !tema.classList || !tema.classList.contains("ayuda-tema")) return null;
  if (!tema.open) tema.open = true;
  if (typeof tema.scrollIntoView === "function") {
    tema.scrollIntoView({ block: "start", behavior: suave && !sinMovimiento() ? "smooth" : "auto" });
  }
  return tema;
}

/* Clic en un botón del índice: baja hasta el tema, lo abre y deja el #tema
   en la dirección (sin el salto brusco del enlace). */
function irATema(evento, enlace, doc = document) {
  const id = (enlace.getAttribute("href") || "").replace(/^#/, "");
  const tema = abrirTema(id, doc, { suave: true });
  if (!tema) return null;
  if (evento && typeof evento.preventDefault === "function") evento.preventDefault();
  try {
    if (window.history && typeof window.history.replaceState === "function") {
      window.history.replaceState(null, "", `#${id}`);
    }
  } catch (error) {
    // Sin historial (pruebas o navegadores viejos): solo se abre el tema.
  }
  return tema;
}

function iniciarAyuda(doc = document) {
  doc.querySelectorAll(".ayuda-indice a").forEach((enlace) => {
    enlace.addEventListener("click", (evento) => irATema(evento, enlace, doc));
  });
  const actual = (window.location.hash || "").slice(1);
  if (actual) abrirTema(actual, doc);
}

if (typeof document !== "undefined" && typeof document.addEventListener === "function") {
  document.addEventListener("DOMContentLoaded", () => iniciarAyuda());
}
