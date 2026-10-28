/* «Explicar con IA» en el detalle del ticket (Técnico, Supervisor y
   Administrador). Al abrir el ticket muestra la última explicación guardada
   (GET, sin llamar a la IA). «Explicar con IA» la pide (POST; el servidor
   reutiliza la guardada si el ticket no cambió) y «Volver a explicar»
   fuerza una nueva (?regenerar=true).
   Muestra la explicación con su certeza, las posibles causas y qué revisar
   primero. Todo lo que llega del servidor se pinta como texto
   (textContent), nunca como HTML. */

/* El servidor puede reintentar una vez si el JSON viene mal: hasta ~3 min. */
const IA_LIMITE_MS = 200000;
const IA_NOTA = "Contenido generado automáticamente. Revíselo antes de utilizarlo.";
const IA_NO_DISPONIBLE_TXT = "La IA no está disponible en este momento";
const IA_TARDO_TXT =
  "La IA no está disponible en este momento. Tardó demasiado en responder; inténtelo de nuevo.";

let iaOcupada = false;

function iaTicketId() {
  const id = Number(new URLSearchParams(window.location.search).get("id"));
  return Number.isInteger(id) && id > 0 ? id : null;
}

function iaElementos() {
  return {
    seccion: document.getElementById("seccion-ia"),
    explicar: document.getElementById("ia-explicar"),
    regenerar: document.getElementById("ia-regenerar"),
    estado: document.getElementById("ia-estado"),
    panel: document.getElementById("ia-panel"),
  };
}

function iaEstado(mensaje, tipo = "") {
  const { estado } = iaElementos();
  estado.textContent = mensaje;
  estado.className = `estado ${tipo}`.trim();
  estado.hidden = !mensaje;
}

function iaNodo(tag, clase, texto) {
  const el = document.createElement(tag);
  if (clase) el.className = clase;
  if (texto !== undefined) el.textContent = texto;
  return el;
}

function iaLista(items, ordenada = false) {
  const lista = iaNodo(ordenada ? "ol" : "ul");
  items.forEach((item) => lista.appendChild(iaNodo("li", "", item)));
  return lista;
}

function iaFecha(valor) {
  const fecha = new Date(valor);
  if (Number.isNaN(fecha.getTime())) return "";
  return fecha.toLocaleString("es-CR", {
    timeZone: "America/Costa_Rica",
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/* Un solo botón a la vista: «Explicar con IA» sin explicación y «Volver a
   explicar» cuando ya hay una. */
function iaRenderizar(datos) {
  const { panel, explicar, regenerar } = iaElementos();
  const e = datos.explicacion;
  panel.replaceChildren();
  if (!e) {
    panel.hidden = true;
    explicar.hidden = false;
    regenerar.hidden = true;
    return;
  }

  panel.appendChild(iaNodo("p", "ia-aviso", IA_NOTA));
  if (!datos.vigente) {
    panel.appendChild(
      iaNodo("p", "ia-desactualizada",
        "El ticket cambió desde la última explicación. Seleccione «Volver a explicar» para actualizarla.")
    );
  }

  panel.appendChild(iaNodo("p", "ia-explicacion", e.explicacion));

  const certeza = iaNodo("p");
  certeza.appendChild(iaNodo("strong", "", "Certeza: "));
  certeza.appendChild(iaNodo("span", `ia-certeza ${e.certeza}`, e.certeza));
  panel.appendChild(certeza);

  const claridad = iaNodo("p");
  claridad.appendChild(iaNodo("strong", "", "Claridad: "));
  claridad.appendChild(iaNodo("span", `ia-claridad ${datos.claridad.replace(" ", "-")}`, datos.claridad));
  claridad.appendChild(document.createTextNode(` ${datos.motivo_claridad}`));
  panel.appendChild(claridad);

  if (e.posibles_causas.length) {
    panel.appendChild(iaNodo("h3", "", "Posibles causas"));
    panel.appendChild(iaLista(e.posibles_causas));
  }
  if (e.que_revisar_primero.length) {
    panel.appendChild(iaNodo("h3", "", "Qué revisar primero"));
    panel.appendChild(iaLista(e.que_revisar_primero, true));
  }

  const sugerencias = [
    ["Categoría sugerida", e.categoria_sugerida],
    ["Prioridad sugerida", e.prioridad_sugerida],
  ].filter(([, s]) => s && s.valor);
  if (sugerencias.length) {
    panel.appendChild(iaNodo("h3", "", "Sugerencias (no se aplican solas)"));
    panel.appendChild(
      iaLista(sugerencias.map(([t, s]) => `${t}: ${s.valor}${s.razon ? ` — ${s.razon}` : ""}`))
    );
  }

  const pie = [datos.modelo && `Modelo: ${datos.modelo}`, datos.generada_en && `generado el ${iaFecha(datos.generada_en)}`]
    .filter(Boolean)
    .join(" · ");
  if (pie) panel.appendChild(iaNodo("p", "ia-pie", pie));

  panel.hidden = false;
  explicar.hidden = true;
  regenerar.hidden = false;
}

function iaBloquear(bloqueado) {
  const { explicar, regenerar } = iaElementos();
  iaOcupada = bloqueado;
  explicar.disabled = bloqueado;
  regenerar.disabled = bloqueado;
}

async function iaExplicar(regenerar = false) {
  const ticketId = iaTicketId();
  if (iaOcupada || ticketId === null) return;
  iaBloquear(true);
  iaEstado("Analizando el ticket… puede tardar hasta un minuto.", "ia-cargando");

  const control = typeof AbortController === "function" ? new AbortController() : null;
  const limite = control ? setTimeout(() => control.abort(), IA_LIMITE_MS) : null;
  try {
    const url = `/api/tickets/${ticketId}/explicacion${regenerar ? "?regenerar=true" : ""}`;
    const response = await fetchWithAuth(url, {
      method: "POST",
      signal: control ? control.signal : undefined,
    });
    const datos = await response.json().catch(() => null);
    if (response.ok && datos) {
      iaEstado("");
      iaRenderizar(datos);
    } else if (response.status === 403) {
      iaEstado("Su rol no tiene permiso para usar «Explicar con IA».", "error");
    } else if (response.status === 404) {
      iaEstado("El ticket ya no existe.", "error");
    } else {
      const detalle = datos && typeof datos.detail === "string" ? datos.detail : IA_NO_DISPONIBLE_TXT;
      iaEstado(detalle, "error");
    }
  } catch (error) {
    console.error("POST explicacion:", error);
    iaEstado(
      error && error.name === "AbortError" ? IA_TARDO_TXT : "Error al comunicarse con la API.",
      "error"
    );
  } finally {
    if (limite) clearTimeout(limite);
    iaBloquear(false);
  }
}

/* Al abrir el ticket: la explicación guardada, si hay (sin llamar a la IA). */
async function iaCargarGuardada() {
  const ticketId = iaTicketId();
  if (ticketId === null) return;
  try {
    const response = await fetchWithAuth(`/api/tickets/${ticketId}/explicacion`);
    if (!response.ok) return;
    const datos = await response.json();
    if (datos && datos.explicacion) iaRenderizar(datos);
  } catch (error) {
    console.error("GET explicacion:", error);
  }
}

async function iniciarExplicacion() {
  const { seccion, explicar, regenerar } = iaElementos();
  if (!seccion || !puede("explicar_ia")) return;
  explicar.addEventListener("click", () => iaExplicar(false));
  regenerar.addEventListener("click", () => iaExplicar(true));
  await iaCargarGuardada();
}

if (typeof document !== "undefined") {
  document.addEventListener("DOMContentLoaded", iniciarExplicacion);
}
