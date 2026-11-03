/* Tarea 12 — Alta de tickets desde el formulario, contra POST /api/tickets.
   JavaScript vanilla, sin frameworks ni librerías externas.
   Fase 2: usa fetchWithAuth para incluir el token JWT automáticamente.
   Adjuntos (opcional): se eligen antes (con tamaño y ✕ para quitar; las
   fotos se achican al elegirlas) y, recién creado el ticket, se suben uno
   por uno con POST /api/tickets/{id}/adjuntos (adjSubirUno, js/adjuntos.js).
   Si alguno falla el ticket queda creado igual: se muestra cuál y por qué,
   con el enlace al detalle para reintentarlo. */

const API_TICKETS_URL = "/api/tickets";
const REDIRECT_DELAY_MS = 1500;

let enviando = false;
let redirigiendo = false;
/* Archivos elegidos para adjuntar (ya achicados si eran fotos). */
let elegidos = [];
let preparando = false;

function getElements() {
  return {
    form: document.getElementById("form-crear"),
    title: document.getElementById("title"),
    description: document.getElementById("description"),
    category: document.getElementById("category"),
    priority: document.getElementById("priority"),
    save: document.getElementById("guardar"),
    estado: document.getElementById("estado-carga"),
    adjSubir: document.getElementById("crear-adj-subir"),
    adjFoto: document.getElementById("crear-adj-foto"),
    adjArchivos: document.getElementById("crear-adj-archivos"),
    adjCamara: document.getElementById("crear-adj-camara"),
    adjEstado: document.getElementById("crear-adj-estado"),
    adjLista: document.getElementById("crear-adj-lista"),
    resultado: document.getElementById("crear-resultado"),
    resultadoTitulo: document.getElementById("crear-resultado-titulo"),
    resultadoTexto: document.getElementById("crear-resultado-texto"),
    resultadoFallas: document.getElementById("crear-resultado-fallas"),
    resultadoDetalle: document.getElementById("crear-resultado-detalle"),
  };
}

const hayAdjuntos = () => typeof adjSubirUno === "function";
const maxAdjuntos = () => (typeof adjDatos === "object" && adjDatos ? adjDatos.max_archivos : 10);

function mostrarEstadoAdjuntos(mensaje) {
  const { adjEstado } = getElements();
  if (!adjEstado) return;
  adjEstado.textContent = mensaje || "";
  adjEstado.className = mensaje ? "estado error" : "estado";
  adjEstado.hidden = !mensaje;
}

/* Lista de lo elegido: nombre, tamaño y ✕ para quitarlo. */
function pintarElegidos() {
  const { adjLista, adjSubir } = getElements();
  if (!adjLista) return;
  adjLista.replaceChildren();
  elegidos.forEach((archivo, indice) => {
    const fila = document.createElement("li");
    fila.className = "adjunto adjunto-elegido";
    const nombre = document.createElement("span");
    nombre.className = "adjunto-nombre";
    nombre.textContent = archivo.name;
    const tamano = document.createElement("span");
    tamano.className = "adjunto-meta";
    tamano.textContent = formatoTamano(archivo.size);
    const datos = document.createElement("div");
    datos.className = "adjunto-datos";
    datos.appendChild(nombre);
    datos.appendChild(tamano);
    const quitar = document.createElement("button");
    quitar.type = "button";
    quitar.className = "adjunto-quitar";
    quitar.textContent = "✕";
    quitar.setAttribute("aria-label", `Quitar ${archivo.name}`);
    quitar.addEventListener("click", () => quitarElegido(indice));
    fila.appendChild(datos);
    fila.appendChild(quitar);
    adjLista.appendChild(fila);
  });
  adjLista.hidden = elegidos.length === 0;
  if (adjSubir) adjSubir.disabled = enviando || elegidos.length >= maxAdjuntos();
}

