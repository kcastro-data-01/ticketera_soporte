/* Mi cuenta: muestra los datos del usuario de la sesión. La contraseña es
   la de la cuenta de Microsoft de la empresa: no se cambia aquí. */

function initCuenta() {
  const user = getUser();
  if (user) {
    document.getElementById("cuenta-nombre").textContent = user.name || "—";
    document.getElementById("cuenta-email").textContent = user.email || "—";
    document.getElementById("cuenta-rol").textContent = user.role || "—";
  }
}

if (typeof document !== "undefined" && typeof document.addEventListener === "function") {
  document.addEventListener("DOMContentLoaded", initCuenta);
}
