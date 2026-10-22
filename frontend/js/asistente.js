/* Asistente virtual: botón flotante y panel de chat en las páginas internas.
   Envía la conversación a POST /api/asistente/stream; el servidor decide qué
   datos puede usar según el rol de la sesión y responde por partes (NDJSON).
   La conversación se guarda en sessionStorage (se pierde al cerrar la
   pestaña o la sesión). */

const API_ASISTENTE_URL = "/api/asistente/stream";
const CHAT_KEY = "asistente_chat";
/* Tamaño de la ventana elegido por el usuario (grande o normal). */
const CHAT_GRANDE_KEY = "asistente_grande";
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

/* Preguntas de ejemplo del saludo. El Solicitante no tiene tickets
   asignados ni usa «Explicá», así que recibe otras. */
const SUGERENCIAS_EQUIPO = [
  "¿Cuántos tickets pendientes hay?",
  "¿Qué tickets tengo asignados?",
  "Explique el ticket #1",
];
const SUGERENCIAS_POR_ROL = {
  Administrador: SUGERENCIAS_EQUIPO,
  Supervisor: SUGERENCIAS_EQUIPO,
  Técnico: SUGERENCIAS_EQUIPO,
  Solicitante: [
    "¿Cómo va mi solicitud?",
    "¿Cómo creo un ticket?",
    "¿Cuántos tickets tengo abiertos?",
  ],
};
const SALUDO = "Buen día. ¿En qué le puedo ayudar? Puede consultar, por ejemplo:";

/* Íconos (trazos con currentColor, sin dependencias externas). */
const ICONOS = {
  cerrar: '<path d="M6 6l12 12M18 6L6 18"/>',
  nueva: '<path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/>',
  enviar: '<path d="M5 12h14"/><path d="M13 6l6 6-6 6"/>',
  expandir: '<path d="M14 4h6v6"/><path d="M20 4l-7 7"/><path d="M10 20H4v-6"/><path d="M4 20l7-7"/>',
  contraer: '<path d="M20 4l-6 6"/><path d="M14 4v6h6"/><path d="M4 20l6-6"/><path d="M10 20v-6H4"/>',
  copiar: '<rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V6a2 2 0 0 1 2-2h9"/>',
  abajo: '<path d="M12 5v14"/><path d="M6 13l6 6 6-6"/>',
};

/* Ícono de conversación (dos burbujas): a color, con las partes pintadas
   desde el CSS (color principal y su versión clara), por eso va aparte de
   los íconos de trazo. */
const CONVERSACION =
  '<path class="conv-fondo" d="M10 8h10a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2h-1v3l-4-3h-5a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2z"/>' +
  '<path class="conv-frente" d="M3 2h11a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2H8l-4 3v-3H3a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2z"/>' +
  '<path class="conv-lineas" d="M5 6h7M5 9h4"/>';

function iconoConversacion(clase) {
  return `<svg class="${clase} icono-conversacion" viewBox="0 0 24 24" aria-hidden="true">${CONVERSACION}</svg>`;
}

function icono(nombre, clase = "chat-svg") {
  return `<svg class="${clase}" viewBox="0 0 24 24" aria-hidden="true">${ICONOS[nombre]}</svg>`;
}

let chatOcupado = false;
/* Si el usuario subió para leer, lo nuevo no lo mueve: aparece «Ir al
   final». Se vuelve a seguir al pie al enviar, al abrir o al bajar. */
let chatSeguirAbajo = true;

function seguirAlFinal(lista) {
  const irFinal = document.getElementById("chat-ir-final");
  if (chatSeguirAbajo) {
    lista.scrollTop = lista.scrollHeight;
    if (irFinal) irFinal.hidden = true;
  } else if (irFinal) {
    irFinal.hidden = false;
  }
}

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

/* Escribe una línea con «**negrita**» y «#N» como enlace al detalle del
   ticket. Usa nodos de texto: nada de lo que responde el servidor se
   interpreta como HTML. */
