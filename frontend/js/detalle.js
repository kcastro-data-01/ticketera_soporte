/* Tarea 13/14 — Detalle y gestión de un ticket con los endpoints existentes:
   GET/PATCH /api/tickets/{id}, PATCH .../assign, GET /api/users,
   POST .../comments y GET .../history. Sin cambio de estado (pendiente como
   Tarea 18). JavaScript vanilla, sin frameworks ni librerías externas. */

const API_USERS_URL = "/api/users";

let ticketId = null;
let usersById = new Map();
let ocupado = false;

function getElements() {
  return {
    estado: document.getElementById("estado-carga"),
    ver: {
      id: document.getElementById("ver-id"),
      title: document.getElementById("ver-title"),
      description: document.getElementById("ver-description"),
      category: document.getElementById("ver-category"),
      priority: document.getElementById("ver-priority"),
      state: document.getElementById("ver-state"),
      assigned: document.getElementById("ver-assigned"),
      created: document.getElementById("ver-created"),
      updated: document.getElementById("ver-updated"),
    },
    formEditar: document.getElementById("form-editar"),
    title: document.getElementById("title"),
    description: document.getElementById("description"),
    category: document.getElementById("category"),
    priority: document.getElementById("priority"),
    guardar: document.getElementById("guardar"),
    usuario: document.getElementById("usuario"),
    asignar: document.getElementById("asignar"),
    formComentario: document.getElementById("form-comentario"),
    contenido: document.getElementById("contenido"),
    comentar: document.getElementById("comentar"),
    historial: document.getElementById("historial"),
    historialEstado: document.getElementById("historial-estado"),
    tablaHistorial: document.getElementById("tabla-historial"),
    historialCuerpo: document.getElementById("historial-cuerpo"),
  };
}

/* El id llega por query string: detalle.html?id=12 */
function getTicketId() {
  const raw = new URLSearchParams(window.location.search).get("id");
  const id = Number(raw);
  return raw !== null && Number.isInteger(id) && id > 0 ? id : null;
}

function showStatus(message, type) {
  const elements = getElements();
  elements.estado.textContent = message;
  elements.estado.className = `estado ${type}`;
  elements.estado.hidden = false;
}

function hideStatus() {
  const elements = getElements();
  elements.estado.textContent = "";
  elements.estado.hidden = true;
}

function bloquearBotones(bloqueado) {
  const elements = getElements();
  elements.guardar.disabled = bloqueado;
  elements.asignar.disabled = bloqueado;
  elements.comentar.disabled = bloqueado;
  elements.historial.disabled = bloqueado;
}

function formatFecha(value) {
  return new Date(value).toLocaleString("es-ES");
}

function nombreAsignado(ticket) {
  if (ticket.assigned_to_id === null || ticket.assigned_to_id === undefined) {
    return "—";
  }
  return usersById.get(ticket.assigned_to_id) || `Usuario #${ticket.assigned_to_id}`;
}

