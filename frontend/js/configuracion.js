/* Página de configuración informativa: consulta GET /api/config y
   muestra las constantes del sistema. JavaScript vanilla, sin frameworks. */

const API_CONFIG_URL = "/api/config";

function getElements() {
  return {
    estado: document.getElementById("estado-carga"),
    categorias: document.getElementById("lista-categorias"),
    estados: document.getElementById("lista-estados"),
    prioridades: document.getElementById("lista-prioridades"),
    roles: document.getElementById("lista-roles"),
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

function renderList(listElement, values) {
  listElement.replaceChildren();
  values.forEach((value) => {
    const li = document.createElement("li");
    li.textContent = value;
    listElement.appendChild(li);
  });
}

function renderConfig(config) {
  const elements = getElements();
  renderList(elements.categorias, config.categories);
  renderList(elements.estados, config.states);
  renderList(elements.prioridades, config.priorities);
  renderList(elements.roles, config.roles);
  hideStatus();
}

async function fetchConfig() {
  showStatus("Cargando...", "cargando");

  let response;
  try {
    response = await fetch(API_CONFIG_URL);
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

  let config;
  try {
    config = await response.json();
  } catch (error) {
    console.error("La API no devolvió JSON válido:", error);
    showStatus("Respuesta inválida del servidor.", "error");
    return;
  }

  if (!config || typeof config !== "object") {
    console.error("La API no devolvió un objeto:", config);
    showStatus("Respuesta inválida del servidor.", "error");
    return;
  }

  renderConfig(config);
}

function init() {
  fetchConfig();
}

if (typeof document !== "undefined") {
  document.addEventListener("DOMContentLoaded", init);
}
