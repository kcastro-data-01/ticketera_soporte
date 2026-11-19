import { useEffect } from "react";
import { useParams } from "react-router-dom";
import { navegador } from "../sesion/almacen.js";
import { PAGINAS_ACTUALES, paginaActualDeTicket } from "../rutas.js";

/* Pantallas que todavía no están en React: la ruta nueva abre la página
   actual (se migran en las próximas etapas). */
export default function Heredada({ pagina }) {
  const { id } = useParams();
  const destino = pagina === "ticket" ? paginaActualDeTicket(id) : PAGINAS_ACTUALES[pagina];
  useEffect(() => {
    if (destino) navegador.reemplazar(destino);
  }, [destino]);
  return <p className="estado" role="status">Abriendo…</p>;
}
