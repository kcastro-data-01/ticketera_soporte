import { Link } from "react-router-dom";
import logo from "../images/logo-circular.jpg";
import { useClaseBody, useTitulo } from "../componentes/claseBody.js";

function PaginaError({ titulo, codigo, icono, mensaje }) {
  useClaseBody("pagina-error");
  useTitulo(titulo);
  return (
    <main className="pagina-error-tarjeta">
      <div className="pagina-error-marca">
        <img src={logo} alt="" />
        <span>American Data Networks</span>
      </div>
      <span className={`pagina-error-icono ${icono}`} aria-hidden="true" />
      <p className="pagina-error-codigo">{codigo}</p>
      <h1>{titulo}</h1>
      <p className="pagina-error-mensaje">{mensaje}</p>
      <div className="acciones">
        <Link to="/" className="enlace-boton">Volver al inicio</Link>
      </div>
    </main>
  );
}

export function SinPermiso() {
  return (
    <PaginaError titulo="Acceso restringido" codigo="Sin permiso" icono="icono-candado"
      mensaje="Su rol no tiene permiso para ver esta página. Si necesita acceso, comuníquese con el administrador." />
  );
}

export function NoEncontrada() {
  return (
    <PaginaError titulo="Página no encontrada" codigo="Error 404" icono="icono-buscar"
      mensaje="La dirección que buscó no existe o fue movida. Verifique el enlace o regrese al inicio." />
  );
}
