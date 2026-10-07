/* Tarea 12 — Alta de tickets desde el formulario, contra POST /api/tickets.
   JavaScript vanilla, sin frameworks ni librerías externas. */

const API_TICKETS_URL = "/api/tickets";
const REDIRECT_DELAY_MS = 1500;

let enviando = false;
let redirigiendo = false;

function getElements() {
  return {
    form: document.getElementById("form-crear"),
    title: document.getElementById("title"),
    description: document.getElementById("description"),
    category: document.getElementById("category"),
    priority: document.getElementById("priority"),
    save: document.getElementById("guardar"),
    estado: document.getElementById("estado-carga"),
  };
}

function showStatus(message, type) {
  const elements = getElements();
  elements.estado.textContent = message;
  elements.estado.className = `estado ${type}`;
  elements.estado.hidden = false;
}

function getPayload() {
  const elements = getElements();
  return {
    title: elements.title.value.trim(),
    description: elements.description.value.trim(),
    category: elements.category.value,
    priority: elements.priority.value,
  };
}

/* Validación en el navegador antes de tocar la API. */
function validatePayload(payload) {
  if (!payload.title && !payload.description) {
    return "El título y la descripción son obligatorios.";
  }
  if (!payload.title) {
    return "El título es obligatorio.";
  }
  if (!payload.description) {
    return "La descripción es obligatoria.";
  }
  return "";
}

/* Convierte el detalle de validación de FastAPI (422) en un mensaje legible. */
function formatValidation(detail) {
  if (!detail || !Array.isArray(detail.detail)) {
    return "La API rechazó los datos enviados. Revisa el formulario.";
  }
  const messages = detail.detail.map((error) => {
    const field = Array.isArray(error.loc) ? error.loc.slice(1).join(".") : "";
    return field ? `${field}: ${error.msg}` : error.msg;
  });
  return `Revisa los datos enviados. ${messages.join(" | ")}`;
}

async function createTicket() {
  if (enviando) return;

  const payload = getPayload();
  const clientError = validatePayload(payload);
  if (clientError) {
    showStatus(clientError, "error");
    return;
  }

  enviando = true;
  const elements = getElements();
  elements.save.disabled = true;
  showStatus("Guardando...", "cargando");

  try {
    const response = await fetch(API_TICKETS_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (response.status === 422) {
      const body = await response.json().catch(() => null);
      showStatus(formatValidation(body), "error");
      return;
    }

    if (!response.ok) {
      showStatus(
        `No se pudo crear el ticket (HTTP ${response.status}). Inténtalo de nuevo.`,
        "error"
      );
      return;
    }

    const ticket = await response.json();
    redirigiendo = true;
    showStatus(
      `Ticket #${ticket.id} creado correctamente. Redirigiendo al listado...`,
      "exito"
    );
    setTimeout(() => {
      window.location.href = "index.html";
    }, REDIRECT_DELAY_MS);
  } catch (error) {
    showStatus("Error al comunicarse con la API.", "error");
  } finally {
    if (!redirigiendo) {
      enviando = false;
      elements.save.disabled = false;
    }
  }
}

function init() {
  const elements = getElements();

  elements.form.addEventListener("submit", (event) => {
    event.preventDefault();
    createTicket();
  });
}

if (typeof document !== "undefined") {
  document.addEventListener("DOMContentLoaded", init);
}