function quitarElegido(indice) {
  if (enviando) return;
  elegidos.splice(indice, 1);
  mostrarEstadoAdjuntos("");
  pintarElegidos();
  /* El foco pasa al ✕ que quedó en ese lugar (o a «Adjuntar archivos»). */
  const { adjLista, adjSubir } = getElements();
  const fila = adjLista.children[Math.min(indice, elegidos.length - 1)];
  const destino = fila ? fila.children[fila.children.length - 1] : adjSubir;
  if (destino && typeof destino.focus === "function") destino.focus();
}

/* Revisa y prepara lo que se eligió (mismas reglas que en el detalle). */
async function agregarElegidos(lista) {
  const archivos = Array.from(lista || []);
  if (archivos.length === 0 || enviando || !hayAdjuntos()) return;
  const elements = getElements();
  const errores = [];
  preparando = true;
  elements.save.disabled = true;
  try {
    for (const original of archivos) {
      if (elegidos.length >= maxAdjuntos()) {
        errores.push(`Se pueden adjuntar hasta ${maxAdjuntos()} archivos por ticket.`);
        break;
      }
      const archivo = await achicarImagen(original);
      const problema = adjProblema(archivo);
      if (problema) errores.push(problema);
      else elegidos.push(archivo);
    }
  } finally {
    preparando = false;
    elements.save.disabled = enviando;
    if (elements.adjArchivos) elements.adjArchivos.value = "";
    if (elements.adjCamara) elements.adjCamara.value = "";
  }
  pintarElegidos();
  mostrarEstadoAdjuntos(errores.join(" "));
}

/* «… : el contenido no corresponde…» sin repetir el nombre del archivo. */
function motivoSinNombre(nombre, motivo) {
  const limpio = String(motivo || "").replace(`«${nombre}»: `, "").replace(`«${nombre}» `, "");
  return limpio.charAt(0).toUpperCase() + limpio.slice(1);
}

async function subirElegidos(ticketId) {
  const fallas = [];
  for (const [i, archivo] of elegidos.entries()) {
    showStatus(`Ticket #${ticketId} creado. Subiendo adjunto ${i + 1} de ${elegidos.length}: ${archivo.name}…`, "cargando");
    const error = await adjSubirUno(ticketId, archivo);
    if (error) fallas.push({ nombre: archivo.name, motivo: motivoSinNombre(archivo.name, error) });
  }
  return fallas;
}

/* El ticket está creado pero algún adjunto no se subió. */
function mostrarFallas(ticketId, fallas, subidos) {
  const elements = getElements();
  elements.form.hidden = true;
  elements.estado.hidden = true;
  elements.resultadoTitulo.textContent = `Ticket #${ticketId} creado`;
  const no = fallas.length === 1 ? "No se pudo subir 1 adjunto" : `No se pudieron subir ${fallas.length} adjuntos`;
  elements.resultadoTexto.textContent = subidos
    ? `${no}; ${subidos === 1 ? "el otro quedó guardado" : `los otros ${subidos} quedaron guardados`}. Puede reintentarlos desde el detalle del ticket.`
    : `${no}. Puede reintentarlos desde el detalle del ticket.`;
  elements.resultadoFallas.replaceChildren();
  fallas.forEach(({ nombre, motivo }) => {
    const fila = document.createElement("li");
    const fuerte = document.createElement("strong");
    fuerte.textContent = nombre;
    fila.appendChild(fuerte);
    fila.appendChild(document.createTextNode(`: ${motivo}`));
    elements.resultadoFallas.appendChild(fila);
  });
  elements.resultadoDetalle.href = `detalle.html?id=${ticketId}`;
  elements.resultado.hidden = false;
  if (typeof elements.resultadoTitulo.focus === "function") elements.resultadoTitulo.focus();
  if (typeof mostrarAviso === "function") mostrarAviso(`Ticket #${ticketId} creado. ${no}.`, "error");
}

function showStatus(message, type) {
  const elements = getElements();
  elements.estado.textContent = message;
  elements.estado.className = `estado ${type}`;
  elements.estado.hidden = false;
}

