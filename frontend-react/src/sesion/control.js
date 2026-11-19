/* Sesión deslizante y aviso por inactividad (port de frontend/js/sesion.js).

   - Actividad: mover el mouse, escribir, hacer clic, tocar o la rueda, en
     cualquier pestaña de la ticketera (se anota en localStorage).
   - Con actividad, la sesión se renueva (POST /api/auth/renovar) cada
     RENOVAR_CADA_MS como mucho. El servidor nunca pasa del máximo de horas
     (claim «max»): después hay que volver a entrar.
   - Con INACTIVIDAD_MS sin actividad aparece «¿Sigue ahí?» con una cuenta
     regresiva de AVISO_MS; al llegar a cero se cierra en todas las pestañas.
   - ?sesion_rapida=1 (solo en localhost): 2 min y 30 s; ?sesion_rapida=0 vuelve.

   La lógica no toca el DOM: avisa con ``alCambiar({ abierta, restanteMs })``
   y el componente AvisoSesion dibuja la ventana. */
import {
  SESION_ACTIVIDAD_KEY, SESION_CIERRE_KEY, SESION_INICIO_KEY, TOKEN_KEY,
  cerrarSesion, datosToken, estadoToken, getToken, guardarAlmacen, leerAlmacen,
  navegador, recordarInicio, saveSession,
} from "./almacen.js";
import { conBase } from "../rutas.js";

export const SESION_TIEMPOS = {
  INACTIVIDAD_MS: 30 * 60 * 1000,
  AVISO_MS: 2 * 60 * 1000,
  RENOVAR_CADA_MS: 5 * 60 * 1000,
};
export const SESION_TIEMPOS_RAPIDOS = {
  INACTIVIDAD_MS: 2 * 60 * 1000,
  AVISO_MS: 30 * 1000,
  RENOVAR_CADA_MS: 20 * 1000,
};
const SESION_RAPIDA_KEY = "sesion_rapida";
const SESION_RENOVANDO_KEY = "sesion_renovando";
const SESION_ANOTAR_CADA_MS = 1000;
const SESION_REVISAR_CADA_MS = 1000;
const SESION_EVENTOS = ["mousemove", "mousedown", "keydown", "touchstart", "wheel"];

export function esLocal(loc = window.location) {
  const host = loc && loc.hostname ? loc.hostname : "";
  return host === "localhost" || host === "127.0.0.1" || host === "[::1]";
}

export function tiemposDeSesion(loc = window.location) {
  if (!esLocal(loc)) return SESION_TIEMPOS;
  const pedido = new URLSearchParams(loc.search || "").get(SESION_RAPIDA_KEY);
  if (pedido === "1") guardarAlmacen(SESION_RAPIDA_KEY, "1");
  if (pedido === "0") guardarAlmacen(SESION_RAPIDA_KEY, null);
  return leerAlmacen(SESION_RAPIDA_KEY) === "1" ? SESION_TIEMPOS_RAPIDOS : SESION_TIEMPOS;
}

function ultimaActividad() {
  const valor = Number(leerAlmacen(SESION_ACTIVIDAD_KEY));
  return Number.isFinite(valor) && valor > 0 ? valor : 0;
}

