import { useEffect } from "react";
import { navegador } from "../sesion/almacen.js";
import { PAGINAS_ACTUALES } from "../rutas.js";

/* Pantallas que todavía no están en React: la ruta nueva abre la página
   actual (se migran en las próximas etapas). */
export default function Heredada({ pagina }) {
  const destino = PAGINAS_ACTUALES[pagina];
  useEffect(() => {
    if (destino) navegador.reemplazar(destino);
  }, [destino]);
  return <p className="estado" role="status">Abriendo…</p>;
}
