/* Direcciones de la app React (sin «.html») y su equivalente en el frontend
   actual. Mientras dura la migración la app vive bajo BASE ("/react/"); en
   la etapa final pasa a la raíz y el servidor redirige (301) las
   direcciones viejas con REDIRECCIONES_VIEJAS (ver rutaNuevaDe). */

export const BASE = import.meta.env.BASE_URL || "/";
/* basename del router: "/react" (sin la barra final), o "" en la raíz. */
export const BASENAME = BASE.replace(/\/$/, "");

export const RUTAS = {
  inicio: "/",
  login: "/login",
  ticket: "/tickets/:id",
  crear: "/crear",
  metricas: "/metricas",
  departamentos: "/departamentos",
  historial: "/historial",
  usuarios: "/usuarios",
  cuenta: "/cuenta",
  ayuda: "/ayuda",
  sinPermiso: "/sin-permiso",
};

export const rutaTicket = (id) => `/tickets/${encodeURIComponent(id)}`;

/* Dirección vieja → nueva. La etapa final las usa para los 301. */
export const REDIRECCIONES_VIEJAS = {
  "/index.html": "/",
  "/login.html": "/login",
  "/crear.html": "/crear",
  "/metricas.html": "/metricas",
  "/departamentos.html": "/departamentos",
  "/historial.html": "/historial",
  "/usuarios.html": "/usuarios",
  "/cuenta.html": "/cuenta",
  "/ayuda.html": "/ayuda",
  "/sin-permiso.html": "/sin-permiso",
};

/* «/detalle.html?id=5» → «/tickets/5»; null si no es una dirección vieja. */
export function rutaNuevaDe(ruta, busqueda = "") {
  const params = new URLSearchParams(busqueda);
  if (ruta === "/detalle.html") {
    const id = params.get("id");
    return /^\d+$/.test(id || "") ? rutaTicket(id) : "/";
  }
  const nueva = REDIRECCIONES_VIEJAS[ruta];
  if (!nueva) return null;
  const resto = params.toString();
  return resto ? `${nueva}?${resto}` : nueva;
}

/* Pantallas todavía no migradas: la ruta nueva abre la página actual. */
export const PAGINAS_ACTUALES = {
  crear: "/crear.html",
  metricas: "/metricas.html",
  departamentos: "/departamentos.html",
  historial: "/historial.html",
  usuarios: "/usuarios.html",
  cuenta: "/cuenta.html",
  ayuda: "/ayuda.html",
};

export const paginaActualDeTicket = (id) => `/detalle.html?id=${encodeURIComponent(id)}`;

/* Dirección completa del navegador para una ruta de la app («/login» →
   «/react/login»). */
export const conBase = (ruta) => `${BASENAME}${ruta}`;