function pintarLinea(elemento, texto) {
  String(texto).split(/(\*\*[^*\n]+\*\*)/).forEach((trozo) => {
    const negrita = /^\*\*([^*\n]+)\*\*$/.exec(trozo);
    const destino = negrita ? elemento.appendChild(document.createElement("strong")) : elemento;
    (negrita ? negrita[1] : trozo).split(/(#\d+)/).forEach((parte) => {
      const numero = /^#(\d+)$/.exec(parte);
      if (numero) {
        const enlace = document.createElement("a");
        enlace.className = "chat-enlace";
        enlace.href = `detalle.html?id=${numero[1]}`;
        enlace.textContent = parte;
        destino.appendChild(enlace);
      } else if (parte) {
        destino.appendChild(document.createTextNode(parte));
      }
    });
  });
}

/* Líneas que se muestran como título: «Resumen:», «Pasos sugeridos:» o
   «## Resumen» (pocas palabras, sin otra puntuación). */
function tituloDeLinea(linea) {
  const markdown = /^#{1,3}\s+(.+)$/.exec(linea);
  if (markdown) return markdown[1].replace(/\*\*/g, "");
  const limpia = linea.replace(/\*\*/g, "");
  if (/^[A-ZÁÉÍÓÚÑ][A-Za-zÁÉÍÓÚÑáéíóúñü ]{0,40}:$/.test(limpia) && limpia.split(" ").length <= 4) return limpia;
  return null;
}

/* Arma la respuesta con párrafos, listas («- » o «1. ») y títulos en
   negrita, siempre con createElement y textContent. */
function pintarTexto(elemento, texto) {
  elemento.replaceChildren();
  let lista = null;
  let parrafo = null;
  String(texto).split("\n").forEach((cruda) => {
    const linea = cruda.trim();
    const vineta = /^[-*•]\s+(.*)$/.exec(linea);
    const numerada = /^\d+[.)]\s+(.*)$/.exec(linea);
    if (vineta || numerada) {
      const tipo = vineta ? "ul" : "ol";
      if (!lista || lista.tag !== tipo) {
        lista = { tag: tipo, el: elemento.appendChild(crearElemento(tipo, "chat-lista-respuesta")) };
      }
      pintarLinea(lista.el.appendChild(document.createElement("li")), (vineta || numerada)[1]);
      parrafo = null;
      return;
    }
    lista = null;
    if (!linea) {
      parrafo = null;
      return;
    }
    const titulo = tituloDeLinea(linea);
    if (titulo) {
      elemento.appendChild(crearElemento("strong", "chat-titulo-respuesta", titulo));
      parrafo = null;
      return;
    }
    if (parrafo) parrafo.appendChild(document.createElement("br"));
    else parrafo = elemento.appendChild(crearElemento("p", "chat-parrafo"));
    pintarLinea(parrafo, linea);
  });
}

/* Tickets mencionados (#N) en una respuesta: hasta 3 tarjetitas con el
   título, el estado y la prioridad. Se consultan una vez por página con
   GET /api/tickets/{id}; si no hay permiso o falla, no se muestra nada. */
const CHAT_MAX_TARJETAS = 3;
const ticketsConsultados = new Map();

function consultarTicket(id) {
  if (!ticketsConsultados.has(id)) {
    ticketsConsultados.set(
      id,
      fetchWithAuth(`/api/tickets/${id}`)
        .then((response) => (response.ok ? response.json() : null))
        .catch(() => null)
    );
  }
  return ticketsConsultados.get(id);
}

function tarjetaTicket(ticket) {
  const tarjeta = crearElemento("a", "chat-ticket");
  tarjeta.href = `detalle.html?id=${ticket.id}`;
  const cabeza = crearElemento("span", "chat-ticket-cabeza");
  cabeza.append(
    crearElemento("span", "chat-ticket-id", `#${ticket.id}`),
    crearElemento("span", "chat-ticket-titulo", ticket.title)
  );
  const etiquetas = crearElemento("span", "chat-ticket-etiquetas");
  etiquetas.appendChild(crearElemento("span", claseBadge(ticket.state), ticket.state));
  /* El Solicitante no ve la prioridad, igual que en el listado. */
  const user = getUser();
  if (!(user && user.role === "Solicitante")) {
    etiquetas.appendChild(crearElemento("span", claseBadge(ticket.priority), ticket.priority));
  }
  tarjeta.append(cabeza, etiquetas);
  return tarjeta;
}

