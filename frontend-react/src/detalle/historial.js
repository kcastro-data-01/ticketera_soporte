/* Historial legible (port de describirHistorial, auth.js): acción y detalle
   en español. Los registros antiguos de asignación guardaban ids: «Usuario #id». */
import { SIN_AREA } from "../sesion/permisos.js";

const CAMPOS_HISTORIAL = {
  title: "Título",
  description: "Descripción",
  category: "Categoría",
  priority: "Prioridad",
  state: "Estado",
};

function recortar(texto, maximo = 120) {
  const limpio = String(texto).replace(/\s+/g, " ").trim();
  return limpio.length > maximo ? `${limpio.slice(0, maximo - 1)}…` : limpio;
}

function nombreAsignacion(valor) {
  if (valor === null || valor === undefined || valor === "") return "Sin asignar";
  return /^\d+$/.test(String(valor)) ? `Usuario #${valor}` : String(valor);
}

export function describirHistorial(entry) {
  const antes = entry.old_value;
  const despues = entry.new_value;
  switch (entry.action) {
    case "created":
      if (entry.field === "correo") return { accion: "Creó el ticket", detalle: despues || "—" };
      return { accion: "Creó el ticket", detalle: despues ? `Asignado automáticamente a ${despues}` : "—" };
    case "updated": {
      const campo = CAMPOS_HISTORIAL[entry.field] || entry.field || "Dato";
      return { accion: "Editó el ticket", detalle: `${campo}: «${recortar(antes ?? "")}» → «${recortar(despues ?? "")}»` };
    }
    case "assigned":
      return {
        accion: despues ? "Asignó el ticket" : "Quitó la asignación",
        detalle: `${nombreAsignacion(antes)} → ${nombreAsignacion(despues)}`,
      };
    case "area_changed":
      return { accion: "Cambió el departamento", detalle: `${antes || SIN_AREA} → ${despues || SIN_AREA}` };
    case "Cierre automático":
      return { accion: "Cerrado automáticamente por falta de respuesta", detalle: `${antes ?? "Resuelto"} → ${despues ?? "Cerrado"}` };
    case "Reabierto por respuesta":
      return { accion: "Reabierto por respuesta del solicitante", detalle: `${antes ?? "Resuelto"} → ${despues ?? "En proceso"}` };
    case "Cambio de estado":
    case "state_changed":
      return { accion: "Cambió el estado", detalle: `${antes ?? "—"} → ${despues ?? "—"}` };
    case "commented":
      return { accion: "Comentó", detalle: despues ? `«${recortar(despues)}»` : "—" };
    case "attachment_added": {
      const porCorreo = entry.field === "correo" ? " (por correo)" : "";
      return { accion: "Adjuntó un archivo", detalle: despues ? `«${recortar(despues)}»${porCorreo}` : "—" };
    }
    case "attachments_skipped":
      return { accion: "Adjuntos no guardados", detalle: despues ? recortar(despues, 240) : "—" };
    case "attachment_deleted":
      return { accion: "Eliminó un adjunto", detalle: antes ? `«${recortar(antes)}»` : "—" };
    default: {
      const hayValores = (antes ?? null) !== null || (despues ?? null) !== null;
      return { accion: entry.action || "—", detalle: hayValores ? `${antes ?? "—"} → ${despues ?? "—"}` : "—" };
    }
  }
}

/* Registros sin usuario autenticado (vacíos o «Anónimo») → «Sistema». */
export function autorHistorial(entry) {
  const autor = entry.author ? String(entry.author).trim() : "";
  return !autor || autor === "Anónimo" ? "Sistema" : autor;
}
