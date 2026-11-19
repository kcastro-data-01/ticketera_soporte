/* Usuarios (port de frontend/js/usuarios.js, sin DOM): validación y
   mensajes de error de la API. */
export const ROLES_VALIDOS = ["Técnico", "Administrador", "Solicitante"];
export const ROLES_IT_USUARIOS = ["Administrador", "Técnico"];
const EMAIL_PATTERN = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
const PASSWORD_MIN = 6;
const PASSWORD_MAX = 72;

export function validarPassword(password) {
  if (password.length < PASSWORD_MIN) return `La contraseña debe tener al menos ${PASSWORD_MIN} caracteres.`;
  if (password.length > PASSWORD_MAX) return `La contraseña debe tener como máximo ${PASSWORD_MAX} caracteres.`;
  return "";
}

export function validarUsuario({ nombre, email, password, rol }, loginLocal) {
  if (!nombre.trim()) return "El nombre no puede estar vacío.";
  const correo = email.trim();
  if (!correo) return "El correo electrónico no puede estar vacío.";
  if (!EMAIL_PATTERN.test(correo)) return "El correo electrónico no tiene un formato válido.";
  if (loginLocal) {
    const error = validarPassword(password || "");
    if (error) return error;
  }
  if (!ROLES_VALIDOS.includes(rol)) return "Seleccione un rol válido.";
  return "";
}

/* 409 → detail; 422 → errores de campo; resto → «Error de API». */
export function mensajeDeError(response, payload) {
  if (response.status === 409) {
    if (payload && typeof payload.detail === "string") return payload.detail;
    return "Ese correo electrónico ya está registrado.";
  }
  if (response.status === 422) {
    if (payload && typeof payload.detail === "string") return payload.detail;
    if (payload && Array.isArray(payload.detail)) {
      return payload.detail.map((error) => {
        const campo = Array.isArray(error.loc) ? error.loc[error.loc.length - 1] : null;
        return campo ? `${campo}: ${error.msg}` : error.msg;
      }).join(" | ");
    }
    return "El servidor rechazó los datos enviados. Revise el formulario.";
  }
  if (payload && typeof payload.detail === "string") return `Error de API (${response.status}): ${payload.detail}`;
  return `Error de API (${response.status}).`;
}

/* A qué campo va un mensaje (o "" si a ninguno). */
export function campoDelError(mensaje) {
  const texto = String(mensaje || "").toLowerCase();
  if (/nombre|^name/.test(texto)) return "nombre";
  if (/correo|^email/.test(texto)) return "email";
  if (/contraseña|^password/.test(texto)) return "password";
  if (/\brol\b|^role/.test(texto)) return "rol";
  return "";
}

export const CLASES_ROL = { Administrador: "rol-administrador", Técnico: "rol-tecnico", Solicitante: "rol-solicitante" };
export const claseRol = (rol) => CLASES_ROL[rol] || "rol-solicitante";

export function textoAreaUsuario(user) {
  if (!ROLES_IT_USUARIOS.includes(user.role)) return "—";
  return user.area_name || "Sin departamento";
}

/* area_id para enviar: número, null (Sin departamento) o undefined (Solicitante). */
export function areaElegida(rol, area) {
  if (!ROLES_IT_USUARIOS.includes(rol)) return undefined;
  return /^\d+$/.test(String(area || "")) ? Number(area) : null;
}
