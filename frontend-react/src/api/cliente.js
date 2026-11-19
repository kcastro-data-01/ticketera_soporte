/* Cliente único de la API (port de fetchWithAuth): agrega el token, manda
   JSON y, si la API responde 401, la sesión venció: va al login, que
   intenta volver a entrar en silencio con Microsoft. */
import { cerrarSesion, estadoToken, getToken } from "../sesion/almacen.js";

export class SesionVencida extends Error {}

export async function api(url, opciones = {}) {
  const token = getToken();
  const headers = { ...opciones.headers };
  if (token) headers.Authorization = `Bearer ${token}`;
  let body = opciones.body;
  /* Solo un objeto o lista simple se manda como JSON; un archivo (Blob)
     o FormData va tal cual. */
  const simple = body !== null && typeof body === "object"
    && (Array.isArray(body) || Object.getPrototypeOf(body) === Object.prototype);
  if (simple) body = JSON.stringify(body);
  if (typeof body === "string" && !headers["Content-Type"]) headers["Content-Type"] = "application/json";

  const response = await fetch(url, { ...opciones, headers, body });
  if (response.status === 401 && token) {
    cerrarSesion(estadoToken(token) === "maxima" ? "maxima" : "vencida");
    throw new SesionVencida("La sesión expiró. Inicie sesión nuevamente.");
  }
  return response;
}

/* JSON de una respuesta correcta, o null. */
export async function apiJson(url, opciones) {
  const response = await api(url, opciones);
  if (!response.ok) return null;
  try {
    return await response.json();
  } catch {
    return null;
  }
}

/* FastAPI devuelve «detail»: solo se muestra si es texto, para no exponer
   estructuras internas de validación. */
export async function leerDetalle(response) {
  try {
    const cuerpo = await response.json();
    if (cuerpo && typeof cuerpo.detail === "string") return cuerpo.detail;
  } catch {
    /* Cuerpo no JSON. */
  }
  return "";
}
