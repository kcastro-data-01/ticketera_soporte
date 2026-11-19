import { useEffect, useState } from "react";

/* Debajo de 900 px las listas de pestañas son una fila horizontal: se avisa
   a los lectores de pantalla con aria-orientation. */
export function useOrientacion(media = "(max-width: 900px)") {
  const leer = () => (typeof window.matchMedia === "function" && window.matchMedia(media).matches ? "horizontal" : "vertical");
  const [orientacion, setOrientacion] = useState(leer);
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return undefined;
    const consulta = window.matchMedia(media);
    const aplicar = () => setOrientacion(consulta.matches ? "horizontal" : "vertical");
    if (typeof consulta.addEventListener === "function") consulta.addEventListener("change", aplicar);
    return () => { if (typeof consulta.removeEventListener === "function") consulta.removeEventListener("change", aplicar); };
  }, [media]);
  return orientacion;
}

/* Flechas, Inicio y Fin entre pestañas (activación automática): el índice
   de destino o null. */
export function destinoTeclado(key, indice, total, { verticalYHorizontal = true } = {}) {
  if (!verticalYHorizontal) return null;
  if (key === "ArrowDown" || key === "ArrowRight") return (indice + 1) % total;
  if (key === "ArrowUp" || key === "ArrowLeft") return (indice - 1 + total) % total;
  if (key === "Home") return 0;
  if (key === "End") return total - 1;
  return null;
}
