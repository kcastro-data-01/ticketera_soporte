/* Tarea 20.3 — Administración de usuarios desde la interfaz:
   GET /api/users (listado de usuarios activos) y POST /api/users (alta
   con nombre, correo y rol). JavaScript vanilla, sin frameworks ni
   librerías externas.
   Fase 2: usa fetchWithAuth para incluir el token JWT automáticamente. */

const API_USERS_URL = "/api/users";

/* Roles válidos (espejo de backend.constants.UserRole). */
const ROLES_VALIDOS = [
  "Técnico",
  "Administrador",
  "Supervisor",
  "Solicitante",
];

/* Mismo patrón de correo que backend.schemas (UserCreate). */
const EMAIL_PATTERN = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

/* Largo de contraseña aceptado (espejo de backend.schemas). */
const PASSWORD_MIN = 6;
const PASSWORD_MAX = 72;

/* Mensaje de error de una contraseña, o "" si es válida. */
function validarPassword(password) {
  if (password.length < PASSWORD_MIN) {
    return `La contraseña debe tener al menos ${PASSWORD_MIN} caracteres.`;
  }
  if (password.length > PASSWORD_MAX) {
    return `La contraseña debe tener como máximo ${PASSWORD_MAX} caracteres.`;
  }
  return "";
}

let ocupado = false;

/* --- Errores debajo de cada campo ---------------------------------------
   El mensaje se muestra debajo del campo al que corresponde (con
   aria-invalid); si no corresponde a ninguno, queda el aviso general. */
function campoDelError(mensaje, prefijo = "") {
  const texto = String(mensaje || "").toLowerCase();
  let campo = "";
  if (/nombre|^name/.test(texto)) campo = "nombre";
  else if (/correo|^email/.test(texto)) campo = "email";
  else if (/contraseña|^password/.test(texto)) campo = "password";
  else if (/\brol\b|^role/.test(texto)) campo = "rol";
  return campo ? `${prefijo}${campo}` : "";
}

function limpiarErroresCampo(prefijo = "") {
  ["nombre", "email", "password", "rol"].forEach((campo) => {
    const error = document.getElementById(`error-${prefijo}${campo}`);
    const control = document.getElementById(`${prefijo}${campo}`);
    if (error) {
      error.textContent = "";
      error.hidden = true;
    }
    if (control && typeof control.removeAttribute === "function") control.removeAttribute("aria-invalid");
  });
}

/* true si el mensaje quedó debajo de su campo. */
function mostrarErrorCampo(mensaje, prefijo = "") {
  const campo = campoDelError(mensaje, prefijo);
  const error = campo ? document.getElementById(`error-${campo}`) : null;
  if (!error) return false;
  error.textContent = mensaje;
  error.hidden = false;
  const control = document.getElementById(campo);
  if (control) {
    if (typeof control.setAttribute === "function") control.setAttribute("aria-invalid", "true");
    if (typeof control.focus === "function") control.focus();
  }
  return true;
}

