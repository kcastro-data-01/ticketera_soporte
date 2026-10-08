/* Tarea 13/14/18/20.2 — Detalle y gestión de un ticket con los endpoints
   existentes: GET/PATCH /api/tickets/{id}, PATCH .../assign,
   PATCH .../state, GET /api/users, POST y GET .../comments y
   GET .../history. JavaScript vanilla, sin frameworks ni librerías. */

const API_USERS_URL = "/api/users";

/* Transiciones válidas desde cada estado (espejo del backend para ofrecer
   solo destinos posibles; el backend siempre vuelve a validar). Avances
   lineales: Nuevo → En proceso → Resuelto → Cerrado (Cerrado es final). */
const TRANSICIONES = {
  "Nuevo": ["En proceso"],
  "En proceso": ["Resuelto"],
  "Resuelto": ["Cerrado"],
  "Cerrado": [],
};

let ticketId = null;
let usersById = new Map();
let ocupado = false;
/* false cuando GET /api/users falla: bloquea la asignación para que un
   select sin usuarios no desasigne el ticket por accidente. */
let usuariosCargados = false;

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
    usuariosNota: document.getElementById("usuarios-nota"),
    estadoActual: document.getElementById("estado-actual"),
    estadoDestino: document.getElementById("estado-destino"),
    cambiarEstado: document.getElementById("cambiar-estado"),
    estadoFinal: document.getElementById("estado-final"),
    formComentario: document.getElementById("form-comentario"),
    contenido: document.getElementById("contenido"),
    comentar: document.getElementById("comentar"),
    comentariosEstado: document.getElementById("comentarios-estado"),
    listaComentarios: document.getElementById("lista-comentarios"),
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
  /* El botón de estado solo se activa si hay alguna transición posible. */
  elements.cambiarEstado.disabled =
    bloqueado || elements.estadoDestino.options.length === 0;
}

function formatFecha(value) {
  /* Hora local de Costa Rica (America/Costa_Rica, UTC-6), sin importar
     la zona horaria del navegador: la API envía marcas de tiempo en UTC
     con desplazamiento explícito. */
  return new Date(value).toLocaleString("es-ES", {
    timeZone: "America/Costa_Rica",
  });
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

  renderEstadoControl(ticket);
}

/* Muestra el estado actual y solo ofrece los destinos posibles desde él.
   Con "Cerrado" no queda ninguna transición: se oculta el selector útil y
   se explica que el estado es final. */
function renderEstadoControl(ticket) {
  const elements = getElements();
  const destinos = TRANSICIONES[ticket.state] || [];
  elements.estadoActual.textContent = ticket.state;
  elements.estadoDestino.replaceChildren();
  destinos.forEach((estado) => {
    const option = document.createElement("option");
    option.value = estado;
    option.textContent = estado;
    elements.estadoDestino.appendChild(option);
  });
  const sinTransiciones = destinos.length === 0;
  elements.estadoDestino.disabled = sinTransiciones;
  elements.cambiarEstado.disabled = sinTransiciones;
  elements.estadoFinal.hidden = !sinTransiciones;
}

function renderUsuarios(users) {
  usuariosCargados = true;
  usersById = new Map(users.map((user) => [user.id, user.name]));
  const elements = getElements();
  elements.usuario.replaceChildren();
  const sinAsignar = document.createElement("option");
  sinAsignar.value = "";
  sinAsignar.textContent = "Sin asignar";
  elements.usuario.appendChild(sinAsignar);

  if (users.length === 0) {
    /* Sin usuarios no hay nada que asignar: se explica cómo crear uno. */
    elements.usuario.disabled = true;
    elements.usuariosNota.hidden = false;
    return;
  }
  elements.usuario.disabled = false;
  elements.usuariosNota.hidden = true;

  users.forEach((user) => {
    const option = document.createElement("option");
    option.value = String(user.id);
    option.textContent = user.name;
    elements.usuario.appendChild(option);
  });
}

/* Sin lista de usuarios el select queda deshabilitado con una opción que
   explica el motivo: así no se puede "guardar" una asignación vacía por
   accidente ni se desasigna el ticket sin querer. */
function renderUsuariosNoDisponibles() {
  const elements = getElements();
  elements.usuario.replaceChildren();
  elements.usuario.disabled = true;
  elements.usuariosNota.hidden = true;
  const option = document.createElement("option");
  option.value = "";
  option.textContent = "No se pudo cargar la lista de usuarios";
  elements.usuario.appendChild(option);
}

