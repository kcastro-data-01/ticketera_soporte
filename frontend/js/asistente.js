/* Asistente de IA: botón flotante y panel de chat en las páginas internas.
   Envía la conversación a POST /api/asistente/stream; el servidor decide qué
   datos puede usar según el rol de la sesión y responde por partes (NDJSON).
   La conversación se guarda en sessionStorage (se pierde al cerrar la
   pestaña o la sesión). */

const API_ASISTENTE_URL = "/api/asistente/stream";
const CHAT_KEY = "asistente_chat";
const CHAT_MAX_MENSAJES = 20;
/* Lo que se muestra si la IA falla o tarda demasiado (el servidor corta a
   los 90 s por llamada; explicar un ticket puede reintentar una vez, así que
   el navegador espera hasta ~3 min antes de rendirse, como el panel). */
const IA_NO_DISPONIBLE = "La IA no está disponible en este momento";
const CHAT_LIMITE_MS = 200000;

/* En el detalle de un ticket (detalle.html?id=N) se envía su número para
   poder preguntar por «este ticket». */
function ticketEnPantalla() {
  try {
    if (!/detalle\.html$/.test(window.location.pathname || "")) return null;
    const id = Number(new URLSearchParams(window.location.search).get("id"));
    return Number.isInteger(id) && id > 0 ? id : null;
  } catch {
    return null;
  }
}

const SUGERENCIAS_POR_ROL = {
  Administrador: ["¿Cuántos tickets críticos hay sin resolver?", "¿Cómo desactivo a un usuario?"],
  Supervisor: ["¿Qué tickets están sin asignar?", "¿Cómo reasigno un ticket?"],
  Técnico: ["¿Qué tickets tengo pendientes?", "¿Cómo cambio el estado de un ticket?"],
  Solicitante: ["¿En qué estado están mis tickets?", "¿Cómo creo un ticket?"],
};

/* Íconos (trazos con currentColor, sin dependencias externas). */
const ICONOS = {
  chispa:
    '<path d="M12 3l1.8 4.9L19 9.7l-5.2 1.8L12 16.4l-1.8-4.9L5 9.7l5.2-1.8z"/>' +
    '<path d="M19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z"/>',
  chat:
    '<path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1.1-4.6A8 8 0 1 1 21 12z"/>' +
    '<path d="M8.5 12h.01M12 12h.01M15.5 12h.01"/>',
  cerrar: '<path d="M6 6l12 12M18 6L6 18"/>',
  nueva: '<path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/>',
  enviar: '<path d="M5 12h14"/><path d="M13 6l6 6-6 6"/>',
};

function icono(nombre, clase = "chat-svg") {
  return `<svg class="${clase}" viewBox="0 0 24 24" aria-hidden="true">${ICONOS[nombre]}</svg>`;
}

let chatOcupado = false;

function leerChat() {
  try {
    const guardado = JSON.parse(sessionStorage.getItem(CHAT_KEY) || "[]");
    return Array.isArray(guardado) ? guardado : [];
  } catch {
    return [];
  }
}

function guardarChat(mensajes) {
  try {
    sessionStorage.setItem(CHAT_KEY, JSON.stringify(mensajes));
  } catch {
    /* Sin almacenamiento la conversación solo vive en esta página. */
  }
}

/* La API acepta como máximo 20 mensajes alternados que empiezan por user.
   Solo se envían role y content. */
function recortarConversacion(mensajes) {
  let recorte = mensajes.slice(-CHAT_MAX_MENSAJES);
  while (recorte.length && recorte[0].role !== "user") recorte = recorte.slice(1);
  return recorte.map((m) => ({ role: m.role, content: m.content }));
}

function crearElemento(tag, clase, texto) {
  const el = document.createElement(tag);
  if (clase) el.className = clase;
  if (texto !== undefined) el.textContent = texto;
  return el;
}

/* Escribe el texto con «#N» como enlace al detalle del ticket. Usa nodos
   de texto: nada de lo que responde el servidor se interpreta como HTML. */
