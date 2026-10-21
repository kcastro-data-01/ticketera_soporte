// Ayuda — Ticketera de Soporte
// El contenido es estático. Los temas son <details> que se abren y cierran;
// los enlaces del índice (y una dirección con #tema) abren el tema elegido.

function abrirTema(id, doc = document) {
  if (!id) return null;
  const tema = doc.getElementById(id);
  if (!tema || !tema.classList || !tema.classList.contains("ayuda-tema")) return null;
  tema.open = true;
  if (typeof tema.scrollIntoView === "function") tema.scrollIntoView({ block: "start" });
  return tema;
}

function iniciarAyuda(doc = document) {
  doc.querySelectorAll(".ayuda-indice a").forEach((enlace) => {
    enlace.addEventListener("click", () => abrirTema(enlace.getAttribute("href").slice(1), doc));
  });
  const actual = (window.location.hash || "").slice(1);
  if (actual) abrirTema(actual, doc);
}

if (typeof document !== "undefined" && typeof document.addEventListener === "function") {
  document.addEventListener("DOMContentLoaded", () => iniciarAyuda());
}