/* «1:05» */
export function formatoCuenta(ms) {
  const total = Math.max(0, Math.ceil(ms / 1000));
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

export function iniciarSesion({ doc = document, win = window, reloj = () => Date.now(), tiempos = null, alCambiar = () => {} } = {}) {
  if (!getToken()) return null;
  const t = tiempos || tiemposDeSesion(win.location);
  let abierta = false;
  let anotada = 0;
  let renovando = false;
  let renovadaCon = 0;
  let intervalo = null;
  let detenida = false;

  const avisar = (restanteMs = 0) => alCambiar({ abierta, restanteMs });

  const anotarActividad = (forzar = false) => {
    const ahora = reloj();
    if (!forzar && ahora - anotada < SESION_ANOTAR_CADA_MS) return;
    anotada = ahora;
    guardarAlmacen(SESION_ACTIVIDAD_KEY, ahora);
  };

  /* Con el aviso abierto, mover el mouse no cuenta: hay que elegir un botón. */
  const alActuar = () => {
    if (!abierta) anotarActividad();
  };

  const cerrar = (motivo) => {
    if (detenida) return;
    detener();
    cerrarSesion(motivo);
  };

  const renovar = async ({ forzar = false } = {}) => {
    if (renovando || !getToken()) return false;
    const ahora = reloj();
    const otra = Number(leerAlmacen(SESION_RENOVANDO_KEY)) || 0;
    if (!forzar && ahora - otra < 10000) return false; /* la renueva otra pestaña */
    renovando = true;
    guardarAlmacen(SESION_RENOVANDO_KEY, ahora);
    renovadaCon = ultimaActividad();
    try {
      const response = await fetch("/api/auth/renovar", {
        method: "POST",
        headers: { Authorization: `Bearer ${getToken()}` },
      });
      if (response.status === 401) {
        cerrar(estadoToken(getToken(), reloj()) === "maxima" ? "maxima" : "vencida");
        return false;
      }
      if (!response.ok) return false;
      const datos = await response.json();
      if (datos && datos.access_token && getToken()) saveSession(datos.access_token);
      return true;
    } catch {
      return false;
    } finally {
      renovando = false;
      guardarAlmacen(SESION_RENOVANDO_KEY, null);
    }
  };

  const quitarVentana = () => {
    if (!abierta) return;
    abierta = false;
    avisar();
  };

  const seguir = async () => {
    anotarActividad(true);
    quitarVentana();
    await renovar({ forzar: true });
  };

  const revisar = () => {
    if (detenida) return;
    const token = getToken();
    if (!token) {
      /* Otra pestaña cerró la sesión: esta va al login también. */
      detener();
      if (leerAlmacen(SESION_CIERRE_KEY) === "vencida") cerrarSesion("vencida");
      else navegador.ir(conBase("/login"));
      return;
    }
    const ahora = reloj();
    const estado = estadoToken(token, ahora);
    if (estado === "maxima") return cerrar("maxima");
    const inactivo = ahora - (ultimaActividad() || ahora);
    if (inactivo >= t.INACTIVIDAD_MS + t.AVISO_MS) return cerrar("inactividad");
    if (estado === "vencida") return cerrar("vencida");
    if (inactivo >= t.INACTIVIDAD_MS) {
      abierta = true;
      avisar(t.INACTIVIDAD_MS + t.AVISO_MS - inactivo);
      return;
    }
    quitarVentana();
    const datos = datosToken(token);
    if (!datos || !Number.isFinite(datos.iat)) return;
    if (ultimaActividad() > renovadaCon && ahora - datos.iat * 1000 >= t.RENOVAR_CADA_MS) renovar();
  };

  const alAlmacenar = (event) => {
    if (!event || event.key === TOKEN_KEY || event.key === SESION_ACTIVIDAD_KEY) revisar();
  };
  const alVolver = (event) => {
    if (event && event.persisted) {
      anotarActividad(true);
      revisar();
    }
  };
  const alVer = () => {
    if (doc.visibilityState === "visible") revisar();
  };

  function detener() {
    detenida = true;
    if (intervalo !== null) win.clearInterval(intervalo);
    SESION_EVENTOS.forEach((tipo) => doc.removeEventListener(tipo, alActuar, true));
    win.removeEventListener("storage", alAlmacenar);
    win.removeEventListener("pageshow", alVolver);
    doc.removeEventListener("visibilitychange", alVer);
    if (abierta) {
      abierta = false;
      avisar();
    }
  }

  if (!leerAlmacen(SESION_INICIO_KEY)) recordarInicio();
  anotarActividad(true);
  SESION_EVENTOS.forEach((tipo) => doc.addEventListener(tipo, alActuar, { capture: true, passive: true }));
  win.addEventListener("storage", alAlmacenar);
  win.addEventListener("pageshow", alVolver);
  doc.addEventListener("visibilitychange", alVer);
  intervalo = win.setInterval(revisar, SESION_REVISAR_CADA_MS);
  revisar();
  return { revisar, seguir, detener, renovar, cerrar, tiempos: t, abierta: () => abierta };
}