function pintarTexto(elemento, texto) {
  elemento.replaceChildren();
  const partes = String(texto).split(/(#\d+)/);
  partes.forEach((parte) => {
    const numero = /^#(\d+)$/.exec(parte);
    if (numero) {
      const enlace = document.createElement("a");
      enlace.className = "chat-enlace";
      enlace.href = `detalle.html?id=${numero[1]}`;
      enlace.textContent = parte;
      elemento.appendChild(enlace);
    } else if (parte) {
      elemento.appendChild(document.createTextNode(parte));
    }
  });
}

/* Fila del asistente: avatar + contenido (burbuja y, opcional, una nota). */
function filaAsistente() {
  const fila = crearElemento("div", "chat-fila asistente");
  const avatar = crearElemento("div", "chat-avatar");
  avatar.innerHTML = icono("chispa");
  const contenido = crearElemento("div", "chat-contenido");
  fila.append(avatar, contenido);
  return { fila, contenido };
}

const NOTA_FUENTE = {
  directa: "Respuesta del sistema",
  ia: "Generada con IA",
};

function burbuja(mensaje) {
  if (mensaje.role === "user") {
    const fila = crearElemento("div", "chat-fila usuario");
    fila.appendChild(crearElemento("div", "chat-mensaje usuario", mensaje.content));
    return fila;
  }
  const { fila, contenido } = filaAsistente();
  const el = crearElemento("div", `chat-mensaje asistente${mensaje.error ? " error" : ""}`);
  if (mensaje.error) el.textContent = mensaje.content;
  else pintarTexto(el, mensaje.content);
  contenido.appendChild(el);
  if (!mensaje.error && NOTA_FUENTE[mensaje.fuente]) {
    contenido.appendChild(crearElemento("span", "chat-nota", NOTA_FUENTE[mensaje.fuente]));
  }
  return fila;
}

function pintarMensajes(lista, mensajes) {
  lista.replaceChildren();
  const user = getUser();
  if (mensajes.length === 0) {
    const nombre = user && user.name ? `, ${user.name.split(" ")[0]}` : "";
    const rol = user && user.role ? user.role : "usuario";
    lista.appendChild(
      burbuja({
        role: "assistant",
        content: `¡Hola${nombre}! Soy el asistente del Sistema de Tickets. Puedo ayudarte a usar la aplicación y a consultar los tickets que puedes ver como ${rol}.`,
      })
    );
    const sugerencias = crearElemento("div", "chat-sugerencias");
    sugerencias.appendChild(crearElemento("span", "chat-sugerencias-titulo", "Prueba con"));
    (SUGERENCIAS_POR_ROL[user && user.role] || []).forEach((texto) => {
      const chip = crearElemento("button", "chat-sugerencia", texto);
      chip.type = "button";
      chip.addEventListener("click", () => enviarPregunta(texto));
      sugerencias.appendChild(chip);
    });
    lista.appendChild(sugerencias);
  }
  mensajes.forEach((mensaje) => lista.appendChild(burbuja(mensaje)));
  lista.scrollTop = lista.scrollHeight;
}

/* El campo crece con el texto hasta un máximo y el botón Enviar solo se
   activa cuando hay algo escrito. */
function ajustarEntrada(entrada, boton) {
  entrada.style.height = "auto";
  entrada.style.height = `${Math.min(entrada.scrollHeight, 120)}px`;
  boton.disabled = chatOcupado || !entrada.value.trim();
}

async function enviarPregunta(texto) {
  const pregunta = String(texto || "").trim();
  if (!pregunta || chatOcupado) return;
  const lista = document.getElementById("chat-lista");
  const entrada = document.getElementById("chat-entrada");
  const boton = document.getElementById("chat-enviar");

  /* Los avisos de error se muestran pero no se envían a la API. */
  const historial = leerChat().filter((m) => !m.error);
  historial.push({ role: "user", content: pregunta });
  guardarChat(historial);
  pintarMensajes(lista, historial);
  entrada.value = "";

  chatOcupado = true;
  ajustarEntrada(entrada, boton);

  /* Mientras llega la respuesta: tres puntos animados. */
  const { fila, contenido } = filaAsistente();
  const escribiendo = crearElemento("div", "chat-mensaje asistente escribiendo");
  escribiendo.innerHTML = '<span class="chat-puntos"><i></i><i></i><i></i></span>';
  contenido.appendChild(escribiendo);
  lista.appendChild(fila);
  lista.scrollTop = lista.scrollHeight;
  /* Un modelo local puede tardar en cargarse: se avisa para que no parezca
     colgado. */
  const pista = crearElemento(
    "span",
    "chat-nota",
    "Pensando… la primera respuesta puede tardar hasta un minuto mientras se carga el modelo."
  );
  const aviso = setTimeout(() => {
    contenido.appendChild(pista);
    lista.scrollTop = lista.scrollHeight;
  }, 8000);

  /* La respuesta llega por partes (NDJSON): {"t"} texto, {"fin"} o {"error"}. */
  let respuesta;
  let acumulado = "";
  let fuente = "";
  /* Si no termina a tiempo se corta, y la página sigue usable. */
  const control = typeof AbortController === "function" ? new AbortController() : null;
  const limite = control ? setTimeout(() => control.abort(), CHAT_LIMITE_MS) : null;
  try {
    const cuerpo = { messages: recortarConversacion(historial) };
    const ticketId = ticketEnPantalla();
    if (ticketId !== null) cuerpo.ticket_id = ticketId;
    const response = await fetchWithAuth(API_ASISTENTE_URL, {
      method: "POST",
      body: JSON.stringify(cuerpo),
      signal: control ? control.signal : undefined,
    });
    if (!response.ok || !response.body) {
      const body = await response.json().catch(() => null);
      const detalle = body && typeof body.detail === "string" ? body.detail : "";
      respuesta = {
        role: "assistant",
        error: true,
        content: detalle || `El asistente no pudo responder (${response.status}).`,
      };
    } else {
      const lector = response.body.getReader();
      const decodificador = new TextDecoder();
      let pendiente = "";
      let error = "";
      for (;;) {
        const { value, done } = await lector.read();
        if (done) break;
        pendiente += decodificador.decode(value, { stream: true });
        const lineas = pendiente.split("\n");
        pendiente = lineas.pop();
        for (const linea of lineas) {
          if (!linea.trim()) continue;
          const evento = JSON.parse(linea);
          if (typeof evento.t === "string") {
            if (!acumulado) {
              clearTimeout(aviso);
              pista.remove();
              escribiendo.className = "chat-mensaje asistente";
            }
            acumulado += evento.t;
            pintarTexto(escribiendo, acumulado);
            lista.scrollTop = lista.scrollHeight;
          } else if (evento.error) {
            error = evento.error;
          } else if (evento.fin) {
            fuente = evento.fuente || "";
          }
        }
      }
      respuesta =
        error || !acumulado
          ? { role: "assistant", error: true, content: error || IA_NO_DISPONIBLE }
          : { role: "assistant", content: acumulado, fuente };
    }
  } catch (error) {
    console.error("POST /api/asistente/stream:", error);
    const cortado = error && error.name === "AbortError";
    respuesta = {
      role: "assistant",
      error: true,
      content: cortado
        ? IA_NO_DISPONIBLE
        : "No se pudo conectar con el servidor. Comprueba que está en ejecución.",
    };
  }

  clearTimeout(aviso);
  if (limite) clearTimeout(limite);
  /* Si falló, la pregunta se quita del historial para poder reintentarla. */
  const actualizado = respuesta.error ? historial.slice(0, -1) : historial;
  guardarChat([...actualizado, respuesta]);
  pintarMensajes(lista, [...historial, respuesta]);
  chatOcupado = false;
  ajustarEntrada(entrada, boton);
  entrada.focus();
}

function crearAsistente() {
  if (!getToken() || document.getElementById("chat-asistente")) return;
  const user = getUser();

  const contenedor = crearElemento("div", "chat-asistente");
  contenedor.id = "chat-asistente";

  const panel = crearElemento("section", "chat-panel");
  panel.id = "chat-panel";
  panel.hidden = true;
  panel.setAttribute("aria-label", "Asistente de IA");

  /* Cabecera: avatar, título con estado y acciones con ícono. */
  const cabecera = crearElemento("header", "chat-cabecera");
  const identidad = crearElemento("div", "chat-identidad");
  const avatar = crearElemento("div", "chat-avatar grande");
  avatar.innerHTML = icono("chispa");
  const titulos = crearElemento("div");
  titulos.appendChild(crearElemento("strong", "chat-titulo", "Asistente"));
  const estado = crearElemento("span", "chat-subtitulo");
  estado.appendChild(crearElemento("span", "chat-punto-en-linea"));
  estado.appendChild(
    document.createTextNode(`En línea · ${user && user.role ? user.role : "según tu rol"}`)
  );
  titulos.appendChild(estado);
  identidad.append(avatar, titulos);

  const acciones = crearElemento("div", "chat-acciones");
  const limpiar = crearElemento("button", "chat-icono");
  limpiar.type = "button";
  limpiar.title = "Nueva conversación";
  limpiar.setAttribute("aria-label", "Nueva conversación");
  limpiar.innerHTML = icono("nueva");
  const cerrar = crearElemento("button", "chat-icono");
  cerrar.type = "button";
  cerrar.title = "Cerrar";
  cerrar.setAttribute("aria-label", "Cerrar asistente");
  cerrar.innerHTML = icono("cerrar");
  acciones.append(limpiar, cerrar);
  cabecera.append(identidad, acciones);

  const lista = crearElemento("div", "chat-lista");
  lista.id = "chat-lista";
  lista.setAttribute("aria-live", "polite");

  /* Campo en forma de píldora con botón redondo de enviar. */
  const formulario = crearElemento("form", "chat-formulario");
  const caja = crearElemento("div", "chat-caja");
  const entrada = crearElemento("textarea", "chat-entrada");
  entrada.id = "chat-entrada";
  entrada.rows = 1;
  entrada.maxLength = 2000;
  entrada.placeholder = "Escribe tu pregunta…";
  entrada.setAttribute("aria-label", "Tu pregunta");
  const enviar = crearElemento("button", "chat-enviar");
  enviar.id = "chat-enviar";
  enviar.type = "submit";
  enviar.disabled = true;
  enviar.setAttribute("aria-label", "Enviar");
  enviar.innerHTML = icono("enviar");
  caja.append(entrada, enviar);
  formulario.append(
    caja,
    crearElemento("p", "chat-aviso", "Las respuestas generadas con IA pueden contener errores.")
  );

  panel.append(cabecera, lista, formulario);

  /* Botón redondo con ícono de chat; al abrir el panel cambia a una «X». */
  const abrir = crearElemento("button", "chat-boton");
  abrir.type = "button";
  abrir.setAttribute("aria-expanded", "false");
  abrir.setAttribute("aria-label", "Abrir asistente");
  abrir.dataset.tooltip = "Asistente";
  abrir.innerHTML = icono("chat", "chat-boton-icono icono-chat") + icono("cerrar", "chat-boton-icono icono-cerrar");

  contenedor.append(panel, abrir);
  document.body.appendChild(contenedor);

  const alternar = (mostrar) => {
    panel.hidden = !mostrar;
    contenedor.classList.toggle("abierto", mostrar);
    abrir.setAttribute("aria-expanded", String(mostrar));
    abrir.setAttribute("aria-label", mostrar ? "Cerrar asistente" : "Abrir asistente");
    abrir.dataset.tooltip = mostrar ? "Cerrar" : "Asistente";
    if (mostrar) {
      pintarMensajes(lista, leerChat());
      entrada.focus();
    }
  };
  abrir.addEventListener("click", () => alternar(panel.hidden));
  cerrar.addEventListener("click", () => alternar(false));
  limpiar.addEventListener("click", () => {
    guardarChat([]);
    pintarMensajes(lista, []);
    entrada.focus();
  });
  formulario.addEventListener("submit", (event) => {
    event.preventDefault();
    enviarPregunta(entrada.value);
  });
  entrada.addEventListener("input", () => ajustarEntrada(entrada, enviar));
  entrada.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      enviarPregunta(entrada.value);
    }
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !panel.hidden) alternar(false);
  });
}

if (typeof document !== "undefined" && typeof document.addEventListener === "function") {
  document.addEventListener("DOMContentLoaded", crearAsistente);
}
