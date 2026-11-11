/* Sesión deslizante y aviso por inactividad (todas las páginas con sesión;
   se carga después de auth.js).

   - Actividad: mover el mouse, escribir, hacer clic, tocar la pantalla o la
     rueda del mouse, en cualquier pestaña de la ticketera. Se anota en
     localStorage (SESION_ACTIVIDAD_KEY), así cuenta para todas las pestañas.
   - Mientras hay actividad, la sesión se renueva sola (POST /api/auth/renovar
     con el token vigente) cada RENOVAR_CADA_MS como mucho. El servidor nunca
     la alarga más allá del máximo de horas desde el inicio de sesión (claim
     «max» del token): después hay que volver a entrar.
   - Con INACTIVIDAD_MS sin actividad aparece «¿Sigue ahí?» con una cuenta
     regresiva de AVISO_MS. «Seguir conectado» renueva y vuelve a contar (y
     cierra el aviso en las demás pestañas); «Cerrar sesión» o llegar a cero
     cierra la sesión en todas.
   - Para probar en local sin esperar: abra cualquier página con
     ?sesion_rapida=1 (2 min de inactividad y 30 s de aviso; solo en
     localhost) y ?sesion_rapida=0 para volver a lo normal. */

const SESION_TIEMPOS = {
  INACTIVIDAD_MS: 30 * 60 * 1000,
  AVISO_MS: 2 * 60 * 1000,
  RENOVAR_CADA_MS: 5 * 60 * 1000,
};
/* Solo en localhost con ?sesion_rapida=1 (se recuerda en este navegador). */
const SESION_TIEMPOS_RAPIDOS = {
  INACTIVIDAD_MS: 2 * 60 * 1000,
  AVISO_MS: 30 * 1000,
  RENOVAR_CADA_MS: 20 * 1000,
};
const SESION_RAPIDA_KEY = "sesion_rapida";
const SESION_RENOVANDO_KEY = "sesion_renovando";
/* Cada cuánto se anota la actividad (no en cada movimiento del mouse). */
const SESION_ANOTAR_CADA_MS = 1000;
const SESION_REVISAR_CADA_MS = 1000;
const SESION_EVENTOS = ["mousemove", "mousedown", "keydown", "touchstart", "wheel"];

function esLocal(loc = typeof window !== "undefined" ? window.location : null) {
  const host = loc && loc.hostname ? loc.hostname : "";
  return host === "localhost" || host === "127.0.0.1" || host === "[::1]";
}

/* Lee ?sesion_rapida=1/0 (solo en localhost) y devuelve los tiempos a usar. */
function tiemposDeSesion(loc = typeof window !== "undefined" ? window.location : null) {
  if (!esLocal(loc)) return SESION_TIEMPOS;
  const pedido = loc && typeof loc.search === "string" ? new URLSearchParams(loc.search).get(SESION_RAPIDA_KEY) : null;
  if (pedido === "1") guardarAlmacen(SESION_RAPIDA_KEY, "1");
  if (pedido === "0") guardarAlmacen(SESION_RAPIDA_KEY, null);
  return leerAlmacen(SESION_RAPIDA_KEY) === "1" ? SESION_TIEMPOS_RAPIDOS : SESION_TIEMPOS;
}

function ultimaActividad() {
  const valor = Number(leerAlmacen(SESION_ACTIVIDAD_KEY));
  return Number.isFinite(valor) && valor > 0 ? valor : 0;
}