function validarTexto(payload) {
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

async function mensajeDeDetalle(response, mensajePorDefecto) {
  const body = await response.json().catch(() => null);
  return body && body.detail ? String(body.detail) : mensajePorDefecto;
}

function renderTicket(ticket) {
  const elements = getElements();
  elements.ver.id.textContent = ticket.id;
  elements.ver.title.textContent = ticket.title;
  elements.ver.description.textContent = ticket.description;
  elements.ver.category.textContent = ticket.category;
  elements.ver.priority.textContent = ticket.priority;
  elements.ver.state.textContent = ticket.state;
  elements.ver.assigned.textContent = nombreAsignado(ticket);
  elements.ver.created.textContent = formatFecha(ticket.created_at);
  elements.ver.updated.textContent = formatFecha(ticket.updated_at);

  elements.title.value = ticket.title;
  elements.description.value = ticket.description;
  elements.category.value = ticket.category;
  elements.priority.value = ticket.priority;

  elements.usuario.value =
    ticket.assigned_to_id === null || ticket.assigned_to_id === undefined
      ? ""
      : String(ticket.assigned_to_id);
}

function renderUsuarios(users) {
  usersById = new Map(users.map((user) => [user.id, user.name]));
  const elements = getElements();
  elements.usuario.replaceChildren();
  const sinAsignar = document.createElement("option");
  sinAsignar.value = "";
  sinAsignar.textContent = "Sin asignar";
  elements.usuario.appendChild(sinAsignar);
  users.forEach((user) => {
    const option = document.createElement("option");
    option.value = String(user.id);
    option.textContent = user.name;
    elements.usuario.appendChild(option);
  });
}

async function cargarUsuarios() {
  try {
    const response = await fetch(API_USERS_URL);
    if (!response.ok) return;
    const users = await response.json();
    if (Array.isArray(users)) renderUsuarios(users);
  } catch (error) {
    /* Sin usuarios se conserva la opción "Sin asignar". */
  }
}

async function cargarTicket({ silencioso = false } = {}) {
  if (!silencioso) showStatus("Cargando...", "cargando");
  try {
    const response = await fetch(`/api/tickets/${ticketId}`);
    if (response.status === 404) {
      showStatus(`No se encontró el ticket #${ticketId}.`, "error");
      return false;
    }
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const ticket = await response.json();
    if (!silencioso) hideStatus();
    renderTicket(ticket);
    return true;
  } catch (error) {
    showStatus("Error al comunicarse con la API.", "error");
    return false;
  }
}

async function guardarEdicion() {
  if (ocupado || ticketId === null) return;
  const elements = getElements();
  const payload = {
    title: elements.title.value.trim(),
    description: elements.description.value.trim(),
    category: elements.category.value,
    priority: elements.priority.value,
  };
  const errorCliente = validarTexto(payload);
  if (errorCliente) {
    showStatus(errorCliente, "error");
    return;
  }

  ocupado = true;
  bloquearBotones(true);
  try {
    const response = await fetch(`/api/tickets/${ticketId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (response.status === 404) {
      showStatus(`No se encontró el ticket #${ticketId}.`, "error");
      return;
    }
    if (response.status === 422) {
      const body = await response.json().catch(() => null);
      showStatus(formatValidation(body), "error");
      return;
    }
    if (!response.ok) {
      showStatus(
        `No se pudieron guardar los cambios (HTTP ${response.status}).`,
        "error"
      );
      return;
    }
    showStatus("Cambios guardados correctamente.", "exito");
    await cargarTicket({ silencioso: true });
  } catch (error) {
    showStatus("Error al comunicarse con la API.", "error");
  } finally {
    ocupado = false;
    bloquearBotones(false);
  }
}

async function guardarAsignacion() {
  if (ocupado || ticketId === null) return;
  const elements = getElements();
  const valor = elements.usuario.value;
  const assignedToId = valor === "" ? null : Number(valor);

  ocupado = true;
  bloquearBotones(true);
  try {
    const response = await fetch(`/api/tickets/${ticketId}/assign`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ assigned_to_id: assignedToId }),
    });
    if (response.status === 404) {
      showStatus(
        await mensajeDeDetalle(
          response,
          `No se encontró el ticket #${ticketId}.`
        ),
        "error"
      );
      return;
    }
    if (response.status === 422) {
      const body = await response.json().catch(() => null);
      showStatus(formatValidation(body), "error");
      return;
    }
    if (!response.ok) {
      showStatus(
        `No se pudo guardar la asignación (HTTP ${response.status}).`,
        "error"
      );
      return;
    }
    showStatus(
      assignedToId === null
        ? "El ticket quedó sin asignar."
        : "Asignación guardada correctamente.",
      "exito"
    );
    await cargarTicket({ silencioso: true });
  } catch (error) {
    showStatus("Error al comunicarse con la API.", "error");
  } finally {
    ocupado = false;
    bloquearBotones(false);
  }
}

async function agregarComentario() {
  if (ocupado || ticketId === null) return;
  const elements = getElements();
  const content = elements.contenido.value.trim();
  if (!content) {
    showStatus("El comentario no puede estar vacío.", "error");
    return;
  }

  ocupado = true;
  bloquearBotones(true);
  try {
    const response = await fetch(`/api/tickets/${ticketId}/comments`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content }),
    });
    if (response.status === 404) {
      showStatus(
        await mensajeDeDetalle(
          response,
          `No se encontró el ticket #${ticketId}.`
        ),
        "error"
      );
      return;
    }
    if (response.status === 422) {
      const body = await response.json().catch(() => null);
      showStatus(formatValidation(body), "error");
      return;
    }
    if (!response.ok) {
      showStatus(
        `No se pudo agregar el comentario (HTTP ${response.status}).`,
        "error"
      );
      return;
    }
    elements.contenido.value = "";
    showStatus("Comentario agregado correctamente.", "exito");
  } catch (error) {
    showStatus("Error al comunicarse con la API.", "error");
  } finally {
    ocupado = false;
    bloquearBotones(false);
  }
}

