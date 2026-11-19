/* Mi cuenta (port de frontend/cuenta.html): los datos de la sesión. La
   contraseña es la de la cuenta de Microsoft: no se cambia aquí. */
import Cabecera from "../componentes/Cabecera.jsx";
import { useTitulo } from "../componentes/claseBody.js";
import { useSesion } from "../contexto/SesionContext.jsx";

function Dato({ etiqueta, id, valor }) {
  return (
    <div className="campo-dato">
      <span className="etiqueta">{etiqueta}</span>
      <span id={id}>{valor || "—"}</span>
    </div>
  );
}

export default function Cuenta() {
  useTitulo("Mi cuenta");
  const { user } = useSesion();
  return (
    <>
      <Cabecera claseTitulo="" titulo="Mi cuenta" subtitulo="Sus datos" />
      <main className="contenido">
        <section className="seccion" aria-label="Mis datos">
          <h2>Mis datos</h2>
          <div className="filtros detalle">
            <Dato etiqueta="Nombre" id="cuenta-nombre" valor={user && user.name} />
            <Dato etiqueta="Correo" id="cuenta-email" valor={user && user.email} />
            <Dato etiqueta="Rol" id="cuenta-rol" valor={user && user.role} />
          </div>
        </section>
      </main>
    </>
  );
}
