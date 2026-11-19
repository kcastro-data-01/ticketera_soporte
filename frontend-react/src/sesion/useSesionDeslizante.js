import { useEffect, useRef, useState } from "react";
import { iniciarSesion } from "./control.js";

/* Arranca el control de la sesión mientras el componente está montado.
   Devuelve el estado del aviso y las acciones de sus botones. */
export function useSesionDeslizante(activa = true, opciones = {}) {
  const [aviso, setAviso] = useState({ abierta: false, restanteMs: 0 });
  const control = useRef(null);

  useEffect(() => {
    if (!activa) return undefined;
    control.current = iniciarSesion({ ...opciones, alCambiar: setAviso });
    return () => {
      if (control.current) control.current.detener();
      control.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activa]);

  return {
    ...aviso,
    seguir: () => control.current && control.current.seguir(),
    salir: () => control.current && control.current.cerrar("manual"),
  };
}
