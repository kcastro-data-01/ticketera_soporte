import BotonTema from "./BotonTema.jsx";

/* Barra del título de cada pantalla; el botón de tema va siempre al final
   de «.cabecera-acciones», como en el frontend actual. */
export default function Cabecera({ className = "", titulo, subtitulo, idTitulo, idSubtitulo, centro = null, acciones = null }) {
  return (
    <header className={`cabecera ${className}`.trim()}>
      <div className="cabecera-titulo">
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
