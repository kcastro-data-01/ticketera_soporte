/* Comentarios como conversación (port de detalle.js): agrupa los seguidos
   de la misma persona (menos de 10 minutos) y separa los avisos del
   sistema (motivo de un cambio de estado). */
const COMENTARIOS_AGRUPAR_MS = 10 * 60 * 1000;

function claveAutor(c) {
  return c.author_id !== null && c.author_id !== undefined ? `id:${c.author_id}` : `nombre:${c.author || "Anónimo"}`;
}

export function agruparConAnterior(anterior, c) {
  if (!anterior || anterior.origen === "estado" || c.origen === "estado") return false;
  if (claveAutor(anterior) !== claveAutor(c)) return false;
  const diferencia = new Date(c.created_at) - new Date(anterior.created_at);
  return Number.isFinite(diferencia) && diferencia >= 0 && diferencia < COMENTARIOS_AGRUPAR_MS;
}

/* [{ comentario, seguido, sistema }] en el orden de la API. */
export function armarConversacion(comentarios) {
  return comentarios.map((c, i) => ({
    comentario: c,
    sistema: c.origen === "estado",
    seguido: c.origen !== "estado" && agruparConAnterior(i ? comentarios[i - 1] : null, c),
  }));
}

export function textoSistema(c) {
  const motivo = String(c.content || "").trim();
  const texto = c.estado_nuevo ? `Pasó a ${c.estado_nuevo}` : "Cambio de estado";
  return motivo ? `${texto} · ${motivo}` : texto;
}

/* Detalle de validación de FastAPI (422) legible. */
export function formatValidation(detail) {
  if (!detail || !Array.isArray(detail.detail)) return "El servidor rechazó los datos enviados. Revise el formulario.";
  const mensajes = detail.detail.map((error) => {
    const campo = Array.isArray(error.loc) ? error.loc.slice(1).join(".") : "";
    return campo ? `${campo}: ${error.msg}` : error.msg;
  });
  return `Revise los datos enviados. ${mensajes.join(" | ")}`;
}

export async function mensajeDeDetalle(response, porDefecto) {
  const body = await response.json().catch(() => null);
  return body && body.detail ? String(body.detail) : porDefecto;
}

export function validarTexto({ title, description }) {
  if (!title && !description) return "El título y la descripción son obligatorios.";
  if (!title) return "El título es obligatorio.";
  if (!description) return "La descripción es obligatoria.";
  return "";
}