/* «1:05» */
function formatoCuenta(ms) {
  const total = Math.max(0, Math.ceil(ms / 1000));
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

/* Arranca el control de la sesión en esta pestaña. Devuelve un objeto con
   lo necesario para las pruebas (revisar, seguir, detener). */
function iniciarSesion({ doc = document, win = window, reloj = () => Date.now(), tiempos = null } = {}) {
  if (!doc || !win || !getToken()) return null;
  const t = tiempos || tiemposDeSesion(win.location);
  let ventana = null;
  let cuenta = null;
  let anotada = 0;
  let renovando = false;
  let renovadaCon = 0; /* actividad que ya se usó para renovar */
  let intervalo = null;
  let detenida = false;

  const anotarActividad = (forzar = false) => {
    const ahora = reloj();
    if (!forzar && ahora - anotada < SESION_ANOTAR_CADA_MS) return;
    anotada = ahora;
    guardarAlmacen(SESION_ACTIVIDAD_KEY, ahora);
  };

  /* Con el aviso abierto, mover el mouse no cuenta: hay que elegir un botón. */
  const alActuar = () => {
    if (!ventana) anotarActividad();
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
      if (!response.ok) return false; /* se intenta en la próxima revisión */
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

  const cerrar = (motivo) => {
    if (detenida) return;
    detener();
    cerrarSesion(motivo);
  };

  const quitarVentana = () => {
    if (!ventana) return;
    doc.removeEventListener("keydown", teclas, true);
    ventana.remove();
    ventana = null;
    cuenta = null;
  };

  const seguir = async () => {
    anotarActividad(true);
    quitarVentana();
    await renovar({ forzar: true });
  };

  let botones = [];
  function teclas(event) {
    if (event.key === "Tab" && botones.length) {
      event.preventDefault();
      const i = botones.indexOf(doc.activeElement);
      const paso = event.shiftKey ? -1 : 1;
      botones[(i + paso + botones.length) % botones.length].focus();
    } else if (event.key === "Escape") {
      event.preventDefault(); /* hay que elegir una opción */
    }
  }

  const mostrarVentana = () => {
    if (ventana || typeof doc.createElement !== "function" || !doc.body) return;
    const nodo = (tag, clase, texto) => {
      const el = doc.createElement(tag);
      if (clase) el.className = clase;
      if (texto !== undefined) el.textContent = texto;
      return el;
    };
    const fondo = nodo("div", "dialogo-fondo dialogo-sesion");
    const caja = nodo("div", "dialogo");
    caja.setAttribute("role", "alertdialog");
    caja.setAttribute("aria-modal", "true");
    caja.setAttribute("aria-labelledby", "sesion-titulo");
    caja.setAttribute("aria-describedby", "sesion-mensaje");
    const h = nodo("h2", "dialogo-titulo", "¿Sigue ahí?");
    h.id = "sesion-titulo";
    const p = nodo("p", "dialogo-mensaje", "Su sesión se cerrará por inactividad. ¿Desea seguir conectado?");
    p.id = "sesion-mensaje";
    const linea = nodo("p", "dialogo-cuenta", "La sesión se cerrará en ");
    cuenta = nodo("strong", "dialogo-cuenta-tiempo", "");
    cuenta.setAttribute("aria-hidden", "true");
    linea.appendChild(cuenta);
    const acciones = nodo("div", "dialogo-acciones");
    const salir = nodo("button", "secundario", "Cerrar sesión");
    salir.type = "button";
    const quedarse = nodo("button", "", "Seguir conectado");
    quedarse.type = "button";
    acciones.append(salir, quedarse);
    caja.append(h, p, linea, acciones);
    fondo.appendChild(caja);
    botones = [salir, quedarse];
    salir.addEventListener("click", () => cerrar("manual"));
    quedarse.addEventListener("click", () => { seguir(); });
    doc.addEventListener("keydown", teclas, true);
    doc.body.appendChild(fondo);
    ventana = fondo;
    quedarse.focus();
  };

  /* Una revisión: cerrar, avisar, quitar el aviso o renovar. */
  const revisar = () => {
    if (detenida) return;
    const token = getToken();
    if (!token) {
      /* Otra pestaña cerró la sesión: esta va al login también. */
      detener();
      const motivo = leerAlmacen(SESION_CIERRE_KEY);
      if (motivo === "vencida") cerrarSesion("vencida");
      else win.location.href = "login.html";
      return;
    }
    const ahora = reloj();
    const estado = estadoToken(token, ahora);
    if (estado === "maxima") return cerrar("maxima");
    const inactivo = ahora - (ultimaActividad() || ahora);
    if (inactivo >= t.INACTIVIDAD_MS + t.AVISO_MS) return cerrar("inactividad");
    if (estado === "vencida") return cerrar("vencida");
    if (inactivo >= t.INACTIVIDAD_MS) {
      mostrarVentana();
      if (cuenta) cuenta.textContent = formatoCuenta(t.INACTIVIDAD_MS + t.AVISO_MS - inactivo);
      return;
    }
    quitarVentana(); /* hubo actividad aquí o en otra pestaña */
    const datos = datosToken(token);
    /* Sin poder leer el token no se sabe su edad: no se renueva (el servidor
       siempre los emite legibles). */
    if (!datos || !Number.isFinite(datos.iat)) return;
    if (ultimaActividad() > renovadaCon && ahora - datos.iat * 1000 >= t.RENOVAR_CADA_MS) renovar();
  };

  function detener() {
    detenida = true;
    if (intervalo !== null) win.clearInterval(intervalo);
    SESION_EVENTOS.forEach((tipo) => doc.removeEventListener(tipo, alActuar, true));
    quitarVentana();
  }

  /* Abrir o volver a la página cuenta como actividad. */
  if (!leerAlmacen(SESION_INICIO_KEY)) recordarInicio(); /* sesión de antes de este cambio */
  anotarActividad(true);
  SESION_EVENTOS.forEach((tipo) => doc.addEventListener(tipo, alActuar, { capture: true, passive: true }));
  if (typeof win.addEventListener === "function") {
    win.addEventListener("storage", (event) => {
      if (!event || event.key === TOKEN_KEY || event.key === SESION_ACTIVIDAD_KEY) revisar();
    });
    /* Volver desde otra página con «Atrás» (caché del navegador). */
    win.addEventListener("pageshow", (event) => {
      if (event && event.persisted) {
        if (!getToken()) {
          win.location.href = "login.html";
          return;
        }
        anotarActividad(true);
        revisar();
      }
    });
  }
  doc.addEventListener("visibilitychange", () => {
    if (doc.visibilityState === "visible") revisar();
  });
  intervalo = win.setInterval(revisar, SESION_REVISAR_CADA_MS);
  revisar();
  return { revisar, seguir, detener, renovar, tiempos: t, abierta: () => Boolean(ventana) };
}

if (typeof document !== "undefined" && typeof document.addEventListener === "function") {
  document.addEventListener("DOMContentLoaded", () => {
    /* guardia.js ya mandó al login si no había sesión. */
    if (getToken() && !estadoToken()) iniciarSesion();
  });
}