async function cargarUsuarios() {
  try {
    const response = await fetch(API_USERS_URL);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const users = await response.json();
    if (!Array.isArray(users)) throw new Error("respuesta inválida");
    renderUsuarios(users);
  } catch (error) {
    console.error("GET /api/users:", error);
    renderUsuariosNoDisponibles();
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
  if (!usuariosCargados) {
    showStatus(
      "No se pudo cargar la lista de usuarios: recarga la página para intentarlo de nuevo.",
      "error"
    );
    return;
  }
  const elements = getElements();
  if (elements.usuario.disabled) {
    showStatus(
      "No hay usuarios disponibles: crea uno desde la página de Usuarios.",
      "error"
    );
    return;
  }
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

async function cambiarEstado() {
  if (ocupado || ticketId === null) return;
  const elements = getElements();
  const destino = elements.estadoDestino.value;
  if (!destino) return; /* sin transiciones posibles (ticket cerrado) */

  ocupado = true;
  bloquearBotones(true);
  try {
    const response = await fetch(`/api/tickets/${ticketId}/state`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ state: destino }),
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
    if (response.status === 409) {
      showStatus(
        await mensajeDeDetalle(
          response,
          "La transición de estado no está permitida."
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
        `No se pudo cambiar el estado (HTTP ${response.status}).`,
        "error"
      );
      return;
    }
    showStatus(`Estado actualizado a «${destino}».`, "exito");
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
    /* El comentario nuevo aparece en la lista sin recargar la página. */
    await cargarComentarios();
  } catch (error) {
    showStatus("Error al comunicarse con la API.", "error");
  } finally {
    ocupado = false;
    bloquearBotones(false);
  }
}

function mostrarComentariosEstado(message, type) {
  const elements = getElements();
  elements.comentariosEstado.textContent = message;
  elements.comentariosEstado.className = type ? `estado ${type}` : "estado";
  elements.comentariosEstado.hidden = false;
}

function ocultarComentariosEstado() {
  const elements = getElements();
  elements.comentariosEstado.textContent = "";
  elements.comentariosEstado.hidden = true;
}

/* Renderiza con textContent: los datos del backend nunca se interpretan
   como HTML. */
function renderComentarios(comments) {
  const elements = getElements();
  elements.listaComentarios.replaceChildren();
  if (!Array.isArray(comments) || comments.length === 0) {
    elements.listaComentarios.hidden = true;
    mostrarComentariosEstado(
      "Este ticket todavía no tiene comentarios.",
      "vacio"
    );
    return;
  }
  comments.forEach((comment) => {
    const card = document.createElement("article");
    card.className = "comentario";

    const header = document.createElement("div");
    header.className = "comentario-cabecera";
    const author = document.createElement("span");
    author.className = "comentario-autor";
    author.textContent = comment.author || "Anónimo";
    const fecha = document.createElement("span");
    fecha.className = "comentario-fecha";
    fecha.textContent = formatFecha(comment.created_at);
    header.appendChild(author);
    header.appendChild(fecha);

    const content = document.createElement("p");
    content.className = "comentario-contenido";
    content.textContent = comment.content;

    card.appendChild(header);
    card.appendChild(content);
    elements.listaComentarios.appendChild(card);
  });
  ocultarComentariosEstado();
  elements.listaComentarios.hidden = false;
}

async function cargarComentarios() {
  if (ticketId === null) return;
  const elements = getElements();
  elements.listaComentarios.hidden = true;
  mostrarComentariosEstado("Cargando comentarios...", "cargando");
  try {
    const response = await fetch(`/api/tickets/${ticketId}/comments`);
    if (response.status === 404) {
      mostrarComentariosEstado(
        await mensajeDeDetalle(
          response,
          `No se encontró el ticket #${ticketId}.`
        ),
        "error"
      );
      return;
    }
    if (!response.ok) {
      mostrarComentariosEstado(
        `No se pudieron cargar los comentarios (HTTP ${response.status}).`,
        "error"
      );
      return;
    }
    let comments = null;
    try {
      comments = await response.json();
    } catch (parseError) {
      comments = null;
    }
    if (!Array.isArray(comments)) {
      mostrarComentariosEstado("Respuesta inválida del servidor.", "error");
      return;
    }
    renderComentarios(comments);
  } catch (error) {
    console.error("GET comentarios:", error);
    mostrarComentariosEstado(
      "No se pudo conectar con el servidor. Comprueba que está en ejecución.",
      "error"
    );
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
  elements.cambiarEstado.addEventListener("click", () => cambiarEstado());
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
  const ticketCargado = await cargarTicket();
  if (ticketCargado) {
    await cargarComentarios();
  }
}

if (typeof document !== "undefined") {
  document.addEventListener("DOMContentLoaded", init);
}
