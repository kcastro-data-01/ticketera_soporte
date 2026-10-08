/* Tarea 20.3 — Administración de usuarios desde la interfaz:
   GET /api/users (listado de usuarios activos) y POST /api/users (alta
   con nombre, correo y rol). JavaScript vanilla, sin frameworks ni
   librerías externas. */

const API_USERS_URL = "/api/users";

/* Roles válidos (espejo de backend.constants.UserRole). */
const ROLES_VALIDOS = ["Soporte", "Administrador"];

/* Mismo patrón de correo que backend.schemas (UserCreate). */
const EMAIL_PATTERN = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

let ocupado = false;

function getElements() {
  return {
    estadoUsuario: document.getElementById("estado-usuario"),
    formUsuario: document.getElementById("form-usuario"),
    nombre: document.getElementById("nombre"),
    email: document.getElementById("email"),
    rol: document.getElementById("rol"),
    crear: document.getElementById("crear"),
    usuariosEstado: document.getElementById("usuarios-estado"),
    tabla: document.getElementById("tabla-usuarios"),
    cuerpo: document.getElementById("cuerpo-usuarios"),
  };
}

function showStatus(message, type) {
  const elements = getElements();
  elements.estadoUsuario.textContent = message;
  elements.estadoUsuario.className = type ? `estado ${type}` : "estado";
  elements.estadoUsuario.hidden = false;
}

/* Validación en el cliente antes de hacer la petición. */
function validarUsuario() {
  const elements = getElements();
  const nombre = elements.nombre.value.trim();
  const email = elements.email.value.trim();
  if (!nombre) return "El nombre no puede estar vacío.";
  if (!email) return "El correo electrónico no puede estar vacío.";
  if (!EMAIL_PATTERN.test(email)) {
    return "El correo electrónico no tiene un formato válido.";
  }
  if (!ROLES_VALIDOS.includes(elements.rol.value)) {
    return "Selecciona un rol válido.";
  }
  return "";
}

/* Mapea la respuesta de error de la API a un mensaje legible (patrón T19):
   409 → detail del backend; 422 → errores de campo; resto → "Error de API". */
function mensajeDeError(response, payload) {
  if (response.status === 409) {
    if (payload && typeof payload.detail === "string") return payload.detail;
    return "Ese correo electrónico ya está registrado.";
  }
  if (response.status === 422) {
    if (payload && Array.isArray(payload.detail)) {
      const messages = payload.detail.map((error) => {
        const field = Array.isArray(error.loc)
          ? error.loc[error.loc.length - 1]
          : null;
        return field ? `${field}: ${error.msg}` : error.msg;
      });
      return messages.join(" | ");
    }
    return "La API rechazó los datos enviados. Revisa el formulario.";
  }
  if (payload && typeof payload.detail === "string") {
    return `Error de API (${response.status}): ${payload.detail}`;
  }
  return `Error de API (${response.status}).`;
}

function mostrarUsuariosEstado(message, type) {
  const elements = getElements();
  elements.usuariosEstado.textContent = message;
  elements.usuariosEstado.className = type ? `estado ${type}` : "estado";
  elements.usuariosEstado.hidden = false;
}

function ocultarUsuariosEstado() {
  const elements = getElements();
  elements.usuariosEstado.textContent = "";
  elements.usuariosEstado.hidden = true;
}

function appendCell(row, text) {
  const cell = document.createElement("td");
  cell.textContent = text;
  row.appendChild(cell);
}

/* Renderiza con textContent: los datos del backend nunca se interpretan
   como HTML. Todos los usuarios listados están activos (el filtro lo hace
   el backend), por eso la columna Estado lo indica con un badge. */
function renderUsers(users) {
  const elements = getElements();
  elements.cuerpo.replaceChildren();
  if (!Array.isArray(users) || users.length === 0) {
    elements.tabla.hidden = true;
    mostrarUsuariosEstado("No hay usuarios registrados.", "vacio");
    return;
  }
  users.forEach((user) => {
    const row = document.createElement("tr");
    appendCell(row, user.name);
    appendCell(row, user.email);
    appendCell(row, user.role);

    const stateCell = document.createElement("td");
    const badge = document.createElement("span");
    badge.className = "badge badge-activo";
    badge.textContent = "Activo";
    stateCell.appendChild(badge);
    row.appendChild(stateCell);

    elements.cuerpo.appendChild(row);
  });
  ocultarUsuariosEstado();
  elements.tabla.hidden = false;
}

async function cargarUsuarios() {
  const elements = getElements();
  elements.tabla.hidden = true;
  mostrarUsuariosEstado("Cargando usuarios...", "cargando");
  try {
    const response = await fetch(API_USERS_URL);
    const payload = await response.json().catch(() => null);
    if (!response.ok) {
      mostrarUsuariosEstado(mensajeDeError(response, payload), "error");
      return;
    }
    if (!Array.isArray(payload)) {
      mostrarUsuariosEstado("Respuesta inválida del servidor.", "error");
      return;
    }
    renderUsers(payload);
  } catch (error) {
    console.error("GET /api/users:", error);
    mostrarUsuariosEstado(
      "No se pudo conectar con el servidor. Comprueba que está en ejecución.",
      "error"
    );
  }
}

async function crearUsuario(event) {
  event.preventDefault();
  if (ocupado) return;

  const errorValidacion = validarUsuario();
  if (errorValidacion) {
    showStatus(errorValidacion, "error");
    return;
  }

  const elements = getElements();
  const payload = {
    name: elements.nombre.value.trim(),
    email: elements.email.value.trim(),
    role: elements.rol.value,
  };

  ocupado = true;
  elements.crear.disabled = true;
  try {
    const response = await fetch(API_USERS_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const body = response.ok ? null : await response.json().catch(() => null);
    if (!response.ok) {
      showStatus(mensajeDeError(response, body), "error");
      return;
    }

    elements.nombre.value = "";
    elements.email.value = "";
    elements.rol.value = "Soporte";
    showStatus("Usuario agregado correctamente.", "exito");
    /* El usuario nuevo aparece en la lista sin recargar la página. */
    await cargarUsuarios();
  } catch (error) {
    console.error("POST /api/users:", error);
    showStatus(
      "No se pudo conectar con el servidor. Comprueba que está en ejecución.",
      "error"
    );
  } finally {
    ocupado = false;
    elements.crear.disabled = false;
  }
}

async function init() {
  const elements = getElements();
  elements.formUsuario.addEventListener("submit", crearUsuario);
  await cargarUsuarios();
}

if (typeof document !== "undefined") {
  document.addEventListener("DOMContentLoaded", () => init());
}
