/* Token y sesión en localStorage (port de frontend/js/auth.js). Usa las
   mismas claves que la ticketera actual: la sesión se comparte entre las
   dos durante la migración. */
import { conBase } from "../rutas.js";

export const TOKEN_KEY = "access_token";
export const USER_KEY = "user";
/* Por qué se cerró la última sesión («vencida», «inactividad», «maxima» o
   «manual»), cuándo empezó (ms) y la última actividad en cualquier pestaña (ms). */
export const SESION_CIERRE_KEY = "sesion_cierre";
export const SESION_INICIO_KEY = "sesion_inicio";
export const SESION_ACTIVIDAD_KEY = "sesion_actividad";
export const VOLVER_KEY = "login_volver";

export function leerAlmacen(clave) {
  try {
    return localStorage.getItem(clave);
  } catch {
    return null;
  }
}

export function guardarAlmacen(clave, valor) {
  try {
    if (valor === null || valor === undefined) localStorage.removeItem(clave);
    else localStorage.setItem(clave, String(valor));
  } catch {
    /* Sin almacenamiento la sesión dura lo que la página. */
  }
}

export const getToken = () => leerAlmacen(TOKEN_KEY);

export function getUser() {
  const raw = leerAlmacen(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

/* Datos del token de la app (exp, ini, max en segundos), o null. Solo para
   saber cuándo vence: el servidor es quien valida. */
export function datosToken(token = getToken()) {
  if (!token || typeof token !== "string") return null;
  const partes = token.split(".");
  if (partes.length !== 3) return null;
  try {
    const base = partes[1].replace(/-/g, "+").replace(/_/g, "/");
    const relleno = base + "=".repeat((4 - (base.length % 4)) % 4);
    const bytes = Uint8Array.from(atob(relleno), (c) => c.charCodeAt(0));
    const datos = JSON.parse(new TextDecoder().decode(bytes));
    return datos && typeof datos === "object" ? datos : null;
  } catch {
    return null;
  }
}

/* «vencida», «maxima» (pasó el máximo de horas) o null si sigue vigente. */
export function estadoToken(token = getToken(), ahora = Date.now()) {
  const datos = datosToken(token);
  if (!datos) return null;
  if (Number.isFinite(datos.max) && ahora >= datos.max * 1000) return "maxima";
  if (Number.isFinite(datos.exp) && ahora >= datos.exp * 1000) return "vencida";
  return null;
}

export function recordarInicio(token = getToken()) {
  const datos = datosToken(token);
  const inicio = datos && (Number.isFinite(datos.ini) ? datos.ini : datos.iat);
  if (Number.isFinite(inicio)) guardarAlmacen(SESION_INICIO_KEY, inicio * 1000);
}

export function saveSession(token, user) {
  guardarAlmacen(TOKEN_KEY, token);
  if (user !== undefined) guardarAlmacen(USER_KEY, JSON.stringify(user));
  recordarInicio(token);
  guardarAlmacen(SESION_CIERRE_KEY, null);
}

export function clearSession() {
  guardarAlmacen(TOKEN_KEY, null);
  guardarAlmacen(USER_KEY, null);
  try {
    sessionStorage.removeItem("asistente_chat");
  } catch {
    /* Nada que borrar. */
  }
}

/* La ruta actual dentro de la app («/tickets/5?x=1»), para volver a ella. */
export function rutaActual(loc = window.location) {
  const base = conBase("");
  let ruta = loc.pathname || "/";
  if (base && ruta.startsWith(base)) ruta = ruta.slice(base.length) || "/";
  return `${ruta}${loc.search || ""}`;
}

/* Navegación de página completa (se reemplaza en las pruebas). */
export const navegador = {
  ir(url) {
    window.location.assign(url);
  },
  reemplazar(url) {
    window.location.replace(url);
  },
};

/* Cierra la sesión en todas las pestañas y va al login. Solo con «vencida»
   el login intenta volver a entrar en silencio y regresar a esta ruta. */
export function cerrarSesion(motivo = "manual") {
  clearSession();
  guardarAlmacen(SESION_CIERRE_KEY, motivo);
  if (motivo !== "vencida") {
    guardarAlmacen(SESION_INICIO_KEY, null);
    guardarAlmacen(SESION_ACTIVIDAD_KEY, null);
  }
  const volver = motivo === "vencida" ? rutaActual() : "";
  navegador.ir(conBase(volver && volver !== "/" ? `/login?volver=${encodeURIComponent(volver)}` : "/login"));
}

/* Solo rutas propias («/tickets/5»): nunca otro sitio ni el login. */
export function destinoSeguro(volver) {
  const texto = String(volver || "");
  if (!/^\/(?!\/)[A-Za-z0-9/_-]*(\?[A-Za-z0-9_=&%.-]*)?$/.test(texto)) return "/";
  if (/^\/login(\/|\?|$)/.test(texto)) return "/";
  return texto;
}
