/* Adjuntos (port de frontend/js/adjuntos.js, sin DOM): validación,
   achicado de fotos, subida y descarga con la sesión. El servidor vuelve a
   validar tipo, contenido, tamaño, cantidad y permisos. */
import { api } from "../api/cliente.js";
import { formatearFechaHora } from "../sesion/permisos.js";

export const ADJ_EXTENSIONES = [".jpg", ".jpeg", ".png", ".pdf", ".docx", ".xlsx", ".txt"];
export const ADJ_TIPOS_TEXTO = "jpg, png, pdf, docx, xlsx o txt";
export const ADJ_ACCEPT = ".jpg,.jpeg,.png,.pdf,.docx,.xlsx,.txt,image/jpeg,image/png,application/pdf,text/plain";
const ADJ_LADO_MAX = 2000;
const ADJ_CALIDAD_JPG = 0.85;
export const ADJ_POR_DEFECTO = { adjuntos: [], puede_subir: false, cerrado: false, max_archivos: 10, max_bytes: 4 * 1024 * 1024 };

/* 900 B · 12,5 KB · 3,4 MB */
export function formatoTamano(bytes) {
  const n = Number(bytes) || 0;
  if (n < 1024) return `${n} B`;
  const [valor, unidad] = n < 1024 * 1024 ? [n / 1024, "KB"] : [n / (1024 * 1024), "MB"];
  return `${valor.toLocaleString("es-CR", { maximumFractionDigits: 1 })} ${unidad}`;
}

export function adjFecha(valor) {
  const texto = formatearFechaHora(valor);
  return texto === "—" ? "" : texto;
}

export function extensionDe(nombre) {
  const i = String(nombre || "").lastIndexOf(".");
  return i < 0 ? "" : String(nombre).slice(i).toLowerCase();
}

export function esTactil() {
  return typeof window.matchMedia === "function" && window.matchMedia("(pointer: coarse)").matches;
}

export function adjProblema(archivo, maxBytes = ADJ_POR_DEFECTO.max_bytes) {
  if (!ADJ_EXTENSIONES.includes(extensionDe(archivo.name))) {
    return `«${archivo.name}»: tipo no permitido. Se aceptan ${ADJ_TIPOS_TEXTO}.`;
  }
  if (!archivo.size) return `«${archivo.name}» está vacío.`;
  if (archivo.size > maxBytes) return `«${archivo.name}» pesa más de 4 MB.`;
  return null;
}

/* Lado mayor a 2000 px o formato que no es jpg/png (HEIC de la cámara): se
   redibuja en un canvas y se guarda como JPG. Si el navegador no puede
   abrir la imagen, se sube tal cual (el servidor decide). */
export async function achicarImagen(archivo, maxBytes = ADJ_POR_DEFECTO.max_bytes) {
  const ext = extensionDe(archivo.name);
  const esJpgPng = [".jpg", ".jpeg", ".png"].includes(ext);
  if (typeof createImageBitmap !== "function" || typeof archivo.type !== "string" || !archivo.type.startsWith("image/")) {
    return archivo;
  }
  let imagen;
  try {
    imagen = await createImageBitmap(archivo);
  } catch {
    return archivo;
  }
  const lado = Math.max(imagen.width, imagen.height);
  if (esJpgPng && lado <= ADJ_LADO_MAX && archivo.size <= maxBytes) {
    if (typeof imagen.close === "function") imagen.close();
    return archivo;
  }
  const escala = Math.min(1, ADJ_LADO_MAX / lado);
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(imagen.width * escala);
  canvas.height = Math.round(imagen.height * escala);
  canvas.getContext("2d").drawImage(imagen, 0, 0, canvas.width, canvas.height);
  if (typeof imagen.close === "function") imagen.close();
  const exportar = (tipo, calidad) => new Promise((resolver) => canvas.toBlob(resolver, tipo, calidad));
  let blob = ext === ".png" ? await exportar("image/png") : null;
  let nombre = archivo.name;
  if (!blob || blob.size > maxBytes) {
    blob = await exportar("image/jpeg", ADJ_CALIDAD_JPG);
    nombre = `${archivo.name.replace(/\.[^.]*$/, "") || "foto"}.jpg`;
  }
  if (!blob) return archivo;
  return { name: nombre, size: blob.size, type: blob.type, blob };
}

async function mensaje(response, porDefecto) {
  const body = await response.json().catch(() => null);
  return body && typeof body.detail === "string" ? body.detail : porDefecto;
}
export { mensaje as adjMensaje };

/* null si quedó guardado; si no, el motivo para mostrar. */
export async function adjSubirUno(id, archivo) {
  try {
    const response = await api(`/api/tickets/${id}/adjuntos?nombre=${encodeURIComponent(archivo.name)}`, {
      method: "POST",
      headers: { "Content-Type": "application/octet-stream" },
      body: archivo.blob || archivo,
    });
    if (response.status === 201) return null;
    return await mensaje(response, `No se pudo subir «${archivo.name}».`);
  } catch {
    return `No se pudo subir «${archivo.name}».`;
  }
}

export async function pedirArchivo(adjunto) {
  const response = await api(`/api/tickets/${adjunto.ticket_id}/adjuntos/${adjunto.id}/archivo`);
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.blob();
}