/* Los errores se muestran como aviso flotante en rojo suave. */
function avisarError(message) {
  showStatus(message, "error");
  getElements().estado.hidden = true;
  if (typeof mostrarAviso === "function") mostrarAviso(message, "error");
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
    return "El servidor rechazó los datos enviados. Revise el formulario.";
  }
  const messages = detail.detail.map((error) => {
    const field = Array.isArray(error.loc) ? error.loc.slice(1).join(".") : "";
    return field ? `${field}: ${error.msg}` : error.msg;
  });
  return `Revise los datos enviados. ${messages.join(" | ")}`;
}

async function createTicket() {
  if (enviando || preparando) return;

  const payload = getPayload();
  const clientError = validatePayload(payload);
  if (clientError) {
    avisarError(clientError);
    return;
  }

  enviando = true;
  const elements = getElements();
  elements.save.disabled = true;
  showStatus("Guardando...", "cargando");

  try {
    const response = await fetchWithAuth(API_TICKETS_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (response.status === 422) {
      const body = await response.json().catch(() => null);
      avisarError(formatValidation(body));
      return;
    }

    if (!response.ok) {
      avisarError(`No se pudo crear el ticket (HTTP ${response.status}). Inténtelo de nuevo.`);
      return;
    }

    const ticket = await response.json();
    /* Desde acá el ticket existe: no se vuelve a habilitar el formulario. */
    redirigiendo = true;
    if (elements.adjSubir) elements.adjSubir.disabled = true;
    if (elements.adjFoto) elements.adjFoto.disabled = true;
    const cantidad = hayAdjuntos() ? elegidos.length : 0;
    if (cantidad) {
      const fallas = await subirElegidos(ticket.id);
      if (fallas.length) {
        mostrarFallas(ticket.id, fallas, cantidad - fallas.length);
        return;
      }
    }
    const conAdjuntos = cantidad === 1 ? " con 1 adjunto" : cantidad ? ` con ${cantidad} adjuntos` : "";
    /* El aviso se ve al llegar al listado. */
    if (typeof avisoPendiente === "function") avisoPendiente(`Ticket #${ticket.id} guardado correctamente${conAdjuntos}.`);
    showStatus(
      `Ticket #${ticket.id} creado correctamente${conAdjuntos}. Redirigiendo al listado...`,
      "exito"
    );
    setTimeout(() => {
      window.location.href = "index.html";
    }, REDIRECT_DELAY_MS);
  } catch (error) {
    avisarError("Error al comunicarse con la API.");
  } finally {
    if (!redirigiendo) {
      enviando = false;
      elements.save.disabled = false;
    }
  }
}

/* Los botones de prioridad guardan su valor en #priority (el que se envía). */
function iniciarPrioridad() {
  if (typeof document.querySelectorAll !== "function") return;
  const elements = getElements();
  document.querySelectorAll('input[name="opcion-prioridad"]').forEach((opcion) => {
    if (opcion.checked) elements.priority.value = opcion.value;
    opcion.addEventListener("change", () => {
      if (opcion.checked) elements.priority.value = opcion.value;
    });
  });
}

function iniciarAdjuntosCrear() {
  const elements = getElements();
  if (!elements.adjSubir || !hayAdjuntos()) return;
  elements.adjSubir.addEventListener("click", () => elements.adjArchivos.click());
  elements.adjArchivos.addEventListener("change", () => agregarElegidos(elements.adjArchivos.files));
  if (elements.adjFoto && elements.adjCamara) {
    elements.adjFoto.hidden = !adjEsTactil();
    elements.adjFoto.addEventListener("click", () => elements.adjCamara.click());
    elements.adjCamara.addEventListener("change", () => agregarElegidos(elements.adjCamara.files));
  }
}

function init() {
  const elements = getElements();
  iniciarPrioridad();
  iniciarAdjuntosCrear();

  elements.form.addEventListener("submit", (event) => {
    event.preventDefault();
    createTicket();
  });
}

if (typeof document !== "undefined") {
  document.addEventListener("DOMContentLoaded", init);
}
