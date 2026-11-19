import { useEffect } from "react";

/* Clase del <body> de cada pantalla («app», «pagina-login»,
   «pagina-error»), como en las páginas actuales. */
export function useClaseBody(clase) {
  useEffect(() => {
    const clases = clase.split(/\s+/).filter(Boolean);
    clases.forEach((c) => document.body.classList.add(c));
    return () => clases.forEach((c) => document.body.classList.remove(c));
  }, [clase]);
}

/* Título de la pestaña. */
export function useTitulo(titulo) {
  useEffect(() => {
    document.title = `${titulo} · American Data Networks`;
  }, [titulo]);
}