function tarjetasMencionadas(texto) {
  const ids = [...new Set([...String(texto).matchAll(/#(\d+)/g)].map((m) => Number(m[1])))]
    .filter((id) => id > 0)
    .slice(0, CHAT_MAX_TARJETAS);
  if (!ids.length) return null;
  const contenedor = crearElemento("div", "chat-tickets");
  ids.forEach((id) => {
    /* Un lugar por ticket para que queden en el orden en que se nombran. */
    const lugar = contenedor.appendChild(crearElemento("div", "chat-ticket-lugar"));
    consultarTicket(id).then((ticket) => {
      if (!ticket || ticket.id === undefined) return;
      lugar.appendChild(tarjetaTicket(ticket));
      const lista = document.getElementById("chat-lista");
      if (lista) seguirAlFinal(lista);
    });
  });
  return contenedor;
}

/* Fila del asistente: el mensaje y, opcional, una nota debajo. */
function filaAsistente() {
  const fila = crearElemento("div", "chat-fila asistente");
  const contenido = crearElemento("div", "chat-contenido");
  fila.append(contenido);
  return { fila, contenido };
}

/* Hora del mensaje (HH:MM) o null si no se guardó (saludo, chats viejos). */
function horaDeMensaje(mensaje) {
  const fecha = mensaje.hora ? new Date(mensaje.hora) : null;
  if (!fecha || Number.isNaN(fecha.getTime())) return null;
  const dos = (n) => String(n).padStart(2, "0");
  return `${dos(fecha.getHours())}:${dos(fecha.getMinutes())}`;
}

/* Botón con ícono que copia la respuesta (sin los «**» del formato) y
   muestra «Copiado» un segundo. */
function botonCopiar(contenido) {
  const boton = crearElemento("button", "chat-copiar");
  boton.type = "button";
  boton.title = "Copiar";
  boton.setAttribute("aria-label", "Copiar respuesta");
  boton.innerHTML = icono("copiar");
  const aviso = boton.appendChild(crearElemento("span", "chat-copiado", "Copiado"));
  aviso.hidden = true;
  let reloj = null;
  boton.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(String(contenido).replace(/\*\*/g, ""));
    } catch {
      return;
    }
    aviso.hidden = false;
    boton.classList.add("copiado");
    clearTimeout(reloj);
    reloj = setTimeout(() => {
      aviso.hidden = true;
      boton.classList.remove("copiado");
    }, 1000);
  });
  return boton;
}

/* Debajo de la burbuja: la hora en gris y, en las respuestas, «Copiar». */
function pieDeMensaje(mensaje, copiable = false) {
  const pie = crearElemento("div", "chat-pie");
  const hora = horaDeMensaje(mensaje);
  if (hora) {
    const tiempo = crearElemento("time", "chat-hora", hora);
    tiempo.setAttribute("datetime", mensaje.hora);
    pie.appendChild(tiempo);
  }
  if (copiable) pie.appendChild(botonCopiar(mensaje.content));
  return pie.children.length ? pie : null;
}

function burbuja(mensaje) {
  if (mensaje.role === "user") {
    const fila = crearElemento("div", "chat-fila usuario");
    const contenido = fila.appendChild(crearElemento("div", "chat-contenido"));
    contenido.appendChild(crearElemento("div", "chat-mensaje usuario", mensaje.content));
    const pie = pieDeMensaje(mensaje);
    if (pie) contenido.appendChild(pie);
    return fila;
  }
  const { fila, contenido } = filaAsistente();
  const el = crearElemento("div", `chat-mensaje asistente${mensaje.error ? " error" : " chat-formato"}`);
  if (mensaje.error) el.textContent = mensaje.content;
  else pintarTexto(el, mensaje.content);
  /* La fuente (sistema o IA) se guarda pero no se muestra: abajo queda el
     aviso general «Las respuestas generadas con IA pueden contener errores». */
  contenido.appendChild(el);
  const pie = pieDeMensaje(mensaje, !mensaje.error && !mensaje.saludo);
  if (pie) contenido.appendChild(pie);
  if (!mensaje.error) {
    const tarjetas = tarjetasMencionadas(mensaje.content);
    if (tarjetas) contenido.appendChild(tarjetas);
  }
  return fila;
}

/* Separador al inicio de la conversación: «Hoy» (o «Ayer» / la fecha si
   la conversación guardada empezó otro día). */
function separadorDeFecha(mensajes) {
  const primera = mensajes.find((m) => m.hora);
  const fecha = primera ? new Date(primera.hora) : new Date();
  const hoy = new Date();
  const ayer = new Date(hoy.getFullYear(), hoy.getMonth(), hoy.getDate() - 1);
  const mismoDia = (a, b) => a.toDateString() === b.toDateString();
  const dos = (n) => String(n).padStart(2, "0");
  let texto = `${dos(fecha.getDate())}/${dos(fecha.getMonth() + 1)}/${fecha.getFullYear()}`;
  if (Number.isNaN(fecha.getTime()) || mismoDia(fecha, hoy)) texto = "Hoy";
  else if (mismoDia(fecha, ayer)) texto = "Ayer";
  const separador = crearElemento("div", "chat-separador");
  separador.setAttribute("role", "separator");
  separador.setAttribute("aria-label", texto);
  separador.appendChild(crearElemento("span", "", texto));
  return separador;
}

function pintarMensajes(lista, mensajes) {
  lista.replaceChildren(separadorDeFecha(mensajes));
  const user = getUser();
  if (mensajes.length === 0) {
    lista.appendChild(burbuja({ role: "assistant", content: SALUDO, saludo: true }));
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
  seguirAlFinal(lista);
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

  chatSeguirAbajo = true;

  /* Los avisos de error se muestran pero no se envían a la API. */
  const historial = leerChat().filter((m) => !m.error);
  historial.push({ role: "user", content: pregunta, hora: new Date().toISOString() });
  guardarChat(historial);
  pintarMensajes(lista, historial);
  entrada.value = "";

  chatOcupado = true;
  ajustarEntrada(entrada, boton);

  /* Mientras llega la respuesta: «Escribiendo…» en gris. */
  const { fila, contenido } = filaAsistente();
  const escribiendo = crearElemento("div", "chat-mensaje asistente escribiendo", "Escribiendo…");
  contenido.appendChild(escribiendo);
  lista.appendChild(fila);
  seguirAlFinal(lista);
  /* Un modelo local puede tardar en cargarse: se avisa para que no parezca
     colgado. */
  const pista = crearElemento(
    "span",
    "chat-nota",
    "La primera respuesta puede tardar hasta un minuto. Gracias por su paciencia."
  );
  const aviso = setTimeout(() => {
    contenido.appendChild(pista);
    seguirAlFinal(lista);
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
              escribiendo.className = "chat-mensaje asistente chat-formato";
            }
            acumulado += evento.t;
            pintarTexto(escribiendo, acumulado);
            seguirAlFinal(lista);
          } else if (typeof evento.reemplazo === "string") {
            /* La respuesta de la IA no servía: se cambia por la del sistema. */
            acumulado = evento.reemplazo;
            pintarTexto(escribiendo, acumulado);
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
        : "No se pudo conectar con el servidor. Verifique que esté en funcionamiento.",
    };
  }

  clearTimeout(aviso);
  if (limite) clearTimeout(limite);
  respuesta.hora = new Date().toISOString();
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
  panel.setAttribute("aria-label", "Asistente virtual");

  /* Cabecera: ícono del chat, título con estado y acciones con ícono. */
  const cabecera = crearElemento("header", "chat-cabecera");
  const identidad = crearElemento("div", "chat-identidad");
  const iconoCabecera = crearElemento("span", "chat-cabecera-icono");
  iconoCabecera.innerHTML = iconoConversacion("chat-svg");
  const titulos = crearElemento("div");
  titulos.appendChild(crearElemento("strong", "chat-titulo", "Asistente virtual"));
  const estado = crearElemento("span", "chat-subtitulo");
  estado.appendChild(crearElemento("span", "chat-punto-en-linea"));
  estado.appendChild(document.createTextNode("En línea"));
  /* El rol queda a la vista al pasar el mouse (y en el saludo del chat). */
  estado.title = user && user.role ? `Respuestas según su rol: ${user.role}` : "Respuestas según su rol";
  titulos.appendChild(estado);
  identidad.append(iconoCabecera, titulos);

  const acciones = crearElemento("div", "chat-acciones");
  const agrandar = crearElemento("button", "chat-icono chat-agrandar");
  agrandar.type = "button";
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
  acciones.append(agrandar, limpiar, cerrar);
  cabecera.append(identidad, acciones);

  const lista = crearElemento("div", "chat-lista");
  lista.id = "chat-lista";
  lista.setAttribute("aria-live", "polite");

  /* Flecha «Ir al final» sobre la conversación. */
  const irFinal = crearElemento("button", "chat-ir-final");
  irFinal.id = "chat-ir-final";
  irFinal.type = "button";
  irFinal.hidden = true;
  irFinal.title = "Ir al final";
  irFinal.setAttribute("aria-label", "Ir al final");
  irFinal.innerHTML = icono("abajo");
  const cuerpo = crearElemento("div", "chat-cuerpo");
  cuerpo.append(lista, irFinal);
  lista.addEventListener("scroll", () => {
    chatSeguirAbajo = lista.scrollHeight - lista.scrollTop - lista.clientHeight < 40;
    if (chatSeguirAbajo) irFinal.hidden = true;
  });
  irFinal.addEventListener("click", () => {
    chatSeguirAbajo = true;
    seguirAlFinal(lista);
  });

  /* Campo rectangular con el botón de enviar a la derecha. */
  const formulario = crearElemento("form", "chat-formulario");
  const caja = crearElemento("div", "chat-caja");
  const entrada = crearElemento("textarea", "chat-entrada");
  entrada.id = "chat-entrada";
  entrada.rows = 1;
  entrada.maxLength = 2000;
  entrada.placeholder = "Ingrese su consulta…";
  entrada.setAttribute("aria-label", "Su consulta");
  const enviar = crearElemento("button", "chat-enviar");
  enviar.id = "chat-enviar";
  enviar.type = "submit";
  enviar.disabled = true;
  enviar.setAttribute("aria-label", "Enviar");
  enviar.innerHTML = icono("enviar");
  caja.append(entrada, enviar);
  formulario.append(
    caja,
    crearElemento(
      "p",
      "chat-aviso",
      "Las respuestas automáticas pueden contener errores. Verifique la información importante."
    )
  );

  panel.append(cabecera, cuerpo, formulario);

  /* Cuadrado del color principal con el ícono de conversación; al abrir
     cambia a una «X». */
  const abrir = crearElemento("button", "chat-boton");
  abrir.type = "button";
  abrir.setAttribute("aria-expanded", "false");
  abrir.setAttribute("aria-label", "Abrir asistente virtual");
  abrir.dataset.tooltip = "Asistente virtual";
  abrir.innerHTML =
    iconoConversacion("chat-boton-icono icono-chat") + icono("cerrar", "chat-boton-icono icono-cerrar");

  contenedor.append(panel, abrir);
  document.body.appendChild(contenedor);

  /* Ventana grande o normal, recordada entre páginas. */
  const ponerGrande = (grande) => {
    contenedor.classList.toggle("grande", grande);
    const texto = grande ? "Achicar ventana" : "Agrandar ventana";
    agrandar.title = texto;
    agrandar.setAttribute("aria-label", texto);
    agrandar.setAttribute("aria-pressed", String(grande));
    agrandar.innerHTML = icono(grande ? "contraer" : "expandir");
  };
  let grande = false;
  try {
    grande = localStorage.getItem(CHAT_GRANDE_KEY) === "1";
  } catch {
    /* Sin almacenamiento arranca en tamaño normal. */
  }
  ponerGrande(grande);
  agrandar.addEventListener("click", () => {
    grande = !grande;
    ponerGrande(grande);
    try {
      localStorage.setItem(CHAT_GRANDE_KEY, grande ? "1" : "0");
    } catch {
      /* Si no se puede guardar, vale solo para esta página. */
    }
  });

  /* Abre y cierra al instante, sin animaciones. */
  let abierto = false;
  const alternar = (mostrar) => {
    if (mostrar === abierto) return;
    abierto = mostrar;
    abrir.setAttribute("aria-expanded", String(mostrar));
    abrir.setAttribute("aria-label", mostrar ? "Cerrar asistente virtual" : "Abrir asistente virtual");
    abrir.dataset.tooltip = mostrar ? "Cerrar" : "Asistente virtual";
    panel.hidden = !mostrar;
    contenedor.classList.toggle("abierto", mostrar);
    if (mostrar) {
      chatSeguirAbajo = true;
      pintarMensajes(lista, leerChat());
      entrada.focus();
    }
  };
  abrir.addEventListener("click", () => alternar(!abierto));
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
    if (event.key === "Escape" && abierto) alternar(false);
  });
}

if (typeof document !== "undefined" && typeof document.addEventListener === "function") {
  document.addEventListener("DOMContentLoaded", crearAsistente);
}
