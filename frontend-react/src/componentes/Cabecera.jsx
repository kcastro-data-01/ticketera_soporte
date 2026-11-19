import { Link } from "react-router-dom";
import { useSesion } from "../contexto/SesionContext.jsx";
import BotonTema from "./BotonTema.jsx";

/* Ruta de navegación: para el Solicitante el listado se llama «Mis solicitudes». */
export function Migas({ actual }) {
  const { user } = useSesion();
  return (
    <nav className="migas" aria-label="Ruta de navegación">
      <ol>
        <li><Link to="/" className="migas-inicio">{user && user.role === "Solicitante" ? "Mis solicitudes" : "Tickets"}</Link></li>
        <li aria-current="page" id="migas-actual">{actual}</li>
      </ol>
    </nav>
  );
}

/* Barra del título de cada pantalla; el botón de tema va siempre al final
   de «.cabecera-acciones», como en el frontend actual. ``claseTitulo``: el
   listado usa «cabecera-titulo»; detalle y crear, un <div> sin clase. */
export default function Cabecera({
  className = "", titulo, subtitulo, idTitulo, idSubtitulo, centro = null, acciones = null,
  claseTitulo = "cabecera-titulo", migas = null,
}) {
  return (
    <header className={`cabecera ${className}`.trim()}>
      <div className={claseTitulo || undefined}>
        {migas}
        <h1 id={idTitulo}>{titulo}</h1>
        {subtitulo && <p id={idSubtitulo}>{subtitulo}</p>}
      </div>
      {centro}
      <div className="cabecera-acciones">
        {acciones}
        <BotonTema />
      </div>
    </header>
  );
}
