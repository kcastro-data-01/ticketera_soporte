/* Mi cuenta: muestra los datos del usuario de la sesión y le permite
   cambiar su propia contraseña (POST /api/auth/change-password). */

const API_CHANGE_PASSWORD_URL = "/api/auth/change-password";

function mostrarEstadoPassword(mensaje, tipo) {
  const estado = document.getElementById("estado-password");
  estado.textContent = mensaje;
  estado.className = `estado ${tipo}`;
  estado.hidden = false;
}

/* Mensaje de error del formulario, o "" si se puede enviar. */
function validarCambioPassword(actual, nueva, confirmar) {
  if (!actual) return "Escribe tu contraseña actual.";
  if (nueva.length < 6) return "La nueva contraseña debe tener al menos 6 caracteres.";
  if (nueva.length > 72) return "La nueva contraseña debe tener como máximo 72 caracteres.";
  if (nueva !== confirmar) return "Las contraseñas nuevas no coinciden.";
  if (nueva === actual) return "La nueva contraseña debe ser distinta de la actual.";
  return "";
}

async function cambiarPassword(event) {
  event.preventDefault();
  const actual = document.getElementById("password-actual");
  const nueva = document.getElementById("password-nueva");
  const confirmar = document.getElementById("password-confirmar");
  const boton = document.getElementById("guardar-password");

  const error = validarCambioPassword(actual.value, nueva.value, confirmar.value);
  if (error) {
    mostrarEstadoPassword(error, "error");
    return;
  }

  boton.disabled = true;
  try {
    const response = await fetchWithAuth(API_CHANGE_PASSWORD_URL, {
      method: "POST",
      body: JSON.stringify({
        current_password: actual.value,
        new_password: nueva.value,
      }),
    });
    if (response.ok) {
      actual.value = "";
      nueva.value = "";
      confirmar.value = "";
      mostrarEstadoPassword("Contraseña cambiada. Úsala la próxima vez que inicies sesión.", "exito");
      return;
    }
    const body = await response.json().catch(() => null);
    const detalle = body && typeof body.detail === "string" ? body.detail : "";
    mostrarEstadoPassword(detalle || `No se pudo cambiar la contraseña (${response.status}).`, "error");
  } catch (err) {
    console.error("POST /api/auth/change-password:", err);
    mostrarEstadoPassword(
      "No se pudo conectar con el servidor. Comprueba que está en ejecución.",
      "error"
    );
  } finally {
    boton.disabled = false;
  }
}

function initCuenta() {
  const user = getUser();
  if (user) {
    document.getElementById("cuenta-nombre").textContent = user.name || "—";
    document.getElementById("cuenta-email").textContent = user.email || "—";
    document.getElementById("cuenta-rol").textContent = user.role || "—";
  }
  document.getElementById("form-password").addEventListener("submit", cambiarPassword);
}

if (typeof document !== "undefined" && typeof document.addEventListener === "function") {
  document.addEventListener("DOMContentLoaded", initCuenta);
}
