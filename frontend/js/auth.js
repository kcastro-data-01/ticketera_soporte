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
  editar: ["Administrador", "Supervisor", "Soporte"],
  asignar: ["Administrador", "Supervisor", "Soporte"],
  cambiar_estado: ["Administrador", "Supervisor", "Soporte", "Técnico"],
  historial_global: ["Administrador", "Supervisor", "Soporte", "Técnico"],
  usuarios: ["Administrador"],
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

if (typeof document !== "undefined" && typeof document.addEventListener === "function") {
  document.addEventListener("DOMContentLoaded", () => aplicarPermisos());
}
