/* Permisos por rol y formatos compartidos (copiados de frontend/js/auth.js;
   espejo de backend/routers/auth.py). El servidor es quien bloquea: aquí
   solo se ocultan los botones y enlaces que el rol no puede usar. */

export const PERMISOS = {
  editar: ["Administrador"],
  asignar: ["Administrador"],
  cambiar_estado: ["Administrador", "Técnico"],
  historial_global: ["Administrador", "Técnico"],
  usuarios: ["Administrador"],
  eliminar: ["Administrador"],
  explicar_ia: ["Administrador", "Técnico"],
  metricas: ["Administrador"],
  departamentos: ["Administrador"],
  cambiar_area: ["Administrador", "Técnico"],
};

export const SIN_AREA = "Sin departamento";

export function puede(user, permiso) {
  const roles = PERMISOS[permiso] || [];
  return Boolean(user && roles.includes(user.role));
}

export const ticketCerrado = (ticket) => Boolean(ticket && ticket.state === "Cerrado");

/* El Administrador salvo Cerrado; quien lo creó, solo mientras está «Nuevo». */
export function puedeEditarTicket(user, ticket) {
  if (!ticket || ticketCerrado(ticket)) return false;
  if (puede(user, "editar")) return true;
  return Boolean(user && user.id !== undefined && user.id !== null
    && ticket.created_by_id === user.id && ticket.state === "Nuevo");
}

export function inicialesDe(nombre) {
  return String(nombre || "")
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((parte) => parte.charAt(0).toUpperCase())
    .join("");
}

const AVATAR_TONOS = 6;
export function tonoAvatar(nombre) {
  const base = String(nombre || "").trim().toLowerCase();
  let hash = 0;
  for (let i = 0; i < base.length; i += 1) hash = (hash * 31 + base.charCodeAt(i)) >>> 0;
  return hash % AVATAR_TONOS;
}

/* Hora de Costa Rica en 12 horas: «11/11/2026, 3:40 p. m.»; «—» sin fecha. */
const PARTES_FECHA_HORA = new Intl.DateTimeFormat("en-US", {
  timeZone: "America/Costa_Rica", year: "numeric", month: "2-digit", day: "2-digit",
  hour: "numeric", minute: "2-digit", hourCycle: "h23",
});

export function formatearFechaHora(valor, { parte = "" } = {}) {
  if (valor === null || valor === undefined || valor === "") return "—";
  const fecha = valor instanceof Date ? valor : new Date(valor);
  if (Number.isNaN(fecha.getTime())) return "—";
  const p = {};
  PARTES_FECHA_HORA.formatToParts(fecha).forEach(({ type, value }) => { p[type] = value; });
  const h24 = Number(p.hour) % 24;
  const textoFecha = `${p.day}/${p.month}/${p.year}`;
  const textoHora = `${h24 % 12 || 12}:${p.minute} ${h24 < 12 ? "a. m." : "p. m."}`;
  if (parte === "fecha") return textoFecha;
  if (parte === "hora") return textoHora;
  return `${textoFecha}, ${textoHora}`;
}

const CLASES_BADGE = {
  Nuevo: "estado-nuevo",
  "En proceso": "estado-proceso",
  Resuelto: "estado-resuelto",
  Cerrado: "estado-cerrado",
  Baja: "prioridad-baja",
  Media: "prioridad-media",
  Alta: "prioridad-alta",
  Crítica: "prioridad-critica",
};

export function claseBadge(valor) {
  const clase = CLASES_BADGE[valor];
  return clase ? `badge ${clase}` : "badge";
}

/* Clase y data-iniciales de una persona (como pintarPersona). */
export function persona(nombre, claseBase = "") {
  const texto = nombre || "—";
  const real = texto !== "—" && !/^Usuario #/.test(texto);
  return {
    texto,
    className: real ? `${claseBase} con-avatar tono-avatar-${tonoAvatar(texto)}`.trim() : claseBase,
    iniciales: real ? inicialesDe(texto) : undefined,
  };
}

/* IT solo recibe: «Asignar a» ofrece solo estos roles (backend.constants.IT_ROLES). */
export const ROLES_IT = ["Administrador", "Técnico"];

/* Cambiar el estado: los roles de «cambiar_estado» y, sea cual sea su rol,
   quien lo tiene asignado (ticket_service.can_change_state). Cerrado, nadie. */
export function puedeCambiarEstado(user, ticket) {
  if (ticketCerrado(ticket)) return false;
  if (puede(user, "cambiar_estado")) return true;
  return Boolean(user && ticket && user.id !== undefined && user.id !== null
    && ticket.assigned_to_id === user.id);
}

/* Transiciones válidas (espejo del backend; el servidor vuelve a validar). */
export const TRANSICIONES = {
  Nuevo: ["En proceso", "Resuelto", "Cerrado"],
  "En proceso": ["Resuelto", "Cerrado"],
  Resuelto: ["Cerrado", "En proceso"],
  Cerrado: [],
};
export const PASOS_ESTADO = ["Nuevo", "En proceso", "Resuelto", "Cerrado"];