function mostrarHistorialEstado(message, type) {
  const elements = getElements();
  elements.historialEstado.textContent = message;
  elements.historialEstado.className = type ? `estado ${type}` : "estado";
  elements.historialEstado.hidden = false;
}

function ocultarHistorialEstado() {
  const elements = getElements();
  elements.historialEstado.textContent = "";
  elements.historialEstado.hidden = true;
}

/* Describe el cambio con los campos que realmente trae el registro:
   campo modificado y valores anterior → nuevo; "—" si no hay detalle. */
function formatDetalleHistorial(entry) {
  const partes = [];
  if (entry.field) partes.push(entry.field);
  const hayValores = entry.old_value !== null || entry.new_value !== null;
  if (hayValores) {
    partes.push(`${entry.old_value ?? "—"} → ${entry.new_value ?? "—"}`);
  }
  return partes.length > 0 ? partes.join(": ") : "—";
}

function appendCeldaHistorial(row, text) {
  const cell = document.createElement("td");
  cell.textContent = text;
  row.appendChild(cell);
}

/* Renderiza con textContent: los datos del backend nunca se interpretan
   como HTML. */
function renderHistorial(entries) {
  const elements = getElements();
  elements.historialCuerpo.replaceChildren();
  if (!Array.isArray(entries) || entries.length === 0) {
    elements.tablaHistorial.hidden = true;
    mostrarHistorialEstado(
      "No hay cambios registrados para este ticket.",
      "vacio"
    );
    return;
  }
  entries.forEach((entry) => {
    const row = document.createElement("tr");
    appendCeldaHistorial(row, formatFecha(entry.created_at));
    appendCeldaHistorial(row, entry.author || "—");
    appendCeldaHistorial(row, entry.action || "—");
    appendCeldaHistorial(row, formatDetalleHistorial(entry));
    elements.historialCuerpo.appendChild(row);
  });
  ocultarHistorialEstado();
  elements.tablaHistorial.hidden = false;
}

async function cargarHistorial() {
  if (ocupado || ticketId === null) return;
  ocupado = true;
  bloquearBotones(true);
  const elements = getElements();
  elements.tablaHistorial.hidden = true;
  mostrarHistorialEstado("Cargando...", "cargando");
  try {
    const response = await fetch(`/api/tickets/${ticketId}/history`);
    if (response.status === 404) {
      mostrarHistorialEstado(
        await mensajeDeDetalle(
          response,
          `No se encontró el ticket #${ticketId}.`
        ),
        "error"
      );
      return;
    }
    if (!response.ok) {
      mostrarHistorialEstado(
        `No se pudo cargar el historial (HTTP ${response.status}).`,
        "error"
      );
      return;
    }
    const entries = await response.json();
    renderHistorial(entries);
  } catch (error) {
    mostrarHistorialEstado("Error al comunicarse con la API.", "error");
  } finally {
    ocupado = false;
    bloquearBotones(false);
  }
}

async function init() {
  const elements = getElements();

  elements.formEditar.addEventListener("submit", (event) => {
    event.preventDefault();
    guardarEdicion();
  });
  elements.asignar.addEventListener("click", () => guardarAsignacion());
  elements.formComentario.addEventListener("submit", (event) => {
    event.preventDefault();
    agregarComentario();
  });
  elements.historial.addEventListener("click", () => cargarHistorial());

  ticketId = getTicketId();
  if (ticketId === null) {
    showStatus(
      "Identificador de ticket no válido. Vuelve al listado y abre un ticket.",
      "error"
    );
    ocupado = true;
    bloquearBotones(true);
    return;
  }

  await cargarUsuarios();
  await cargarTicket();
}

if (typeof document !== "undefined") {
  document.addEventListener("DOMContentLoaded", init);
}
