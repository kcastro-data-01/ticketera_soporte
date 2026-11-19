import { useEffect, useRef } from "react";
import { formatoCuenta } from "../sesion/control.js";

/* «¿Sigue ahí?»: mismas clases y textos que sesion.js. Tab queda dentro de
   la ventana y Escape no la cierra (hay que elegir una opción). */
export default function AvisoSesion({ abierta, restanteMs, onSeguir, onSalir }) {
  const salir = useRef(null);
  const quedarse = useRef(null);

  useEffect(() => {
    if (!abierta) return undefined;
    if (quedarse.current) quedarse.current.focus();
    const teclas = (event) => {
      const botones = [salir.current, quedarse.current].filter(Boolean);
      if (event.key === "Tab" && botones.length) {
        event.preventDefault();
        const i = botones.indexOf(document.activeElement);
        const paso = event.shiftKey ? -1 : 1;
        botones[(i + paso + botones.length) % botones.length].focus();
      } else if (event.key === "Escape") {
        event.preventDefault();
      }
    };
    document.addEventListener("keydown", teclas, true);
    return () => document.removeEventListener("keydown", teclas, true);
  }, [abierta]);

  if (!abierta) return null;
  return (
    <div className="dialogo-fondo dialogo-sesion">
      <div className="dialogo" role="alertdialog" aria-modal="true"
        aria-labelledby="sesion-titulo" aria-describedby="sesion-mensaje">
        <h2 className="dialogo-titulo" id="sesion-titulo">¿Sigue ahí?</h2>
        <p className="dialogo-mensaje" id="sesion-mensaje">
          Su sesión se cerrará por inactividad. ¿Desea seguir conectado?
        </p>
        <p className="dialogo-cuenta">
          La sesión se cerrará en <strong className="dialogo-cuenta-tiempo" aria-hidden="true">{formatoCuenta(restanteMs)}</strong>
        </p>
        <div className="dialogo-acciones">
          <button type="button" className="secundario" ref={salir} onClick={onSalir}>Cerrar sesión</button>
          <button type="button" ref={quedarse} onClick={onSeguir}>Seguir conectado</button>
        </div>
      </div>
    </div>
  );
}
