/* Tarea 11 — Listado, búsqueda y filtros de tickets contra la API.
   JavaScript vanilla, sin frameworks ni librerías externas.
   Fase 2: usa fetchWithAuth para incluir el token JWT automáticamente. */

const API_TICKETS_URL = "/api/tickets";
const API_USERS_URL = "/api/users";
const API_SUMMARY_URL = "/api/tickets/summary";

/* Tickets por página del listado. */
const PAGE_SIZE = 20;

let usersById = new Map();
/* Página actual (empieza en 0) y vista «Mis tickets». */
let paginaActual = 0;
let soloMios = false;

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
    paginacion: document.getElementById("paginacion"),
    paginaAnterior: document.getElementById("pagina-anterior"),
    paginaSiguiente: document.getElementById("pagina-siguiente"),
    paginaInfo: document.getElementById("pagina-info"),
    vistaTodos: document.getElementById("vista-todos"),
    vistaMios: document.getElementById("vista-mios"),
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
    mios: soloMios,
  };
}

/* La página se pide con limit/offset; el total llega en X-Total-Count. */
function buildTicketsUrl(filters, pagina = 0) {
  const params = new URLSearchParams();
  if (filters.search) params.set("search", filters.search);
  if (filters.category) params.set("category", filters.category);
  if (filters.priority) params.set("priority", filters.priority);
  /* «Resuelto,Cerrado» pide varios estados: ?state=Resuelto&state=Cerrado. */
  if (filters.state) {
    filters.state.split(",").forEach((estado) => params.append("state", estado));
  }
  if (filters.mios) params.set("mios", "true");
  params.set("limit", String(PAGE_SIZE));
  if (pagina > 0) params.set("offset", String(pagina * PAGE_SIZE));
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
     con desplazamiento explícito. Formato corto: 20/10/26 16:36. */
  return new Date(value).toLocaleString("es-ES", {
    timeZone: "America/Costa_Rica",
    day: "2-digit",
    month: "2-digit",
    year: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function assignedText(ticket) {
  if (ticket.assigned_to_id === null || ticket.assigned_to_id === undefined) {
    return "—";
  }
  const name = usersById.get(ticket.assigned_to_id);
  return name || `Usuario #${ticket.assigned_to_id}`;
}

function appendCell(row, text, className) {
  const cell = document.createElement("td");
  if (className) cell.className = className;
  cell.textContent = text;
  row.appendChild(cell);
}

/* El ID del listado abre la pantalla de detalle (Tarea 13). */
/* Celda con etiqueta de color para prioridad o estado. */
function appendBadgeCell(row, text) {
  const cell = document.createElement("td");
  const badge = document.createElement("span");
  badge.className = claseBadge(text);
  badge.textContent = text;
  cell.appendChild(badge);
  row.appendChild(cell);
}

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
    appendBadgeCell(row, ticket.priority);
    appendBadgeCell(row, ticket.state);
    appendCell(row, assignedText(ticket));
    appendCell(row, formatFecha(ticket.created_at), "celda-fecha");
    appendActionCell(row, ticket.id);
    elements.tbody.appendChild(row);
  });
}

