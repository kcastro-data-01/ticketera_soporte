/* Tarea 11 — Listado, búsqueda y filtros de tickets contra la API.
   JavaScript vanilla, sin frameworks ni librerías externas. */

const API_TICKETS_URL = "/api/tickets";
const API_USERS_URL = "/api/users";

let usersById = new Map();

function getElements() {
  return {
    form: document.getElementById("form-filtros"),
    search: document.getElementById("search"),
    category: document.getElementById("category"),
    priority: document.getElementById("priority"),
    state: document.getElementById("state"),
    limpiar: document.getElementById("limpiar"),
    estado: document.getElementById("estado-carga"),
    tbody: document.getElementById("lista-tickets"),
  };
}

/* Solo se envían los parámetros con valor, con los nombres que ya usa la API. */
function getFilters() {
  const elements = getElements();
  return {
    search: elements.search.value.trim(),
    category: elements.category.value,
    priority: elements.priority.value,
    state: elements.state.value,
  };
}

function buildTicketsUrl(filters) {
  const params = new URLSearchParams();
  if (filters.search) params.set("search", filters.search);
  if (filters.category) params.set("category", filters.category);
  if (filters.priority) params.set("priority", filters.priority);
  if (filters.state) params.set("state", filters.state);
  const query = params.toString();
  return query ? `${API_TICKETS_URL}?${query}` : API_TICKETS_URL;
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

function clearRows() {
  const elements = getElements();
  elements.tbody.replaceChildren();
}

function formatFecha(value) {
  /* Hora local de Costa Rica (America/Costa_Rica, UTC-6), sin importar
     la zona horaria del navegador: la API envía marcas de tiempo en UTC
     con desplazamiento explícito. */
  return new Date(value).toLocaleString("es-ES", {
    timeZone: "America/Costa_Rica",
  });
}

function assignedText(ticket) {
  if (ticket.assigned_to_id === null || ticket.assigned_to_id === undefined) {
    return "—";
  }
  const name = usersById.get(ticket.assigned_to_id);
  return name || `Usuario #${ticket.assigned_to_id}`;
}

function appendCell(row, text) {
  const cell = document.createElement("td");
  cell.textContent = text;
  row.appendChild(cell);
}

/* El ID del listado abre la pantalla de detalle (Tarea 13). */
function appendIdCell(row, ticketId) {
  const cell = document.createElement("td");
  const link = document.createElement("a");
  link.className = "enlace-tabla";
  link.href = `detalle.html?id=${ticketId}`;
  link.textContent = ticketId;
  cell.appendChild(link);
  row.appendChild(cell);
}

function renderTickets(tickets) {
  const elements = getElements();
  clearRows();
  tickets.forEach((ticket) => {
    const row = document.createElement("tr");
    appendIdCell(row, ticket.id);
    appendCell(row, ticket.title);
    appendCell(row, ticket.category);
    appendCell(row, ticket.priority);
    appendCell(row, ticket.state);
    appendCell(row, assignedText(ticket));
    appendCell(row, formatFecha(ticket.created_at));
    elements.tbody.appendChild(row);
  });
}

/* Los usuarios solo sirven para mostrar el nombre de quien tiene el ticket. */
async function loadUsers() {
  try {
    const response = await fetch(API_USERS_URL);
    if (!response.ok) return;
    const users = await response.json();
    if (!Array.isArray(users)) return;
    usersById = new Map(users.map((user) => [user.id, user.name]));
  } catch (error) {
    /* Sin usuarios se muestra el identificador como alternativa. */
  }
}

/* FastAPI devuelve `detail`; solo se muestra si es texto, para no exponer
   estructuras internas de validación al usuario. */
async function readApiDetail(response) {
  try {
    const body = await response.json();
    if (body && typeof body.detail === "string") {
      return body.detail;
    }
  } catch (error) {
    /* Cuerpo no JSON: se muestra únicamente el código HTTP. */
  }
  return "";
}

async function fetchTickets() {
  showStatus("Cargando...", "cargando");
  clearRows();

  /* 1) La URL se construye una sola vez. 2) Una única petición HTTP por
     ejecución de fetchTickets(). */
  const url = buildTicketsUrl(getFilters());

  let response;
  try {
    response = await fetch(url);
  } catch (error) {
    console.error("No se pudo conectar con el servidor:", error);
    showStatus(
      "No se pudo conectar con el servidor. Comprueba que está en ejecución.",
      "error"
    );
    return;
  }

  if (!response.ok) {
    const detail = await readApiDetail(response);
    console.error(`La API respondió ${response.status}`, detail);
    showStatus(
      detail
        ? `Error de API (${response.status}): ${detail}`
        : `Error de API (${response.status}).`,
      "error"
    );
    return;
  }

  let tickets;
  try {
    tickets = await response.json();
  } catch (error) {
    console.error("La API no devolvió JSON válido:", error);
    showStatus("Respuesta inválida del servidor.", "error");
    return;
  }

  if (!Array.isArray(tickets)) {
    console.error("La API no devolvió una lista de tickets:", tickets);
    showStatus("Respuesta inválida del servidor.", "error");
    return;
  }

  if (tickets.length === 0) {
    showStatus("No hay tickets para mostrar.", "vacio");
    return;
  }

  try {
    hideStatus();
    renderTickets(tickets);
  } catch (error) {
    console.error("No se pudieron representar los tickets:", error);
    showStatus("Respuesta inválida del servidor.", "error");
  }
}

function init() {
  const elements = getElements();

  elements.form.addEventListener("submit", (event) => {
    event.preventDefault();
    fetchTickets();
  });

  elements.limpiar.addEventListener("click", () => {
    elements.form.reset();
    fetchTickets();
  });

  loadUsers().then(fetchTickets);
}

if (typeof document !== "undefined") {
  document.addEventListener("DOMContentLoaded", init);
}
