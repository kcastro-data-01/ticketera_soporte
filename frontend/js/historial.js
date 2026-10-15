/* Página de historial global: consulta GET /api/history y muestra
   los registros en una tabla legible. JavaScript vanilla, sin frameworks. */

const API_HISTORY_URL = "/api/history";

function getElements() {
  return {
    estado: document.getElementById("estado-carga"),
    tbody: document.getElementById("lista-historial"),
  };
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
     la zona horaria del navegador. */
  return new Date(value).toLocaleString("es-ES", {
    timeZone: "America/Costa_Rica",
  });
}

function appendCell(row, text) {
  const cell = document.createElement("td");
  cell.textContent = text;
  row.appendChild(cell);
}

/* El ticket enlaza a su pantalla de detalle; debajo se muestra su título. */
function appendTicketCell(row, ticketId, ticketTitle) {
  const cell = document.createElement("td");
  const link = document.createElement("a");
  link.className = "enlace-tabla";
  link.href = `detalle.html?id=${ticketId}`;
  link.textContent = `#${ticketId}`;
  cell.appendChild(link);
  if (ticketTitle) {
    const titulo = document.createElement("span");
    titulo.className = "texto-secundario";
    titulo.textContent = ticketTitle;
    cell.appendChild(titulo);
  }
  row.appendChild(cell);
}

/* Registros antiguos (anteriores a la auditoría con usuario) no tienen
   autor autenticado: se guardaron como "Anónimo" o sin autor. Se muestran
   como "Sistema", nunca como "Anónimo". */
function formatAutor(entry) {
  const autor = entry.author ? String(entry.author).trim() : "";
  if (!autor || autor === "Anónimo") return "Sistema";
  return autor;
}

function renderHistorial(entries) {
  const elements = getElements();
  clearRows();

  if (entries.length === 0) {
    showStatus("No hay registros de historial todavía.", "vacio");
    return;
  }

  entries.forEach((entry) => {
    const row = document.createElement("tr");
    const { accion, detalle } = describirHistorial(entry);
    appendCell(row, formatFecha(entry.created_at));
    appendTicketCell(row, entry.ticket_id, entry.ticket_title);
    appendCell(row, formatAutor(entry));
    appendCell(row, accion);
    appendCell(row, detalle);
    elements.tbody.appendChild(row);
  });

  hideStatus();
}

async function fetchHistorial() {
  showStatus("Cargando...", "cargando");
  clearRows();

  let response;
  try {
    /* fetchWithAuth (auth.js) adjunta el Bearer token de la sesión: el
       endpoint /api/history requiere autenticación (401 sin token). */
    response = await fetchWithAuth(API_HISTORY_URL);
  } catch (error) {
    console.error("No se pudo conectar con el servidor:", error);
    showStatus(
      "No se pudo conectar con el servidor. Comprueba que está en ejecución.",
      "error"
    );
    return;
  }

  if (!response.ok) {
    console.error(`La API respondió ${response.status}`);
    showStatus(`Error de API (${response.status}).`, "error");
    return;
  }

  let entries;
  try {
    entries = await response.json();
  } catch (error) {
    console.error("La API no devolvió JSON válido:", error);
    showStatus("Respuesta inválida del servidor.", "error");
    return;
  }

  if (!Array.isArray(entries)) {
    console.error("La API no devolvió una lista:", entries);
    showStatus("Respuesta inválida del servidor.", "error");
    return;
  }

  renderHistorial(entries);
}

function init() {
  fetchHistorial();
}

if (typeof document !== "undefined") {
  document.addEventListener("DOMContentLoaded", init);
}
