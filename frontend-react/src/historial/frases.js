/* Historial global (port de frontend/js/historial.js, sin DOM): la
   dirección, la frase de cada cambio y los títulos de día. */
import { describirHistorial } from "../detalle/historial.js";
import { formatearFechaHora } from "../sesion/permisos.js";

export const PERIODOS_HISTORIAL = ["hoy", "7", "30"];
export const PERIODO_POR_DEFECTO = "7";
export const PERSONA_TODAS = "todas";
export const PERSONA_SISTEMA = "sistema";
export const CAMBIOS_POR_PAGINA = 50;

const DIAS_SEMANA = ["domingo", "lunes", "martes", "miércoles", "jueves", "viernes", "sábado"];
const MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
  "agosto", "septiembre", "octubre", "noviembre", "diciembre"];

export const textoCambios = (n) => (n === 1 ? "1 cambio" : `${n} cambios`);

export function formatAutor(entry) {
  const autor = entry.author ? String(entry.author).trim() : "";
  return !autor || autor === "Anónimo" ? "Sistema" : autor;
}

/* «#persona=12&periodo=30» → { persona, periodo } válidos. */
export function leerHash(hash) {
  const params = new URLSearchParams(String(hash || "").replace(/^#/, ""));
  const persona = String(params.get("persona") || "").trim().toLowerCase();
  const periodo = params.get("periodo");
  return {
    persona: persona === PERSONA_SISTEMA || /^\d+$/.test(persona) ? persona : PERSONA_TODAS,
    periodo: PERIODOS_HISTORIAL.includes(periodo) ? periodo : PERIODO_POR_DEFECTO,
  };
}

export function armarHash(persona, periodo) {
  const params = new URLSearchParams();
  params.set("persona", persona);
  params.set("periodo", periodo);
  return `#${params.toString()}`;
}

function recortar(texto, maximo = 120) {
  const limpio = String(texto).replace(/\s+/g, " ").trim();
  return limpio.length > maximo ? `${limpio.slice(0, maximo - 1)}…` : limpio;
}

function nombreAsignacion(valor) {
  if (valor === null || valor === undefined || valor === "") return "Sin asignar";
  return /^\d+$/.test(String(valor)) ? `Usuario #${valor}` : String(valor);
}

const CAMPOS_FRASE = {
  title: "el título", description: "la descripción", category: "la categoría", priority: "la prioridad", state: "el estado",
};

/* Lo que hizo, en una frase que sigue al nombre. */
export function fraseCambio(entry) {
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

function diaCostaRica(valor) {
  const m = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(formatearFechaHora(valor, { parte: "fecha" }));
  if (!m) return null;
  return { clave: `${m[3]}-${m[2]}-${m[1]}`, anio: Number(m[3]), mes: Number(m[2]), dia: Number(m[1]) };
}

/* «Hoy · jueves 12 de noviembre», «Ayer · …» o la fecha (con el año si es otro). */
export function tituloDia(valor, ahora = new Date()) {
  const dia = diaCostaRica(valor);
  if (!dia) return { clave: "", texto: "Sin fecha" };
  const utc = Date.UTC(dia.anio, dia.mes - 1, dia.dia);
  const fecha = `${DIAS_SEMANA[new Date(utc).getUTCDay()]} ${dia.dia} de ${MESES[dia.mes - 1]}`;
  const hoy = diaCostaRica(ahora);
  const diferencia = Math.round(((hoy ? Date.UTC(hoy.anio, hoy.mes - 1, hoy.dia) : NaN) - utc) / 86400000);
  let texto = fecha.charAt(0).toUpperCase() + fecha.slice(1);
  if (diferencia === 0) texto = `Hoy · ${fecha}`;
  else if (diferencia === 1) texto = `Ayer · ${fecha}`;
  else if (hoy && dia.anio !== hoy.anio) texto = `${texto} de ${dia.anio}`;
  return { clave: dia.clave, texto };
}

/* Los cambios en grupos de días seguidos. */
export function agruparPorDia(cambios, ahora) {
  const grupos = [];
  cambios.forEach((entry) => {
    const dia = tituloDia(entry.created_at, ahora);
    const ultimo = grupos[grupos.length - 1];
    if (ultimo && ultimo.clave === dia.clave) ultimo.cambios.push(entry);
    else grupos.push({ ...dia, cambios: [entry] });
  });
  return grupos;
}
