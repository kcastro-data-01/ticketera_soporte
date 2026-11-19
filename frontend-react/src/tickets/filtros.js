/* Filtros, orden y textos del listado (port de frontend/js/app.js, sin DOM). */

export const API_TICKETS_URL = "/api/tickets";
/* Sin paginación: todos los que cumplen los filtros, con el tope de la API. */
export const LIMITE_LISTADO = 1000;

export const CATEGORIAS = ["Hardware", "Software", "Red", "Accesos"];
export const PRIORIDADES = ["Baja", "Media", "Alta", "Crítica"];
export const ESTADO_ABIERTOS = "abiertos";
const ESTADOS_ABIERTOS = ["Nuevo", "En proceso"];
export const ESTADOS = ["Nuevo", "En proceso", "Resuelto", "Cerrado"];
const ESTADOS_FILTRO = [ESTADO_ABIERTOS, ...ESTADOS];
export const ESTADOS_TABLERO = ESTADOS;

export const FILTROS_VACIOS = {
  search: "", category: "", priority: "", state: "", asignado: "", area: "", fecha: "",
};

export const estadoFiltro = (valor) => (ESTADOS_FILTRO.includes(valor) ? valor : "");

const MAX_ANTIGUEDAD_DIAS = 365;
export function antiguedadValida(valor) {
  const n = Number(valor);
  return Number.isInteger(n) && n >= 1 && n <= MAX_ANTIGUEDAD_DIAS ? n : 0;
}

export const creadoAntesDe = (dias, ahora = Date.now()) =>
  new Date(ahora - dias * 24 * 60 * 60 * 1000).toISOString();

export function hayFiltros(f) {
  return Boolean(f.search || f.category || f.priority || f.state || f.mios
    || f.asignado || f.area || f.fecha || f.antiguedad);
}

/* Solo los parámetros con valor, con los nombres que ya usa la API. */
export function buildTicketsUrl(f, ahora = Date.now()) {
  const params = new URLSearchParams();
  if (f.search) params.set("search", f.search.trim());
  if (f.category) params.set("category", f.category);
  if (f.priority) params.set("priority", f.priority);
  const estado = estadoFiltro(f.state);
  if (estado === ESTADO_ABIERTOS) ESTADOS_ABIERTOS.forEach((e) => params.append("state", e));
  else if (estado) params.set("state", estado);
  if (f.mios) params.set("mios", "true");
  if (f.asignado === "sin") params.set("sin_asignar", "true");
  else if (/^\d+$/.test(f.asignado || "")) params.set("assigned_to", f.asignado);
  if (f.area === "sin") params.set("sin_area", "true");
  else if (/^\d+$/.test(f.area || "")) params.set("area", f.area);
  /* Los creados ese día (hora de Costa Rica): desde y hasta el mismo día. */
  if (f.fecha) {
    params.set("desde", f.fecha);
    params.set("hasta", f.fecha);
  }
  const dias = antiguedadValida(f.antiguedad);
  if (dias) params.set("creado_antes", creadoAntesDe(dias, ahora));
  params.set("limit", String(LIMITE_LISTADO));
  return `${API_TICKETS_URL}?${params.toString()}`;
}

/* Filtros que llegan en la dirección (desde «Departamentos»): area,
   estado, prioridad, asignado y antiguedad. Lo que no está entre las
   opciones se ignora. */
export function filtrosDeUrl(search, { solicitante = false, areas = [], usuarios = [] } = {}) {
  const params = new URLSearchParams(search || "");
  const filtros = {};
  let antiguedad = 0;
  const estado = estadoFiltro(params.get("estado") || "");
  if (estado) filtros.state = estado;
  if (!solicitante) {
    const area = params.get("area");
    if (area && (area === "sin" || areas.some((a) => String(a.id) === area))) filtros.area = area;
    const prioridad = params.get("prioridad");
    if (PRIORIDADES.includes(prioridad)) filtros.priority = prioridad;
    const asignado = params.get("asignado");
    if (asignado && (asignado === "sin" || usuarios.some((u) => String(u.id) === asignado))) filtros.asignado = asignado;
    antiguedad = antiguedadValida(params.get("antiguedad"));
  }
  return { filtros, antiguedad };
}

/* --- Orden de columnas (se recuerda en este navegador) --- */
export const ORDEN_KEY = "orden_listado";
const RANGO_PRIORIDAD = { Crítica: 0, Alta: 1, Media: 2, Baja: 3 };
const RANGO_ESTADO = { Nuevo: 0, "En proceso": 1, Resuelto: 2, Cerrado: 3 };
const CAMPOS_ORDEN = ["id", "title", "priority", "state", "created_at"];

export function leerOrden() {
  try {
    const guardado = JSON.parse(localStorage.getItem(ORDEN_KEY) || "null");
    if (guardado && CAMPOS_ORDEN.includes(guardado.campo) && ["asc", "desc"].includes(guardado.dir)) return guardado;
  } catch {
    /* Orden de la API. */
  }
  return null;
}

function valorOrden(ticket, campo) {
  if (campo === "priority") return RANGO_PRIORIDAD[ticket.priority] ?? 9;
  if (campo === "state") return RANGO_ESTADO[ticket.state] ?? 9;
  if (campo === "created_at") return Date.parse(ticket.created_at) || 0;
  if (campo === "title") return String(ticket.title || "");
  return Number(ticket.id) || 0;
}

export function ordenarTickets(tickets, criterio) {
  if (!criterio) return tickets.slice();
  const signo = criterio.dir === "desc" ? -1 : 1;
  return tickets.slice().sort((a, b) => {
    const x = valorOrden(a, criterio.campo);
    const y = valorOrden(b, criterio.campo);
    const comparacion = typeof x === "string" ? x.localeCompare(y, "es", { sensitivity: "base" }) : x - y;
    return comparacion * signo || (Number(b.id) - Number(a.id));
  });
}

/* Primera vez ascendente; otra vez, descendente. */
export const siguienteOrden = (orden, campo) => ({
  campo, dir: orden && orden.campo === campo && orden.dir === "asc" ? "desc" : "asc",
});

export function textoTotal(total, mostrados = total) {
  const tickets = (n) => (n === 1 ? "1 ticket" : `${n} tickets`);
  if (total > mostrados) return `Se muestran ${mostrados} de ${tickets(total)}. Use los filtros para acotar la lista.`;
  return tickets(total);
}

export const textoAntiguedad = (dias) =>
  (dias ? `Solo los creados hace más de ${dias === 1 ? "1 día" : `${dias} días`}.` : "");

export const FILAS_DESTACADAS = { Crítica: "fila-critica", Alta: "fila-alta" };
const CATEGORIAS_ICONO = { Hardware: "hardware", Software: "software", Red: "red", Accesos: "accesos" };
export function claseCategoria(categoria) {
  const clave = CATEGORIAS_ICONO[categoria];
  return clave ? `celda-categoria cat-${clave}` : "celda-categoria";
}

/* Preferencias de dos opciones guardadas en este navegador. */
export function leerPreferencia(clave, valores, porDefecto) {
  try {
    const v = localStorage.getItem(clave);
    return valores.includes(v) ? v : porDefecto;
  } catch {
    return porDefecto;
  }
}
export function guardarPreferencia(clave, valor) {
  try {
    localStorage.setItem(clave, typeof valor === "string" ? valor : JSON.stringify(valor));
  } catch {
    /* Solo para esta visita. */
  }
}
