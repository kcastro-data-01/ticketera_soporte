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

/* El ID del ticket enlaza a su pantalla de detalle. */
function appendTicketCell(row, ticketId) {
  const cell = document.createElement("td");
  const link = document.createElement("a");
  link.className = "enlace-tabla";
  link.href = `detalle.html?id=${ticketId}`;
  link.textContent = `#${ticketId}`;
  cell.appendChild(link);
  row.appendChild(cell);
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
    appendCell(row, formatFecha(entry.created_at));
    appendTicketCell(row, entry.ticket_id);
    appendCell(row, entry.action || "—");
    appendCell(row, entry.field || "—");
    appendCell(row, entry.old_value || "—");
    appendCell(row, entry.new_value || "—");
    appendCell(row, entry.author || "—");
    elements.tbody.appendChild(row);
  });

  hideStatus();
}

async function fetchHistorial() {
  showStatus("Cargando...", "cargando");
  clearRows();

  let response;
  try {
    response = await fetch(API_HISTORY_URL);
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
