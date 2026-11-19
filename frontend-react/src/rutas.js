/* Direcciones de la app (sin «.html»). La app vive en la raíz (BASE "/");
   las direcciones viejas (index.html, detalle.html?id=N, /react/…) las
   redirige el servidor con 301: backend/frontend_react.py → ruta_nueva(). */

export const BASE = import.meta.env.BASE_URL || "/";
/* basename del router: "" en la raíz (o la carpeta sin la barra final). */
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

/* Dirección completa del navegador para una ruta de la app (con la base). */
export const conBase = (ruta) => `${BASENAME}${ruta}`;
