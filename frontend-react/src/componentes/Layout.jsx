import { useEffect, useState } from "react";
import { Link, NavLink } from "react-router-dom";
import logo from "../images/logo-circular.jpg";
import { useSesion } from "../contexto/SesionContext.jsx";
import { useSesionDeslizante } from "../sesion/useSesionDeslizante.js";
import Asistente from "../chat/Asistente.jsx";
import AvisoSesion from "./AvisoSesion.jsx";
import MenuUsuario from "./MenuUsuario.jsx";
import { useClaseBody } from "./claseBody.js";
import { contarParaMenu } from "./contador.js";
import {
  IconoAyuda, IconoDepartamentos, IconoHistorial, IconoMetricas, IconoNuevo, IconoPlegar,
  IconoTickets, IconoUsuarios,
} from "./iconos.jsx";

/* Secciones del menú lateral; ``permiso``: solo los roles que lo tienen. */
const SECCIONES = [
  {
    id: "menu-gestion", titulo: "Gestión", enlaces: [
      { a: "/", texto: "Tickets", Icono: IconoTickets, contador: true },
      { a: "/crear", texto: "Nuevo ticket", Icono: IconoNuevo },
      { a: "/historial", texto: "Historial", Icono: IconoHistorial, permiso: "historial_global" },
    ],
  },
  {
    id: "menu-administracion", titulo: "Administración", enlaces: [
      { a: "/metricas", texto: "Métricas", Icono: IconoMetricas, permiso: "metricas" },
      { a: "/departamentos", texto: "Departamentos", Icono: IconoDepartamentos, permiso: "departamentos" },
      { a: "/usuarios", texto: "Usuarios", Icono: IconoUsuarios, permiso: "usuarios" },
    ],
  },
  {
    id: "menu-soporte", titulo: "Soporte", enlaces: [
      { a: "/ayuda", texto: "Ayuda", Icono: IconoAyuda },
    ],
  },
];

const MENU_PLEGADO_KEY = "menu_plegado";

function menuPlegadoGuardado() {
  try {
    return localStorage.getItem(MENU_PLEGADO_KEY) === "1";
  } catch {
    return false;
  }
}

function useContador(user) {
  const [conteo, setConteo] = useState(null);
  useEffect(() => {
    let vigente = true;
    setConteo(null);
    contarParaMenu(user)
      .then((c) => { if (vigente) setConteo(c); })
      .catch(() => { /* Sin contador: el menú funciona igual. */ });
    return () => { vigente = false; };
  }, [user && user.id, user && user.role]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!conteo || !Number.isFinite(conteo.cantidad) || conteo.cantidad <= 0) return null;
  return conteo;
}

/* Barra lateral + contenido de la pantalla + pie, y el control de la sesión. */
export default function Layout({ children }) {
  const { user, puede } = useSesion();
  const [plegado, setPlegado] = useState(menuPlegadoGuardado);
  const conteo = useContador(user);
  const sesion = useSesionDeslizante(true);
  useClaseBody("app");

  useEffect(() => {
    document.body.classList.toggle("menu-plegado", plegado);
  }, [plegado]);
  useEffect(() => () => document.body.classList.remove("menu-plegado", "menu-animando"), []);

  const plegar = () => {
    const nuevo = !plegado;
    document.body.classList.add("menu-animando");
    try {
      localStorage.setItem(MENU_PLEGADO_KEY, nuevo ? "1" : "0");
    } catch {
      /* Solo para esta página. */
    }
    setPlegado(nuevo);
  };
  const etiquetaPlegar = plegado ? "Expandir menú" : "Achicar menú";

  return (
    <>
      <aside className="barra-lateral">
        <Link to="/" className="marca">
          <img src={logo} alt="" className="marca-logo" />
          <span className="marca-texto">
            <span className="marca-nombre">American Data Networks</span>
            <span className="marca-sub">Sistema de tickets</span>
          </span>
        </Link>
        <button type="button" className="boton-plegar" aria-label={etiquetaPlegar}
          aria-expanded={String(!plegado)} title={etiquetaPlegar} onClick={plegar}>
          <IconoPlegar />
        </button>
        <nav className="menu" aria-label="Menú principal">
          {SECCIONES.map((seccion) => {
            const visibles = seccion.enlaces.filter((e) => !e.permiso || puede(e.permiso));
            return (
              <div className="menu-seccion" role="group" aria-labelledby={seccion.id} key={seccion.id}>
                <p className="menu-titulo" id={seccion.id}>{seccion.titulo}</p>
                {visibles.map(({ a, texto, Icono, contador }) => {
                  const conContador = contador && conteo;
                  return (
                    <NavLink key={a} to={a} end
                      className={({ isActive }) => `menu-enlace${isActive ? " activo" : ""}`}
                      title={conContador ? `${conteo.cantidad} ${conteo.texto}` : (plegado ? texto : undefined)}
                      aria-label={conContador ? `Tickets: ${conteo.cantidad} ${conteo.texto}` : undefined}>
                      <Icono /><span>{texto}</span>
                      {conContador && (
                        <span className="menu-contador" aria-hidden="true">
                          {conteo.cantidad > 99 ? "99+" : String(conteo.cantidad)}
                        </span>
                      )}
                    </NavLink>
                  );
                })}
              </div>
            );
          })}
        </nav>
        <MenuUsuario />
      </aside>

      <div className="app-principal">
        {children}
        <footer className="pie">© 2026 American Data Networks · Sistema de Tickets</footer>
      </div>

      <Asistente />
      <AvisoSesion abierta={sesion.abierta} restanteMs={sesion.restanteMs}
        onSeguir={sesion.seguir} onSalir={sesion.salir} />
    </>
  );
}
