/* Pantalla «Historial» (Administrador y Técnico): los cambios hechos en los
   tickets, agrupados por persona. Mismo armado que Departamentos: a la
   izquierda la lista de personas (pestañas: role="tab"), con «Todas las
   personas» arriba y «Sistema» para los cambios automáticos; a la derecha el
   detalle de la elegida: período, búsqueda, cajas con números y los cambios
   agrupados por día (50 por vez, con «Ver más»).
   Datos: GET /api/history/resumen (personas y cajas) y GET /api/history
   (los cambios, por páginas). Todo se pinta con textContent (nunca como
   HTML) y, por la CSP, sin atributos style="". La persona y el período
   quedan en la dirección (#persona=12&periodo=30). */

const API_HISTORY_URL = "/api/history";
const API_HISTORY_RESUMEN_URL = "/api/history/resumen";
const CAMBIOS_POR_PAGINA = 50;
const PERIODOS_HISTORIAL = ["hoy", "7", "30"];
const PERIODO_POR_DEFECTO = "7";
const PERSONA_TODAS = "todas";
const PERSONA_SISTEMA = "sistema";
const ESPERA_BUSQUEDA_MS = 300;

const DIAS_SEMANA = ["domingo", "lunes", "martes", "miércoles", "jueves", "viernes", "sábado"];
const MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
  "agosto", "septiembre", "octubre", "noviembre", "diciembre"];

const ICONO_TODAS =
  '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/>' +
  '<circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.9M16 3.1a4 4 0 0 1 0 7.8"/></svg>';
const ICONO_SISTEMA =
  '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="4" y="4" width="16" height="16" rx="2"/>' +
  '<path d="M9 9h6v6H9zM9 1v3M15 1v3M9 20v3M15 20v3M20 9h3M20 14h3M1 9h3M1 14h3"/></svg>';

const historialEstado = {
  persona: PERSONA_TODAS,
  periodo: PERIODO_POR_DEFECTO,
  buscar: "",
  personas: [],      /* todas las que vinieron del servidor */
  visibles: [],      /* las de la lista: «Todas» + las con cambios + la elegida */
  total: 0,          /* cambios del período (todas las personas) */
  cajas: null,
  cargados: 0,       /* cambios ya pintados */
  ultimoDia: "",     /* clave del último grupo de día pintado */
  listaDia: null,    /* su <ul>, donde sigue «Ver más» si es el mismo día */
  pedido: 0,         /* para descartar respuestas viejas */
};

function histNodo(tag, clase, texto) {
  const el = document.createElement(tag);
  if (clase) el.className = clase;
  if (texto !== undefined) el.textContent = texto;
  return el;
}

function textoCambios(n) {
  return n === 1 ? "1 cambio" : `${n} cambios`;
}

/* Registros antiguos (anteriores a la auditoría con usuario) no tienen
   autor autenticado: se guardaron como "Anónimo" o sin autor. Se muestran
   como "Sistema", nunca como "Anónimo". */
function formatAutor(entry) {
  const autor = entry.author ? String(entry.author).trim() : "";
  if (!autor || autor === "Anónimo") return "Sistema";
  return autor;
}

/* ---------- Dirección (#persona=12&periodo=30) ---------- */

