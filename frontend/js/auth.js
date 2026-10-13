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
