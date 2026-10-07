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
  return new Date(value).toLocaleString("es-ES");
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

function renderTickets(tickets) {
  const elements = getElements();
  clearRows();
  tickets.forEach((ticket) => {
    const row = document.createElement("tr");
    appendCell(row, ticket.id);
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

async function fetchTickets() {
  showStatus("Cargando...", "cargando");
  clearRows();

  try {
    const response = await fetch(buildTicketsUrl(getFilters()));
    if (!response.ok) {
      throw new Error(`La API respondió ${response.status}`);
    }
    const tickets = await response.json();
    if (!Array.isArray(tickets)) {
      throw new Error("Respuesta inesperada de la API");
    }
    if (tickets.length === 0) {
      showStatus("No hay tickets para mostrar.", "vacio");
      return;
    }
    hideStatus();
    renderTickets(tickets);
  } catch (error) {
    showStatus("Error al comunicarse con la API.", "error");
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