function getElements() {
  return {
    estadoUsuario: document.getElementById("estado-usuario"),
    formUsuario: document.getElementById("form-usuario"),
    nombre: document.getElementById("nombre"),
    email: document.getElementById("email"),
    password: document.getElementById("password"),
    rol: document.getElementById("rol"),
    crear: document.getElementById("crear"),
    usuariosEstado: document.getElementById("usuarios-estado"),
    tabla: document.getElementById("tabla-usuarios"),
    cuerpo: document.getElementById("cuerpo-usuarios"),
    seccionEditar: document.getElementById("seccion-editar"),
    formEditar: document.getElementById("form-editar-usuario"),
    editarId: document.getElementById("editar-id"),
    editarNombre: document.getElementById("editar-nombre"),
    editarEmail: document.getElementById("editar-email"),
    editarPassword: document.getElementById("editar-password"),
    editarRol: document.getElementById("editar-rol"),
    guardarEdicion: document.getElementById("guardar-edicion"),
    cancelarEdicion: document.getElementById("cancelar-edicion"),
    estadoEdicion: document.getElementById("estado-edicion"),
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
  const errorPassword = validarPassword(elements.password ? elements.password.value : "");
  if (errorPassword) return errorPassword;
  if (!ROLES_VALIDOS.includes(elements.rol.value)) {
    return "Seleccione un rol válido.";
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
    return "El servidor rechazó los datos enviados. Revise el formulario.";
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

/* Color de la etiqueta de cada rol. */
const CLASES_ROL = {
  Administrador: "rol-administrador",
  Supervisor: "rol-supervisor",
  Técnico: "rol-tecnico",
  Solicitante: "rol-solicitante",
};

function claseRol(rol) {
  return CLASES_ROL[rol] || "rol-solicitante";
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
    /* Nombre con el círculo de iniciales y el rol como etiqueta. */
    const nameCell = document.createElement("td");
    pintarPersona(nameCell, user.name);
    row.appendChild(nameCell);
    appendCell(row, user.email);
    const roleCell = document.createElement("td");
    const roleBadge = document.createElement("span");
    roleBadge.className = `badge ${claseRol(user.role)}`;
    roleBadge.textContent = user.role;
    roleCell.appendChild(roleBadge);
    row.appendChild(roleCell);

    const activo = user.is_active !== false;
    const stateCell = document.createElement("td");
    const badge = document.createElement("span");
    badge.className = activo ? "badge badge-activo" : "badge badge-inactivo";
    badge.textContent = activo ? "Activo" : "Inactivo";
    stateCell.appendChild(badge);
    row.appendChild(stateCell);

    const actionsCell = document.createElement("td");
    actionsCell.className = "celda-acciones";
    const editBtn = document.createElement("button");
    editBtn.type = "button";
    editBtn.className = "btn-accion";
    editBtn.textContent = "Editar";
    editBtn.addEventListener("click", () => editarUsuario(user));
    actionsCell.appendChild(editBtn);

    /* Nadie se desactiva a sí mismo: el botón no aparece en su fila. */
    const sesion = getUser();
    if (!sesion || sesion.id !== user.id) {
      const toggleBtn = document.createElement("button");
      toggleBtn.type = "button";
      toggleBtn.className = activo ? "btn-accion secundario" : "btn-accion";
      toggleBtn.textContent = activo ? "Desactivar" : "Reactivar";
      toggleBtn.addEventListener("click", () => cambiarActivo(user, !activo));
      actionsCell.appendChild(toggleBtn);
    }
    row.appendChild(actionsCell);

    elements.cuerpo.appendChild(row);
  });
  ocultarUsuariosEstado();
  elements.tabla.hidden = false;
}

/* Desactiva o reactiva un usuario. Desactivado no puede iniciar sesión ni
   recibe tickets, pero conserva su historial. */
async function cambiarActivo(user, activar) {
  if (ocupado) return;
  if (
    !activar &&
    !(await confirmarAccion({
      titulo: "Desactivar usuario",
      mensaje: `¿Desactivar a ${user.name}? No podrá iniciar sesión ni recibir tickets.`,
      aceptar: "Desactivar",
      peligro: true,
    }))
  ) {
    return;
  }
  ocupado = true;
  try {
    const response = await fetchWithAuth(`${API_USERS_URL}/${user.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ is_active: activar }),
    });
    const body = response.ok ? null : await response.json().catch(() => null);
    if (!response.ok) {
      showStatus(mensajeDeError(response, body), "error");
      return;
    }
    showStatus(
      activar ? `${user.name} fue reactivado.` : `${user.name} fue desactivado.`,
      "exito"
    );
    ocupado = false;
    await cargarUsuarios();
  } catch (error) {
    console.error("PATCH /api/users (is_active):", error);
    showStatus(
      "No se pudo conectar con el servidor. Verifique que esté en funcionamiento.",
      "error"
    );
  } finally {
    ocupado = false;
  }
}

function mostrarEdicionEstado(message, type) {
  const elements = getElements();
  elements.estadoEdicion.textContent = message;
  elements.estadoEdicion.className = type ? `estado ${type}` : "estado";
  elements.estadoEdicion.hidden = false;
}

function ocultarEdicionEstado() {
  const elements = getElements();
  elements.estadoEdicion.textContent = "";
  elements.estadoEdicion.hidden = true;
}

function editarUsuario(user) {
  const elements = getElements();
  elements.editarId.value = user.id;
  elements.editarNombre.value = user.name;
  elements.editarEmail.value = user.email;
  elements.editarRol.value = user.role;
  limpiarErroresCampo("editar-");
  if (elements.editarPassword) elements.editarPassword.value = "";
  elements.seccionEditar.hidden = false;
  ocultarEdicionEstado();
  elements.seccionEditar.scrollIntoView({ behavior: "smooth" });
}

function cancelarEdicion() {
  const elements = getElements();
  elements.seccionEditar.hidden = true;
  ocultarEdicionEstado();
}

async function guardarEdicion(event) {
  event.preventDefault();
  if (ocupado) return;

  const elements = getElements();
  const userId = parseInt(elements.editarId.value, 10);
  const payload = {};

  const nombre = elements.editarNombre.value.trim();
  const email = elements.editarEmail.value.trim();
  const rol = elements.editarRol.value;

  if (nombre) payload.name = nombre;
  if (email) payload.email = email;
  if (rol) payload.role = rol;

  /* La contraseña solo se envía si se escribió una nueva. */
  limpiarErroresCampo("editar-");
  const nuevaPassword = elements.editarPassword ? elements.editarPassword.value : "";
  if (nuevaPassword) {
    const errorPassword = validarPassword(nuevaPassword);
    if (errorPassword) {
      avisarErrorEdicion(errorPassword);
      return;
    }
    payload.password = nuevaPassword;
  }

  if (Object.keys(payload).length === 0) {
    mostrarEdicionEstado("No hay cambios para guardar.", "error");
    return;
  }

  ocupado = true;
  elements.guardarEdicion.disabled = true;
  try {
    const response = await fetchWithAuth(`${API_USERS_URL}/${userId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const body = response.ok ? null : await response.json().catch(() => null);
    if (!response.ok) {
      avisarErrorEdicion(mensajeDeError(response, body));
      return;
    }

    elements.seccionEditar.hidden = true;
    ocultarEdicionEstado();
    mostrarEdicionEstado("Usuario actualizado correctamente.", "exito");
    await cargarUsuarios();
  } catch (error) {
    console.error("PATCH /api/users:", error);
    mostrarEdicionEstado(
      "No se pudo conectar con el servidor. Verifique que esté en funcionamiento.",
      "error"
    );
  } finally {
    ocupado = false;
    elements.guardarEdicion.disabled = false;
  }
}

async function cargarUsuarios() {
  const elements = getElements();
  elements.tabla.hidden = true;
  mostrarUsuariosEstado("Cargando usuarios...", "cargando");
  try {
    /* todos=true: el administrador también ve los usuarios desactivados. */
    const response = await fetchWithAuth(`${API_USERS_URL}?todos=true`);
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
      "No se pudo conectar con el servidor. Verifique que esté en funcionamiento.",
      "error"
    );
  }
}

/* Error al agregar: debajo del campo si corresponde a uno (el aviso
   general queda con el mismo texto, oculto); si no, el aviso general. */
function avisarErrorCrear(mensaje) {
  showStatus(mensaje, "error");
  if (mostrarErrorCampo(mensaje)) getElements().estadoUsuario.hidden = true;
}

function avisarErrorEdicion(mensaje) {
  mostrarEdicionEstado(mensaje, "error");
  if (mostrarErrorCampo(mensaje, "editar-")) getElements().estadoEdicion.hidden = true;
}

async function crearUsuario(event) {
  event.preventDefault();
  if (ocupado) return;

  limpiarErroresCampo();
  const errorValidacion = validarUsuario();
  if (errorValidacion) {
    avisarErrorCrear(errorValidacion);
    return;
  }

  const elements = getElements();
  const payload = {
    name: elements.nombre.value.trim(),
    email: elements.email.value.trim(),
    password: elements.password.value,
    role: elements.rol.value,
  };

  ocupado = true;
  elements.crear.disabled = true;
  try {
    const response = await fetchWithAuth(API_USERS_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const body = response.ok ? null : await response.json().catch(() => null);
    if (!response.ok) {
      avisarErrorCrear(mensajeDeError(response, body));
      return;
    }

    elements.nombre.value = "";
    elements.email.value = "";
    elements.password.value = "";
    elements.rol.value = "Técnico";
    showStatus("Usuario agregado correctamente.", "exito");
    /* El usuario nuevo aparece en la lista sin recargar la página. */
    await cargarUsuarios();
  } catch (error) {
    console.error("POST /api/users:", error);
    showStatus(
      "No se pudo conectar con el servidor. Verifique que esté en funcionamiento.",
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
  /* «Limpiar» vacía el formulario y quita los errores. */
  elements.formUsuario.addEventListener("reset", () => {
    limpiarErroresCampo();
    elements.estadoUsuario.hidden = true;
  });
  elements.formEditar.addEventListener("submit", guardarEdicion);
  elements.cancelarEdicion.addEventListener("click", cancelarEdicion);
  await cargarUsuarios();
}

if (typeof document !== "undefined") {
  document.addEventListener("DOMContentLoaded", () => init());
}
