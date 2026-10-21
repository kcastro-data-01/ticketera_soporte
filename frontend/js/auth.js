/* Fase 2 — Helper de autenticación para el frontend.
   Provee funciones para gestionar el token JWT en localStorage y
   redirigir a login cuando no hay sesión activa. */

const TOKEN_KEY = "access_token";
const USER_KEY = "user";

function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

function getUser() {
  const raw = localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function saveSession(token, user) {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

function clearSession() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
  try {
    sessionStorage.removeItem("asistente_chat");
  } catch {
    /* Sin sessionStorage no hay conversación que borrar. */
  }
}

function isAuthenticated() {
  return getToken() !== null;
}

/* Redirige a login.html si no hay token. Devuelve true si hay sesión. */
function requireAuth() {
  if (!isAuthenticated()) {
    window.location.href = "login.html";
    return false;
  }
  return true;
}

/* Cierra sesión: limpia localStorage y redirige a login. */
function logout() {
  clearSession();
  window.location.href = "login.html";
}

/* Fetch con Authorization header incluido automáticamente.
   Si la API responde 401, limpia la sesión y redirige a login. */
async function fetchWithAuth(url, options = {}) {
  const token = getToken();
  const headers = { ...options.headers };

  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  if (options.body && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }

  const response = await fetch(url, { ...options, headers });

  if (response.status === 401 && token) {
    clearSession();
    window.location.href = "login.html";
    throw new Error("Sesión expirada. Inicia sesión de nuevo.");
  }

  return response;
}

/* Tabla de permisos por rol (espejo de backend/routers/auth.py).
   El servidor es quien realmente bloquea; aquí solo se ocultan los
   botones y enlaces que el rol no puede usar. */
const PERMISOS = {
  editar: ["Administrador", "Supervisor"],
  asignar: ["Administrador", "Supervisor"],
  cambiar_estado: ["Administrador", "Supervisor", "Técnico"],
  historial_global: ["Administrador", "Supervisor", "Técnico"],
  usuarios: ["Administrador"],
  eliminar: ["Administrador"],
  explicar_ia: ["Administrador", "Supervisor", "Técnico"],
  metricas: ["Administrador", "Supervisor"],
};

/* true si el usuario de la sesión tiene el permiso indicado. */
function puede(permiso) {
  const user = getUser();
  const roles = PERMISOS[permiso] || [];
  return Boolean(user && roles.includes(user.role));
}

/* Oculta cada elemento con data-permiso="..." que el rol no puede usar. */
function aplicarPermisos(root = document) {
  if (!root || typeof root.querySelectorAll !== "function") return;
  root.querySelectorAll("[data-permiso]").forEach((element) => {
    if (!puede(element.dataset.permiso)) element.hidden = true;
  });
}

/* Para páginas restringidas: sin sesión va a login y sin permiso al
   listado. Devuelve true si se puede mostrar la página. */
function requirePermiso(permiso) {
  if (!requireAuth()) return false;
  if (!puede(permiso)) {
    window.location.href = "index.html";
    return false;
  }
  return true;
}

/* Muestra en el menú lateral el nombre, el rol y las iniciales del
   usuario de la sesión y conecta el botón «Cerrar sesión». */
function pintarUsuario(doc = document) {
  if (!doc || typeof doc.getElementById !== "function") return;
  const user = getUser();
  const nombre = doc.getElementById("usuario-nombre");
  const rol = doc.getElementById("usuario-rol");
  const iniciales = doc.getElementById("usuario-iniciales");
  if (user && nombre) nombre.textContent = user.name || user.email || "";
  if (user && rol) rol.textContent = user.role || "";
  if (user && iniciales) iniciales.textContent = inicialesDe(user.name || user.email || "?");
  const salir = doc.getElementById("btn-logout");
  if (salir && typeof salir.addEventListener === "function") {
    salir.addEventListener("click", logout);
  }
}

/* Iniciales de un nombre: «Carlos Solano» → «CS». */
function inicialesDe(nombre) {
  return String(nombre || "")
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((parte) => parte.charAt(0).toUpperCase())
    .join("");
}

/* Tono del avatar (0 a 5): sale del nombre, así la misma persona tiene
   siempre el mismo color en todas las pantallas. */
const AVATAR_TONOS = 6;
function tonoAvatar(nombre) {
  const base = String(nombre || "").trim().toLowerCase();
  let hash = 0;
  for (let i = 0; i < base.length; i += 1) hash = (hash * 31 + base.charCodeAt(i)) >>> 0;
  return hash % AVATAR_TONOS;
}

/* Escribe el nombre en el elemento y le agrega el círculo con las
   iniciales (lo dibuja el CSS con data-iniciales). Sin persona real
   («—», «Usuario #5») queda solo el texto. */
function pintarPersona(el, nombre) {
  if (!el) return;
  const texto = nombre || "—";
  el.textContent = texto;
  const clase = String(el.className || "").replace(/\s*\bcon-avatar\b|\s*\btono-avatar-\d\b/g, "").trim();
  const real = texto !== "—" && !/^Usuario #/.test(texto);
  el.className = real ? `${clase} con-avatar tono-avatar-${tonoAvatar(texto)}`.trim() : clase;
  if (el.dataset) {
    if (real) el.dataset.iniciales = inicialesDe(texto);
    else delete el.dataset.iniciales;
  }
}

/* Clase CSS de la etiqueta de color para un estado o una prioridad
   («En proceso» → "badge estado-proceso", «Crítica» → "badge prioridad-critica"). */
const CLASES_BADGE = {
  Nuevo: "estado-nuevo",
  "En proceso": "estado-proceso",
  Resuelto: "estado-resuelto",
  Cerrado: "estado-cerrado",
  Baja: "prioridad-baja",
  Media: "prioridad-media",
  Alta: "prioridad-alta",
  Crítica: "prioridad-critica",
};

function claseBadge(valor) {
  const clase = CLASES_BADGE[valor];
  return clase ? `badge ${clase}` : "badge";
}

/* ---------- Historial legible ----------
   Traduce un registro de historial (acción, campo, valores) a una acción
   y un detalle en español. Los registros antiguos de asignación guardaban
   ids de usuario: se muestran como «Usuario #id». */
const CAMPOS_HISTORIAL = {
  title: "Título",
  description: "Descripción",
  category: "Categoría",
  priority: "Prioridad",
  state: "Estado",
};

function recortar(texto, maximo = 120) {
  const limpio = String(texto).replace(/\s+/g, " ").trim();
  return limpio.length > maximo ? `${limpio.slice(0, maximo - 1)}…` : limpio;
}

function nombreAsignacion(valor) {
  if (valor === null || valor === undefined || valor === "") return "Sin asignar";
  return /^\d+$/.test(String(valor)) ? `Usuario #${valor}` : String(valor);
}

function describirHistorial(entry) {
  const antes = entry.old_value;
  const despues = entry.new_value;
  switch (entry.action) {
    case "created":
      return {
        accion: "Creó el ticket",
        detalle: despues ? `Asignado automáticamente a ${despues}` : "—",
      };
    case "updated": {
      const campo = CAMPOS_HISTORIAL[entry.field] || entry.field || "Dato";
      return {
        accion: "Editó el ticket",
        detalle: `${campo}: «${recortar(antes ?? "")}» → «${recortar(despues ?? "")}»`,
      };
    }
    case "assigned":
      return {
        accion: despues ? "Asignó el ticket" : "Quitó la asignación",
        detalle: `${nombreAsignacion(antes)} → ${nombreAsignacion(despues)}`,
      };
    case "Cambio de estado":
    case "state_changed":
      return { accion: "Cambió el estado", detalle: `${antes ?? "—"} → ${despues ?? "—"}` };
    case "commented":
      return { accion: "Comentó", detalle: despues ? `«${recortar(despues)}»` : "—" };
    default: {
      const hayValores = (antes ?? null) !== null || (despues ?? null) !== null;
      return {
        accion: entry.action || "—",
        detalle: hayValores ? `${antes ?? "—"} → ${despues ?? "—"}` : "—",
      };
    }
  }
}

/* ---------- Menú lateral plegable ----------
   Un botón con flecha deja el menú solo con los íconos; la preferencia se
   recuerda en este navegador (localStorage). */
const MENU_PLEGADO_KEY = "menu_plegado";

function menuPlegadoGuardado() {
  try {
    return localStorage.getItem(MENU_PLEGADO_KEY) === "1";
  } catch {
    return false;
  }
}

function iniciarMenuPlegable(doc = document) {
  const barra = doc.querySelector(".barra-lateral");
  if (!barra || barra.querySelector(".boton-plegar")) return null;
  const boton = doc.createElement("button");
  boton.type = "button";
  boton.className = "boton-plegar";
  boton.innerHTML =
    '<svg class="icono" viewBox="0 0 24 24" aria-hidden="true"><path d="M15 6l-6 6 6 6"/></svg>';
  const enlaces = Array.from(barra.querySelectorAll(".menu-enlace"));

  const aplicar = (plegado) => {
    doc.body.classList.toggle("menu-plegado", plegado);
    const etiqueta = plegado ? "Expandir menú" : "Achicar menú";
    boton.setAttribute("aria-label", etiqueta);
    boton.setAttribute("aria-expanded", String(!plegado));
    boton.title = etiqueta;
    /* Plegado solo se ven los íconos: el nombre queda como tooltip. */
    enlaces.forEach((enlace) => {
      if (plegado) enlace.title = enlace.textContent.trim();
      else enlace.removeAttribute("title");
    });
  };

  boton.addEventListener("click", () => {
    const plegado = !doc.body.classList.contains("menu-plegado");
    doc.body.classList.add("menu-animando");
    try {
      localStorage.setItem(MENU_PLEGADO_KEY, plegado ? "1" : "0");
    } catch {
      /* Sin almacenamiento solo vale para esta página. */
    }
    aplicar(plegado);
  });

  const marca = barra.querySelector(".marca");
  if (marca && marca.nextSibling) barra.insertBefore(boton, marca.nextSibling);
  else barra.appendChild(boton);
  aplicar(menuPlegadoGuardado());
  return boton;
}

/* ---------- Modo oscuro ----------
   <html data-tema="oscuro"> activa las variables oscuras de estilos.css.
   La preferencia se guarda en localStorage; cada página la aplica desde el
   <head> (sin destello claro) y aquí se agrega el botón de luna/sol. */
const TEMA_KEY = "tema";
const ICONO_LUNA =
  '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>';
const ICONO_SOL =
  '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4"/>' +
  '<path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>';

function temaGuardado() {
  try {
    return localStorage.getItem(TEMA_KEY) === "oscuro" ? "oscuro" : "claro";
  } catch {
    return "claro";
  }
}

function aplicarTema(tema, doc = document) {
  if (tema === "oscuro") doc.documentElement.setAttribute("data-tema", "oscuro");
  else doc.documentElement.removeAttribute("data-tema");
}

function iniciarBotonTema(doc = document) {
  if (doc.querySelector(".boton-tema")) return null;
  const boton = doc.createElement("button");
  boton.type = "button";
  boton.className = "boton-tema";

  const pintar = () => {
    const oscuro = doc.documentElement.getAttribute("data-tema") === "oscuro";
    /* Muestra el ícono del modo al que se cambia. */
    boton.innerHTML = oscuro ? ICONO_SOL : ICONO_LUNA;
    const etiqueta = oscuro ? "Activar modo claro" : "Activar modo oscuro";
    boton.setAttribute("aria-label", etiqueta);
    boton.setAttribute("aria-pressed", String(oscuro));
    boton.title = etiqueta;
  };

  boton.addEventListener("click", () => {
    const nuevo = doc.documentElement.getAttribute("data-tema") === "oscuro" ? "claro" : "oscuro";
    try {
      localStorage.setItem(TEMA_KEY, nuevo);
    } catch {
      /* Sin almacenamiento solo vale para esta página. */
    }
    aplicarTema(nuevo, doc);
    pintar();
    /* Las gráficas de métricas leen los colores al dibujarse. */
    if (typeof doc.dispatchEvent === "function" && typeof CustomEvent === "function") {
      doc.dispatchEvent(new CustomEvent("tema-cambiado", { detail: { tema: nuevo } }));
    }
  });

  const cabecera = doc.querySelector(".cabecera");
  if (cabecera) {
    let acciones = cabecera.querySelector(".cabecera-acciones");
    if (!acciones) {
      acciones = doc.createElement("div");
      acciones.className = "cabecera-acciones";
      cabecera.appendChild(acciones);
    }
    acciones.appendChild(boton);
  } else if (doc.body) {
    doc.body.appendChild(boton);
  }
  pintar();
  return boton;
}

/* Avisos flotantes abajo a la izquierda: confirman una acción
   («Comentario agregado») y se van solos a los 3 segundos. Los errores
   usan el mismo aviso en rojo suave. */
const AVISO_MS = 3000;
const AVISO_PENDIENTE_KEY = "aviso_pendiente";

function mostrarAviso(mensaje, tipo = "exito", doc = typeof document !== "undefined" ? document : null) {
  if (!mensaje || !doc || !doc.body || typeof doc.createElement !== "function") return null;
  let zona = doc.getElementById("avisos");
  if (!zona) {
    zona = doc.createElement("div");
    zona.id = "avisos";
    zona.className = "avisos";
    zona.setAttribute("role", "status");
    zona.setAttribute("aria-live", "polite");
    doc.body.appendChild(zona);
  }
  const aviso = doc.createElement("div");
  aviso.className = `aviso ${tipo === "error" ? "error" : "exito"}`;
  aviso.textContent = mensaje;
  zona.appendChild(aviso);
  setTimeout(() => {
    aviso.classList.add("saliendo");
    setTimeout(() => aviso.remove(), 250);
  }, AVISO_MS);
  return aviso;
}

/* Para un aviso que se tiene que ver en la página siguiente (por
   ejemplo, después de eliminar un ticket se vuelve al listado). */
function avisoPendiente(mensaje, tipo = "exito") {
  try {
    sessionStorage.setItem(AVISO_PENDIENTE_KEY, JSON.stringify({ mensaje, tipo }));
  } catch (error) {
    /* Sin sessionStorage el aviso simplemente no se muestra. */
  }
}

function mostrarAvisoPendiente() {
  try {
    const guardado = JSON.parse(sessionStorage.getItem(AVISO_PENDIENTE_KEY) || "null");
    sessionStorage.removeItem(AVISO_PENDIENTE_KEY);
    if (guardado && guardado.mensaje) mostrarAviso(guardado.mensaje, guardado.tipo);
  } catch (error) {
    /* Nada que mostrar. */
  }
}

if (typeof document !== "undefined" && document.documentElement) {
  aplicarTema(temaGuardado());
}

if (typeof document !== "undefined" && typeof document.addEventListener === "function") {
  document.addEventListener("DOMContentLoaded", () => {
    aplicarPermisos();
    pintarUsuario();
    iniciarMenuPlegable();
    iniciarBotonTema();
    mostrarAvisoPendiente();
  });
}
