/* Asistente de IA: botón flotante y panel de chat en las páginas internas.
   Envía la conversación a POST /api/asistente; el servidor decide qué datos
   puede usar la IA según el rol de la sesión. La conversación se guarda en
   sessionStorage (se pierde al cerrar la pestaña o la sesión). */

const API_ASISTENTE_URL = "/api/asistente/stream";
const CHAT_KEY = "asistente_chat";
const CHAT_MAX_MENSAJES = 20;

const SUGERENCIAS_POR_ROL = {
  Administrador: ["¿Cuántos tickets críticos hay sin resolver?", "¿Cómo desactivo a un usuario?"],
  Supervisor: ["¿Qué tickets están sin asignar?", "¿Cómo reasigno un ticket?"],
  Técnico: ["¿Qué tickets tengo pendientes?", "¿Cómo cambio el estado de un ticket?"],
  Solicitante: ["¿En qué estado están mis tickets?", "¿Cómo creo un ticket?"],
};

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

/* La API acepta como máximo 20 mensajes alternados que empiezan por user. */
function recortarConversacion(mensajes) {
  let recorte = mensajes.slice(-CHAT_MAX_MENSAJES);
  while (recorte.length && recorte[0].role !== "user") recorte = recorte.slice(1);
  return recorte;
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

function burbuja(mensaje) {
  const clase = `chat-mensaje ${mensaje.role === "user" ? "usuario" : "asistente"}${mensaje.error ? " error" : ""}`;
  const el = crearElemento("div", clase);
  if (mensaje.role === "user" || mensaje.error) el.textContent = mensaje.content;
  else pintarTexto(el, mensaje.content);
  return el;
}

function pintarMensajes(lista, mensajes) {
  lista.replaceChildren();
  const user = getUser();
  if (mensajes.length === 0) {
    const bienvenida = crearElemento(
      "div",
      "chat-mensaje asistente",
      `Hola${user && user.name ? `, ${user.name.split(" ")[0]}` : ""}. Puedo ayudarte con el uso de la aplicación y con los tickets que puedes ver como ${user && user.role ? user.role : "usuario"}.`
    );
    lista.appendChild(bienvenida);
    const sugerencias = crearElemento("div", "chat-sugerencias");
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
  boton.disabled = true;
  const escribiendo = crearElemento("div", "chat-mensaje asistente escribiendo", "Escribiendo…");
  lista.appendChild(escribiendo);
  lista.scrollTop = lista.scrollHeight;
  /* Un modelo local puede tardar en cargarse: se avisa para que no parezca
     colgado. */
  const aviso = setTimeout(() => {
    escribiendo.textContent =
      "Pensando… la primera respuesta puede tardar hasta un minuto mientras se carga el modelo.";
  }, 8000);

  /* La respuesta llega por partes (NDJSON): {"t"} texto, {"fin"} o {"error"}. */
  let respuesta;
  let acumulado = "";
  try {
    const response = await fetchWithAuth(API_ASISTENTE_URL, {
      method: "POST",
      body: JSON.stringify({ messages: recortarConversacion(historial) }),
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
              escribiendo.className = "chat-mensaje asistente";
            }
            acumulado += evento.t;
            pintarTexto(escribiendo, acumulado);
            lista.scrollTop = lista.scrollHeight;
          } else if (evento.error) {
            error = evento.error;
          }
        }
      }
      respuesta = error
        ? { role: "assistant", error: true, content: error }
        : { role: "assistant", content: acumulado || "No tengo una respuesta para eso." };
    }
  } catch (error) {
    console.error("POST /api/asistente/stream:", error);
    respuesta = {
      role: "assistant",
      error: true,
      content: "No se pudo conectar con el servidor. Comprueba que está en ejecución.",
    };
  }

  clearTimeout(aviso);
  /* Si falló, la pregunta se quita del historial para poder reintentarla. */
  const actualizado = respuesta.error ? historial.slice(0, -1) : historial;
  guardarChat([...actualizado, respuesta]);
  pintarMensajes(lista, [...historial, respuesta]);
  chatOcupado = false;
  boton.disabled = false;
  entrada.focus();
}

function crearAsistente() {
  if (!getToken() || document.getElementById("chat-asistente")) return;

  const contenedor = crearElemento("div", "chat-asistente");
  contenedor.id = "chat-asistente";

  const panel = crearElemento("section", "chat-panel");
  panel.id = "chat-panel";
  panel.hidden = true;
  panel.setAttribute("aria-label", "Asistente de IA");

  const cabecera = crearElemento("header", "chat-cabecera");
  const titulos = crearElemento("div");
  titulos.appendChild(crearElemento("strong", "", "Asistente"));
  titulos.appendChild(crearElemento("span", "chat-subtitulo", "Responde según tu rol"));
  const acciones = crearElemento("div", "chat-acciones");
  const limpiar = crearElemento("button", "chat-icono", "Nueva");
  limpiar.type = "button";
  limpiar.title = "Empezar una conversación nueva";
  const cerrar = crearElemento("button", "chat-icono", "✕");
  cerrar.type = "button";
  cerrar.setAttribute("aria-label", "Cerrar asistente");
  acciones.append(limpiar, cerrar);
  cabecera.append(titulos, acciones);

  const lista = crearElemento("div", "chat-lista");
  lista.id = "chat-lista";
  lista.setAttribute("aria-live", "polite");

  const formulario = crearElemento("form", "chat-formulario");
  const entrada = crearElemento("textarea", "chat-entrada");
  entrada.id = "chat-entrada";
  entrada.rows = 2;
  entrada.maxLength = 2000;
  entrada.placeholder = "Escribe tu pregunta…";
  const enviar = crearElemento("button", "chat-enviar", "Enviar");
  enviar.id = "chat-enviar";
  enviar.type = "submit";
  formulario.append(entrada, enviar);

  panel.append(cabecera, lista, formulario);

  const abrir = crearElemento("button", "chat-boton", "Asistente");
  abrir.type = "button";
  abrir.setAttribute("aria-expanded", "false");

  contenedor.append(panel, abrir);
  document.body.appendChild(contenedor);

  const alternar = (mostrar) => {
    panel.hidden = !mostrar;
    abrir.setAttribute("aria-expanded", String(mostrar));
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
  });
  formulario.addEventListener("submit", (event) => {
    event.preventDefault();
    enviarPregunta(entrada.value);
  });
  entrada.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      enviarPregunta(entrada.value);
    }
  });
}

if (typeof document !== "undefined" && typeof document.addEventListener === "function") {
  document.addEventListener("DOMContentLoaded", crearAsistente);
}