function leerHash(hash) {
  const params = new URLSearchParams(String(hash || "").replace(/^#/, ""));
  const persona = String(params.get("persona") || "").trim().toLowerCase();
  const periodo = params.get("periodo");
  return {
    persona: persona === PERSONA_SISTEMA || /^\d+$/.test(persona) ? persona : PERSONA_TODAS,
    periodo: PERIODOS_HISTORIAL.includes(periodo) ? periodo : PERIODO_POR_DEFECTO,
  };
}

function armarHash(persona, periodo) {
  const params = new URLSearchParams();
  params.set("persona", persona);
  params.set("periodo", periodo);
  return `#${params.toString()}`;
}

function guardarHash() {
  if (typeof window === "undefined" || !window.history || typeof window.history.replaceState !== "function") return;
  window.history.replaceState(null, "", armarHash(historialEstado.persona, historialEstado.periodo));
}

/* ---------- Frase de cada cambio ---------- */

const CAMPOS_FRASE = {
  title: "el título",
  description: "la descripción",
  category: "la categoría",
  priority: "la prioridad",
  state: "el estado",
};

/* Lo que hizo, en una frase que sigue al nombre: «comentó «hola»»,
   «cambió el estado: Nuevo → En proceso», «asignó el ticket a Daniel». */
function fraseCambio(entry) {
  const antes = entry.old_value;
  const despues = entry.new_value;
  switch (entry.action) {
    case "created":
      if (entry.field === "correo") return "creó el ticket desde un correo";
      return despues ? `creó el ticket (asignado automáticamente a ${despues})` : "creó el ticket";
    case "updated": {
      const campo = CAMPOS_FRASE[entry.field] || (entry.field ? `«${entry.field}»` : "un dato");
      const largo = entry.field === "title" || entry.field === "description";
      const valor = (v) => (largo ? `«${recortar(v ?? "", 60)}»` : (v ?? "—"));
      return `cambió ${campo}: ${valor(antes)} → ${valor(despues)}`;
    }
    case "assigned":
      return despues ? `asignó el ticket a ${nombreAsignacion(despues)}` : "quitó la asignación";
    case "area_changed":
      return despues ? `cambió el departamento a ${despues}` : "dejó el ticket sin departamento";
    case "Cierre automático":
      return "lo cerró automáticamente";
    case "Reabierto por respuesta":
      return "lo reabrió por la respuesta del solicitante";
    case "Cambio de estado":
    case "state_changed":
      return `cambió el estado: ${antes ?? "—"} → ${despues ?? "—"}`;
    case "commented":
      return despues ? `comentó «${recortar(despues, 80)}»` : "comentó";
    case "attachment_added":
      return `adjuntó ${despues ? recortar(despues, 80) : "un archivo"}${entry.field === "correo" ? " (por correo)" : ""}`;
    case "attachments_skipped":
      return "no se guardaron adjuntos del correo";
    case "attachment_deleted":
      return `eliminó el adjunto ${antes ? recortar(antes, 80) : ""}`.trim();
    default: {
      const { accion, detalle } = describirHistorial(entry);
      const inicio = accion.charAt(0).toLowerCase() + accion.slice(1);
      return detalle && detalle !== "—" ? `${inicio}: ${detalle}` : inicio;
    }
  }
}

/* ---------- Días («Hoy · jueves 12 de noviembre») ---------- */

/* Fecha de Costa Rica («dd/mm/aaaa», de formatearFechaHora) → partes. */
function diaCostaRica(valor) {
  const texto = formatearFechaHora(valor, { parte: "fecha" });
  const m = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(texto);
  if (!m) return null;
  return { clave: `${m[3]}-${m[2]}-${m[1]}`, anio: Number(m[3]), mes: Number(m[2]), dia: Number(m[1]) };
}

function tituloDia(valor, ahora = new Date()) {
  const dia = diaCostaRica(valor);
  if (!dia) return { clave: "", texto: "Sin fecha" };
  const utc = Date.UTC(dia.anio, dia.mes - 1, dia.dia);
  const semana = DIAS_SEMANA[new Date(utc).getUTCDay()];
  const fecha = `${semana} ${dia.dia} de ${MESES[dia.mes - 1]}`;
  const hoy = diaCostaRica(ahora);
  const hoyUtc = hoy ? Date.UTC(hoy.anio, hoy.mes - 1, hoy.dia) : NaN;
  const diferencia = Math.round((hoyUtc - utc) / 86400000);
  let texto = fecha.charAt(0).toUpperCase() + fecha.slice(1);
  if (diferencia === 0) texto = `Hoy · ${fecha}`;
  else if (diferencia === 1) texto = `Ayer · ${fecha}`;
  else if (hoy && dia.anio !== hoy.anio) texto = `${texto} de ${dia.anio}`;
  return { clave: dia.clave, texto };
}

/* ---------- Lista de personas ---------- */

function personaTodas() {
  return { clave: PERSONA_TODAS, nombre: "Todas las personas", rol: null, departamento: null, cambios: historialEstado.total };
}

/* «Todas» arriba y después las que tienen cambios en el período (como las
   ordena el servidor: más cambios primero). La elegida se muestra aunque no
   tenga cambios en el período. */
function personasVisibles(personas, elegida) {
  return [personaTodas(), ...personas.filter((p) => p.cambios > 0 || p.clave === elegida)];
}

function avatarPersona(persona) {
  const avatar = histNodo("span", "hist-avatar");
  avatar.setAttribute("aria-hidden", "true");
  if (persona.clave === PERSONA_TODAS) {
    avatar.className += " hist-avatar-icono";
    avatar.innerHTML = ICONO_TODAS;
  } else if (persona.clave === PERSONA_SISTEMA) {
    avatar.className += " hist-avatar-icono hist-avatar-sistema";
    avatar.innerHTML = ICONO_SISTEMA;
  } else {
    avatar.className += ` tono-avatar-${tonoAvatar(persona.nombre)}`;
    avatar.textContent = inicialesDe(persona.nombre);
  }
  return avatar;
}

const MEDIA_LISTA_HORIZONTAL_HIST = "(max-width: 900px)";

function orientarListaHistorial(lista) {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") return;
  const consulta = window.matchMedia(MEDIA_LISTA_HORIZONTAL_HIST);
  const aplicar = () => lista.setAttribute("aria-orientation", consulta.matches ? "horizontal" : "vertical");
  aplicar();
  if (!lista.dataset || lista.dataset.orientada) return;
  lista.dataset.orientada = "1";
  if (typeof consulta.addEventListener === "function") consulta.addEventListener("change", aplicar);
}

function pintarListaPersonas() {
  const lista = document.getElementById("hist-lista");
  const visibles = personasVisibles(historialEstado.personas, historialEstado.persona);
  historialEstado.visibles = visibles;
  lista.replaceChildren();
  orientarListaHistorial(lista);
  visibles.forEach((persona, indice) => {
    const boton = histNodo("button", "depto-boton hist-persona");
    boton.type = "button";
    boton.id = `tab-persona-${persona.clave}`;
    boton.setAttribute("role", "tab");
    boton.setAttribute("aria-controls", "hist-detalle");
    const elegida = persona.clave === historialEstado.persona;
    boton.setAttribute("aria-selected", elegida ? "true" : "false");
    boton.tabIndex = elegida ? 0 : -1;
    if (elegida) boton.className += " elegido";
    if (persona.clave === PERSONA_TODAS) boton.className += " hist-todas";
    if (persona.clave === PERSONA_SISTEMA) boton.className += " hist-sistema";
    if (boton.dataset) boton.dataset.persona = persona.clave;

    boton.appendChild(avatarPersona(persona));
    const nombre = histNodo("span", "depto-boton-nombre", persona.nombre);
    nombre.title = persona.nombre;
    boton.appendChild(nombre);
    boton.appendChild(histNodo("span", "depto-boton-abiertos", textoCambios(persona.cambios)));
    const pastilla = histNodo("span", "depto-pastilla", String(persona.cambios));
    pastilla.setAttribute("aria-hidden", "true");
    boton.appendChild(pastilla);

    boton.addEventListener("click", () => elegirPersona(persona.clave, { foco: false }));
    boton.addEventListener("keydown", (evento) => moverEntrePersonas(evento, indice));
    lista.appendChild(boton);
  });
}

/* Flechas, Inicio y Fin entre las pestañas (activación automática). */
function moverEntrePersonas(evento, indice) {
  const total = historialEstado.visibles.length;
  let destino = null;
  if (evento.key === "ArrowDown" || evento.key === "ArrowRight") destino = (indice + 1) % total;
  else if (evento.key === "ArrowUp" || evento.key === "ArrowLeft") destino = (indice - 1 + total) % total;
  else if (evento.key === "Home") destino = 0;
  else if (evento.key === "End") destino = total - 1;
  if (destino === null) return;
  evento.preventDefault();
  elegirPersona(historialEstado.visibles[destino].clave, { foco: true });
}

function marcarElegida(foco) {
  const lista = document.getElementById("hist-lista");
  Array.from(lista.children || []).forEach((boton) => {
    const elegida = boton.dataset && boton.dataset.persona === historialEstado.persona;
    boton.setAttribute("aria-selected", elegida ? "true" : "false");
    boton.tabIndex = elegida ? 0 : -1;
    const base = String(boton.className).replace(/\s*\belegido\b/g, "");
    boton.className = elegida ? `${base} elegido` : base;
    if (elegida && foco && typeof boton.focus === "function") boton.focus();
    if (elegida && foco && typeof boton.scrollIntoView === "function") {
      boton.scrollIntoView({ block: "nearest", inline: "nearest" });
    }
  });
  document.getElementById("hist-detalle").setAttribute("aria-labelledby", `tab-persona-${historialEstado.persona}`);
}

function elegirPersona(clave, { foco = false } = {}) {
  if (clave === historialEstado.persona) {
    marcarElegida(foco);
    return;
  }
  historialEstado.persona = clave;
  marcarElegida(foco);
  guardarHash();
  actualizarHistorial({ repintarLista: false });
}

/* ---------- Detalle ---------- */

function personaElegida() {
  return historialEstado.visibles.find((p) => p.clave === historialEstado.persona)
    || historialEstado.personas.find((p) => p.clave === historialEstado.persona)
    || personaTodas();
}

function pintarCabeceraPersona() {
  const persona = historialEstado.persona === PERSONA_TODAS ? personaTodas() : personaElegida();
  document.getElementById("hist-nombre").textContent = persona.nombre;
  const rol = document.getElementById("hist-rol");
  const partes = persona.clave === PERSONA_TODAS
    ? ["Técnicos, administradores, solicitantes y Sistema"]
    : [persona.rol, persona.departamento].filter(Boolean);
  rol.textContent = partes.join(" · ");
  rol.hidden = !partes.length;
  document.getElementById("hist-total").textContent = `${textoCambios(persona.cambios || 0)} en el período`;
}

function cajaHistorial(etiqueta, valor, clase) {
  const li = histNodo("li", `depto-caja ${clase || ""}`.trim());
  li.appendChild(histNodo("span", "depto-caja-numero", String(valor)));
  li.appendChild(histNodo("span", "depto-caja-etiqueta", etiqueta));
  return li;
}

function pintarCajasHistorial(cajas) {
  const lista = document.getElementById("hist-cajas");
  const c = cajas || {};
  lista.replaceChildren(
    cajaHistorial("Cambios", c.cambios || 0, "depto-caja-abiertos"),
    cajaHistorial("Tickets tocados", c.tickets || 0),
    cajaHistorial("Comentarios", c.comentarios || 0),
    cajaHistorial("Cambios de estado", c.cambios_estado || 0),
  );
}

/* Una línea por cambio: hora, (con «Todas» también quién), el ticket y lo
   que hizo. */
function lineaCambio(entry, conAutor) {
  const li = histNodo("li", conAutor ? "hist-linea con-autor" : "hist-linea");
  const hora = histNodo("time", "hist-hora", formatearFechaHora(entry.created_at, { parte: "hora" }));
  if (entry.created_at) hora.setAttribute("datetime", String(entry.created_at));
  li.appendChild(hora);
  if (conAutor) {
    const autor = histNodo("span", "hist-autor");
    pintarPersona(autor, formatAutor(entry));
    li.appendChild(autor);
  }
  const ticket = histNodo("span", "hist-ticket");
  const enlace = histNodo("a", "enlace-tabla", `#${entry.ticket_id}`);
  enlace.href = `detalle.html?id=${entry.ticket_id}`;
  ticket.appendChild(enlace);
  if (entry.ticket_title) {
    const titulo = histNodo("span", "hist-ticket-titulo", entry.ticket_title);
    titulo.title = entry.ticket_title;
    ticket.appendChild(titulo);
  }
  li.appendChild(ticket);
  li.appendChild(histNodo("span", "hist-frase", fraseCambio(entry)));
  return li;
}

/* Agrega los cambios debajo de los ya pintados; si el primero es del mismo
   día que el último grupo, sigue en ese grupo. */
function pintarCambios(entries, { reiniciar = false } = {}) {
  const contenedor = document.getElementById("hist-cambios");
  if (reiniciar) {
    contenedor.replaceChildren();
    historialEstado.ultimoDia = "";
    historialEstado.listaDia = null;
    historialEstado.cargados = 0;
  }
  const conAutor = historialEstado.persona === PERSONA_TODAS;
  let lista = historialEstado.listaDia;
  entries.forEach((entry) => {
    const dia = tituloDia(entry.created_at);
    if (!lista || dia.clave !== historialEstado.ultimoDia) {
      const grupo = histNodo("section", "hist-dia");
      const id = `hist-dia-${dia.clave || "sin-fecha"}`;
      const titulo = histNodo("h3", "depto-subtitulo hist-dia-titulo", dia.texto);
      titulo.id = id;
      grupo.setAttribute("aria-labelledby", id);
      grupo.appendChild(titulo);
      lista = histNodo("ul", "hist-lineas");
      grupo.appendChild(lista);
      contenedor.appendChild(grupo);
      historialEstado.ultimoDia = dia.clave;
    }
    lista.appendChild(lineaCambio(entry, conAutor));
  });
  historialEstado.listaDia = lista;
  historialEstado.cargados += entries.length;

  const total = historialEstado.cajas ? historialEstado.cajas.cambios : historialEstado.cargados;
  const verMas = document.getElementById("hist-ver-mas");
  const resto = total - historialEstado.cargados;
  verMas.hidden = resto <= 0;
  verMas.textContent = "Ver más";
  verMas.setAttribute("aria-label", `Ver más cambios (faltan ${resto})`);

  const vacio = document.getElementById("hist-vacio");
  vacio.hidden = historialEstado.cargados > 0;
  vacio.textContent = historialEstado.buscar
    ? `Ningún cambio en el período coincide con «${historialEstado.buscar}».`
    : "No hay cambios en este período.";
}

/* ---------- Pedidos ---------- */

function avisoHistorial(mensaje, tipo) {
  const el = document.getElementById("estado-carga");
  if (!el) return;
  el.textContent = mensaje;
  el.className = tipo ? `estado ${tipo}` : "estado";
  el.hidden = !mensaje;
}

function paramsFiltro() {
  const params = new URLSearchParams();
  params.set("persona", historialEstado.persona);
  params.set("periodo", historialEstado.periodo);
  if (historialEstado.buscar) params.set("buscar", historialEstado.buscar);
  return params;
}

const SIN_CONEXION = "No se pudo conectar con el servidor. Verifique que esté en funcionamiento.";

async function pedirJson(url) {
  let response;
  try {
    response = await fetchWithAuth(url);
  } catch (error) {
    throw new Error(SIN_CONEXION);
  }
  if (response.status === 403) throw new Error("Su rol no tiene permiso para ver el historial.");
  const datos = await response.json().catch(() => null);
  if (!response.ok || datos === null) throw new Error(`No se pudo cargar el historial (${response.status}).`);
  return datos;
}

function urlCambios(desplazamiento) {
  const params = paramsFiltro();
  params.set("limit", String(CAMBIOS_POR_PAGINA));
  params.set("offset", String(desplazamiento));
  return `${API_HISTORY_URL}?${params.toString()}`;
}

/* Pide el resumen (personas y cajas) y la primera página de cambios del
   filtro actual. Si mientras tanto cambió el filtro, la respuesta vieja se
   descarta. */
async function actualizarHistorial({ repintarLista = true } = {}) {
  const pedido = ++historialEstado.pedido;
  const detalle = document.getElementById("hist-detalle");
  detalle.setAttribute("aria-busy", "true");
  try {
    const [resumen, cambios] = await Promise.all([
      pedirJson(`${API_HISTORY_RESUMEN_URL}?${paramsFiltro().toString()}`),
      pedirJson(urlCambios(0)),
    ]);
    if (pedido !== historialEstado.pedido) return;
    if (!resumen || !Array.isArray(resumen.personas) || !Array.isArray(cambios)) {
      throw new Error("Respuesta inválida del servidor.");
    }
    historialEstado.personas = resumen.personas;
    historialEstado.total = resumen.total || 0;
    historialEstado.cajas = resumen.cajas || null;
    /* Una persona que ya no existe en el historial vuelve a «Todas». */
    if (historialEstado.persona !== PERSONA_TODAS
      && !resumen.personas.some((p) => p.clave === historialEstado.persona)) {
      historialEstado.persona = PERSONA_TODAS;
      guardarHash();
      actualizarHistorial({ repintarLista: true });
      return;
    }
    if (repintarLista) pintarListaPersonas();
    else actualizarCantidadTodas();
    marcarElegida(false);
    pintarCabeceraPersona();
    pintarCajasHistorial(historialEstado.cajas);
    pintarCambios(cambios, { reiniciar: true });
    document.getElementById("hist-layout").hidden = false;
    avisoHistorial("", "");
  } catch (error) {
    if (pedido !== historialEstado.pedido) return;
    avisoHistorial(error && error.message ? error.message : "Error al comunicarse con el servidor.", "error");
  } finally {
    if (pedido === historialEstado.pedido) detalle.removeAttribute("aria-busy");
  }
}

/* Sin repintar la lista (para no perder el foco al usar las flechas):
   solo el número de «Todas las personas». */
function actualizarCantidadTodas() {
  const boton = document.getElementById("tab-persona-todas");
  if (!boton || !boton.children) return;
  const total = historialEstado.total;
  Array.from(boton.children).forEach((hijo) => {
    if (/\bdepto-pastilla\b/.test(hijo.className)) hijo.textContent = String(total);
    if (/\bdepto-boton-abiertos\b/.test(hijo.className)) hijo.textContent = textoCambios(total);
  });
}

async function verMasCambios() {
  const boton = document.getElementById("hist-ver-mas");
  const pedido = historialEstado.pedido;
  boton.disabled = true;
  try {
    const cambios = await pedirJson(urlCambios(historialEstado.cargados));
    if (pedido !== historialEstado.pedido || !Array.isArray(cambios)) return;
    pintarCambios(cambios);
  } catch (error) {
    avisoHistorial(error && error.message ? error.message : "Error al comunicarse con el servidor.", "error");
  } finally {
    boton.disabled = false;
  }
}

function cambiarPeriodo(periodo) {
  if (!PERIODOS_HISTORIAL.includes(periodo) || periodo === historialEstado.periodo) return;
  historialEstado.periodo = periodo;
  guardarHash();
  actualizarHistorial({ repintarLista: true });
}

let esperaBusqueda = null;
function buscarTicket(texto, { inmediato = false } = {}) {
  const limpio = String(texto || "").trim();
  if (esperaBusqueda) clearTimeout(esperaBusqueda);
  const aplicar = () => {
    if (limpio === historialEstado.buscar) return;
    historialEstado.buscar = limpio;
    actualizarHistorial({ repintarLista: false });
  };
  if (inmediato) aplicar();
  else esperaBusqueda = setTimeout(aplicar, ESPERA_BUSQUEDA_MS);
}

function aplicarHash(hash) {
  const { persona, periodo } = leerHash(hash);
  const cambioPeriodo = periodo !== historialEstado.periodo;
  historialEstado.persona = persona;
  historialEstado.periodo = periodo;
  const select = document.getElementById("hist-periodo");
  if (select) select.value = periodo;
  return cambioPeriodo;
}

function iniciarHistorial() {
  const hash = typeof window !== "undefined" && window.location ? window.location.hash : "";
  aplicarHash(hash);
  const select = document.getElementById("hist-periodo");
  select.addEventListener("change", () => cambiarPeriodo(select.value));
  const buscar = document.getElementById("hist-buscar");
  buscar.addEventListener("input", () => buscarTicket(buscar.value));
  buscar.addEventListener("keydown", (evento) => {
    if (evento.key === "Enter") {
      evento.preventDefault();
      buscarTicket(buscar.value, { inmediato: true });
    }
  });
  document.getElementById("hist-ver-mas").addEventListener("click", verMasCambios);
  avisoHistorial("Cargando…", "cargando");
  return actualizarHistorial({ repintarLista: true });
}

if (typeof document !== "undefined" && typeof document.addEventListener === "function") {
  document.addEventListener("DOMContentLoaded", iniciarHistorial);
  if (typeof window !== "undefined" && typeof window.addEventListener === "function") {
    /* Atrás/adelante o un enlace con otra persona o período. */
    window.addEventListener("hashchange", () => {
      const antes = historialEstado.persona;
      const cambioPeriodo = aplicarHash(window.location.hash);
      if (cambioPeriodo || antes !== historialEstado.persona) actualizarHistorial({ repintarLista: true });
    });
  }
}