/* Los usuarios solo sirven para mostrar el nombre de quien tiene el ticket. */
async function loadUsers() {
  try {
    const response = await fetchWithAuth(API_USERS_URL);
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
  const url = buildTicketsUrl(getFilters(), paginaActual);

  let response;
  try {
    response = await fetchWithAuth(url);
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

  const totalCabecera = Number(
    response.headers && typeof response.headers.get === "function"
      ? response.headers.get("X-Total-Count")
      : NaN
  );
  renderPaginacion(Number.isFinite(totalCabecera) ? totalCabecera : tickets.length);

  if (tickets.length === 0) {
    const filtros = getFilters();
    const conFiltros = Boolean(
      filtros.search || filtros.category || filtros.priority || filtros.state || filtros.mios
    );
    showStatus(
      conFiltros ? "No hay tickets que coincidan con los filtros." : "No hay tickets para mostrar.",
      "vacio"
    );
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

/* Controles «← Anterior · Página X de Y · Siguiente →». */
function renderPaginacion(total) {
  const elements = getElements();
  if (!elements.paginacion) return;
  const paginas = Math.max(1, Math.ceil(total / PAGE_SIZE));
  elements.paginacion.hidden = total <= PAGE_SIZE;
  elements.paginaInfo.textContent = `Página ${paginaActual + 1} de ${paginas} · ${total} tickets`;
  elements.paginaAnterior.disabled = paginaActual === 0;
  elements.paginaSiguiente.disabled = paginaActual + 1 >= paginas;
}

function irAPagina(pagina) {
  paginaActual = Math.max(0, pagina);
  fetchTickets();
}

/* Cambia entre «Todos» y «Mis tickets» y vuelve a la primera página. */
function mostrarSoloMios(valor) {
  const elements = getElements();
  soloMios = valor;
  if (elements.vistaTodos && elements.vistaMios) {
    elements.vistaTodos.classList.toggle("activa", !valor);
    elements.vistaMios.classList.toggle("activa", valor);
    elements.vistaTodos.setAttribute("aria-pressed", String(!valor));
    elements.vistaMios.setAttribute("aria-pressed", String(valor));
  }
  irAPagina(0);
}

/* Tarjetas del panel: números del resumen y, al pulsarlas, el filtro. */
async function cargarResumen() {
  const campos = {
    "res-nuevos": "nuevos",
    "res-en-proceso": "en_proceso",
    "res-resueltos": "resueltos",
    "res-criticos": "criticos_abiertos",
    "res-mios": "mios_abiertos",
  };
  try {
    const response = await fetchWithAuth(API_SUMMARY_URL);
    if (!response.ok) return;
    const resumen = await response.json();
    Object.entries(campos).forEach(([id, campo]) => {
      const nodo = document.getElementById(id);
      if (nodo) nodo.textContent = String(resumen[campo] ?? "—");
    });
  } catch (error) {
    console.error("No se pudo cargar el resumen:", error);
  }
}

function aplicarTarjeta(tarjeta) {
  const elements = getElements();
  elements.form.reset();
  if (tarjeta.dataset.estado) elements.state.value = tarjeta.dataset.estado;
  if (tarjeta.dataset.prioridad) elements.priority.value = tarjeta.dataset.prioridad;
  mostrarSoloMios(tarjeta.dataset.mios === "true");
}

function init() {
  const elements = getElements();

  elements.form.addEventListener("submit", (event) => {
    event.preventDefault();
    irAPagina(0);
  });

  elements.limpiar.addEventListener("click", () => {
    elements.form.reset();
    mostrarSoloMios(false);
  });

  if (elements.paginaAnterior) {
    elements.paginaAnterior.addEventListener("click", () => irAPagina(paginaActual - 1));
    elements.paginaSiguiente.addEventListener("click", () => irAPagina(paginaActual + 1));
  }
  if (elements.vistaTodos) {
    elements.vistaTodos.addEventListener("click", () => mostrarSoloMios(false));
    elements.vistaMios.addEventListener("click", () => mostrarSoloMios(true));
  }
  if (typeof document.querySelectorAll === "function") {
    document.querySelectorAll(".tarjeta-resumen").forEach((tarjeta) => {
      tarjeta.addEventListener("click", () => aplicarTarjeta(tarjeta));
    });
  }

  cargarResumen();
  loadUsers().then(fetchTickets);
}

if (typeof document !== "undefined") {
  document.addEventListener("DOMContentLoaded", init);
}

/* Celda de acción: «Editar» para los roles que pueden editar tickets y
   «Ver» para el resto; ambos abren el detalle. */
function appendActionCell(row, ticketId) {
  const cell = document.createElement("td");
  const button = document.createElement("button");
  button.type = "button";
  button.className = "btn-accion";
  const puedeEditar = typeof puede === "function" ? puede("editar") : true;
  button.textContent = puedeEditar ? "Editar" : "Ver";
  button.onclick = (e) => {
    e.preventDefault();
    window.location.href = `detalle.html?id=${ticketId}`;
  };
  cell.appendChild(button);
  row.appendChild(cell);
}

