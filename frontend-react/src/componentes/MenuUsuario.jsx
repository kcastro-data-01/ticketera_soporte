import { useEffect, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { useSesion } from "../contexto/SesionContext.jsx";
import { inicialesDe } from "../sesion/permisos.js";
import { IconoFlechaAbajo } from "./iconos.jsx";

/* Usuario abajo del todo en el menú lateral; al pulsarlo se abre (hacia
   arriba) «Mi cuenta» y «Cerrar sesión». */
export default function MenuUsuario() {
  const { user, salir } = useSesion();
  const [abierto, setAbierto] = useState(false);
  const menu = useRef(null);
  const boton = useRef(null);
  const { pathname } = useLocation();

  useEffect(() => {
    if (!abierto) return undefined;
    const clic = (event) => {
      if (menu.current && !menu.current.contains(event.target)) setAbierto(false);
    };
    const tecla = (event) => {
      if (event.key === "Escape") {
        setAbierto(false);
        if (boton.current) boton.current.focus();
      }
    };
    document.addEventListener("click", clic);
    document.addEventListener("keydown", tecla);
    return () => {
      document.removeEventListener("click", clic);
      document.removeEventListener("keydown", tecla);
    };
  }, [abierto]);

  if (!user) return null;
  const nombre = user.name || user.email || "";
  const enCuenta = pathname === "/cuenta";
  return (
    <div className="menu-usuario" ref={menu}>
      <button type="button" ref={boton} className={`menu-usuario-boton${enCuenta ? " activo" : ""}`}
        aria-haspopup="menu" aria-expanded={String(abierto)} aria-label={`Menú de ${nombre}`}
        onClick={(event) => { event.stopPropagation(); setAbierto((a) => !a); }}>
        <span className="usuario-avatar menu-usuario-avatar" aria-hidden="true">{inicialesDe(nombre || "?")}</span>
        <span className="menu-usuario-datos">
          <span className="menu-usuario-nombre">{nombre}</span>
          <span className="menu-usuario-rol">{user.role || ""}</span>
        </span>
        <IconoFlechaAbajo />
      </button>
      <div className="menu-usuario-lista" role="menu" hidden={!abierto}>
        <Link to="/cuenta" className="menu-usuario-opcion" role="menuitem"
          aria-current={enCuenta ? "page" : undefined}>Mi cuenta</Link>
        <button type="button" className="menu-usuario-opcion salir" role="menuitem" onClick={salir}>Cerrar sesión</button>
      </div>
    </div>
  );
}
