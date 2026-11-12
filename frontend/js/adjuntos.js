/* Adjuntos en el detalle del ticket (GET/POST/DELETE /api/tickets/{id}/adjuntos).
   «Adjuntar archivos» elige uno o varios; «Sacar foto» (solo en pantallas
   táctiles) abre la cámara. Se sube un archivo por llamada, con el contenido
   en el cuerpo y el nombre en ?nombre=. Las fotos más grandes que
   ADJ_LADO_MAX px se achican aquí antes de subirlas.
   Las miniaturas y las descargas se piden con la sesión (fetchWithAuth) y se
   muestran desde un blob local: nunca hay enlaces públicos. El servidor
   vuelve a validar tipo, contenido, tamaño, cantidad y permisos. */

const ADJ_EXTENSIONES = [".jpg", ".jpeg", ".png", ".pdf", ".docx", ".xlsx", ".txt"];
const ADJ_TIPOS_TEXTO = "jpg, png, pdf, docx, xlsx o txt";
const ADJ_LADO_MAX = 2000;
const ADJ_CALIDAD_JPG = 0.85;

let adjDatos = { adjuntos: [], puede_subir: false, cerrado: false, max_archivos: 10, max_bytes: 4 * 1024 * 1024 };
let adjOcupado = false;
let adjUrls = [];
/* id del adjunto → URL local de su imagen (la miniatura y la vista previa
   usan la misma descarga). */
let adjImagenes = new Map();
let adjEstadoTicket = null;

function adjTicketId() {
  const id = Number(new URLSearchParams(window.location.search).get("id"));
  return Number.isInteger(id) && id > 0 ? id : null;
}

function adjElementos() {
  return {
    seccion: document.getElementById("seccion-adjuntos"),
    subir: document.getElementById("adj-subir"),
    foto: document.getElementById("adj-foto"),
    archivos: document.getElementById("adj-archivos"),
    camara: document.getElementById("adj-camara"),
    acciones: document.getElementById("adj-acciones"),
    nota: document.getElementById("adj-nota"),
    vacio: document.getElementById("adj-vacio"),
    estado: document.getElementById("adj-estado"),
    lista: document.getElementById("adj-lista"),
  };
}

function adjNodo(tag, clase, texto) {
  const el = document.createElement(tag);
  if (clase) el.className = clase;
  if (texto !== undefined) el.textContent = texto;
  return el;
}

function adjMostrarEstado(mensaje, tipo = "") {
  const { estado } = adjElementos();
  if (!estado) return;
  estado.textContent = mensaje || "";
  estado.className = `estado ${tipo}`.trim();
  estado.hidden = !mensaje;
}

function adjAvisar(mensaje, tipo) {
  if (typeof mostrarAviso === "function") mostrarAviso(mensaje, tipo);
  else adjMostrarEstado(mensaje, tipo);
}

/* 900 B · 12,5 KB · 3,4 MB */
function formatoTamano(bytes) {
  const n = Number(bytes) || 0;
  if (n < 1024) return `${n} B`;
  const unidades = n < 1024 * 1024 ? [n / 1024, "KB"] : [n / (1024 * 1024), "MB"];
  return `${unidades[0].toLocaleString("es-CR", { maximumFractionDigits: 1 })} ${unidades[1]}`;
}

function adjFecha(valor) {
  const fecha = new Date(valor);
  if (Number.isNaN(fecha.getTime())) return "";
  return fecha.toLocaleString("es-CR", { timeZone: "America/Costa_Rica", dateStyle: "short", timeStyle: "short" });
}

function extensionDe(nombre) {
  const i = String(nombre || "").lastIndexOf(".");
  return i < 0 ? "" : String(nombre).slice(i).toLowerCase();
}

function adjLiberarUrls() {
  if (typeof URL !== "undefined" && typeof URL.revokeObjectURL === "function") {
    adjUrls.forEach((url) => URL.revokeObjectURL(url));
  }
  adjUrls = [];
  adjImagenes = new Map();
}

async function adjPedirArchivo(adjunto) {
  const response = await fetchWithAuth(`/api/tickets/${adjunto.ticket_id}/adjuntos/${adjunto.id}/archivo`);
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.blob();
}

/* URL local de una imagen, pedida con la sesión una sola vez. */
function adjUrlImagen(adjunto) {
  if (!adjImagenes.has(adjunto.id)) {
    const pedido = adjPedirArchivo(adjunto).then((blob) => {
      const url = URL.createObjectURL(blob);
      adjUrls.push(url);
      return url;
    });
    pedido.catch(() => adjImagenes.delete(adjunto.id));
    adjImagenes.set(adjunto.id, pedido);
  }
  return adjImagenes.get(adjunto.id);
}

async function pintarMiniatura(adjunto, img) {
  try {
    img.src = await adjUrlImagen(adjunto);
  } catch (error) {
    img.hidden = true;
  }
}

/* Vista previa: la imagen grande (ajustada a la pantalla, sin deformarla)
   sobre un fondo oscuro, con el nombre y ✕. Se cierra con ✕, Esc o tocando
   afuera; el foco empieza en ✕, queda dentro y vuelve a ``volverA``. */
function abrirVistaPrevia(adjunto, volverA) {
  if (document.getElementById("adj-visor")) return null;
  const fondo = adjNodo("div", "adj-visor-fondo");
  fondo.id = "adj-visor";
  fondo.setAttribute("role", "dialog");
  fondo.setAttribute("aria-modal", "true");
  fondo.setAttribute("aria-labelledby", "adj-visor-titulo");
  const caja = adjNodo("div", "adj-visor");
  const cabecera = adjNodo("div", "adj-visor-cabecera");
  const titulo = adjNodo("p", "adj-visor-titulo", adjunto.nombre);
  titulo.id = "adj-visor-titulo";
  const cerrarBoton = adjNodo("button", "adj-visor-cerrar", "✕");
  cerrarBoton.type = "button";
  cerrarBoton.setAttribute("aria-label", "Cerrar vista previa");
  cabecera.appendChild(titulo);
  cabecera.appendChild(cerrarBoton);
  const estado = adjNodo("p", "adj-visor-estado", "Cargando imagen…");
  const img = adjNodo("img", "adj-visor-imagen");
  img.alt = adjunto.nombre;
  img.hidden = true;
  caja.appendChild(cabecera);
  caja.appendChild(estado);
  caja.appendChild(img);
  fondo.appendChild(caja);

  const teclas = (event) => {
    if (event.key === "Escape") {
      event.preventDefault();
      cerrar();
    } else if (event.key === "Tab") {
      /* ✕ es lo único enfocable: Tab no sale de la ventana. */
      event.preventDefault();
      cerrarBoton.focus();
    }
  };
  function cerrar() {
    document.removeEventListener("keydown", teclas, true);
    fondo.remove();
    if (volverA && typeof volverA.focus === "function") volverA.focus();
  }
  cerrarBoton.addEventListener("click", cerrar);
  fondo.addEventListener("click", (event) => {
    if (event.target === fondo || event.target === caja) cerrar();
  });
  document.addEventListener("keydown", teclas, true);
  document.body.appendChild(fondo);
  cerrarBoton.focus();

  const cargada = adjUrlImagen(adjunto).then((url) => {
    img.src = url;
    img.hidden = false;
    estado.remove();
  }).catch(() => {
    estado.textContent = "No se pudo cargar la imagen.";
  });
  return { cerrar, cargada };
}

async function descargarAdjunto(adjunto) {
  try {
    const url = URL.createObjectURL(await adjPedirArchivo(adjunto));
    const enlace = adjNodo("a");
    enlace.href = url;
    enlace.download = adjunto.nombre;
    document.body.appendChild(enlace);
    enlace.click();
    enlace.remove();
    setTimeout(() => URL.revokeObjectURL(url), 60000);
  } catch (error) {
    adjAvisar(`No se pudo descargar «${adjunto.nombre}».`, "error");
  }
}

async function eliminarAdjunto(adjunto) {
  if (adjOcupado) return;
  const confirmado = await confirmarAccion({
    titulo: "Eliminar adjunto",
    mensaje: `¿Desea eliminar «${adjunto.nombre}» del ticket? Esta acción no se puede deshacer.`,
    aceptar: "Eliminar",
    peligro: true,
  });
  if (!confirmado) return;
  adjOcupado = true;
  try {
    const response = await fetchWithAuth(`/api/tickets/${adjunto.ticket_id}/adjuntos/${adjunto.id}`, { method: "DELETE" });
    if (response.status === 204) {
      adjAvisar(`«${adjunto.nombre}» eliminado.`, "exito");
    } else {
      adjAvisar(await adjMensaje(response, "No se pudo eliminar el adjunto."), "error");
    }
  } catch (error) {
    adjAvisar("Error al comunicarse con la API.", "error");
  } finally {
    adjOcupado = false;
  }
  await cargarAdjuntos();
}

async function adjMensaje(response, porDefecto) {
  const body = await response.json().catch(() => null);
  return body && typeof body.detail === "string" ? body.detail : porDefecto;
}

function renderAdjuntos(datos) {
  const el = adjElementos();
  adjDatos = datos;
  adjLiberarUrls();
  el.lista.replaceChildren();
  const adjuntos = Array.isArray(datos.adjuntos) ? datos.adjuntos : [];

  el.acciones.hidden = !datos.puede_subir;
  if (el.subir) el.subir.disabled = adjOcupado;
  if (el.foto) el.foto.hidden = !adjEsTactil();
  /* Texto chico debajo del botón: «jpg, png… · hasta 4 MB cada uno · 0 de 10». */
  el.nota.textContent = datos.puede_subir
    ? `${ADJ_TIPOS_TEXTO} · hasta 4 MB cada uno · ${adjuntos.length} de ${datos.max_archivos}`
    : (datos.cerrado
      ? "El ticket está Cerrado: no se agregan ni se eliminan adjuntos."
      : `El ticket ya tiene ${datos.max_archivos} adjuntos, el máximo permitido.`);

  /* Sin archivos: solo la línea «Sin adjuntos» al lado del botón. */
  if (el.vacio) el.vacio.hidden = adjuntos.length > 0;
  adjMostrarEstado("");
  if (adjuntos.length === 0) {
    el.lista.hidden = true;
    return;
  }
  adjuntos.forEach((adjunto) => {
    const fila = adjNodo("li", "adjunto");
    let ver = null;
    if (adjunto.es_imagen) {
      ver = adjNodo("button", "adjunto-ver");
      ver.type = "button";
      ver.setAttribute("aria-label", `Ver imagen ${adjunto.nombre}`);
      const img = adjNodo("img", "adjunto-miniatura");
      img.alt = "";
      img.width = 48;
      img.height = 48;
      ver.appendChild(img);
      ver.addEventListener("click", () => abrirVistaPrevia(adjunto, ver));
      fila.appendChild(ver);
      pintarMiniatura(adjunto, img);
    } else {
      fila.appendChild(adjNodo("span", "adjunto-icono", extensionDe(adjunto.nombre).slice(1).toUpperCase()));
    }
    const datosFila = adjNodo("div", "adjunto-datos");
    if (ver) {
      /* El nombre de una imagen también abre la vista previa. */
      const nombre = adjNodo("button", "adjunto-nombre adjunto-nombre-boton", adjunto.nombre);
      nombre.type = "button";
      nombre.setAttribute("aria-label", `Ver imagen ${adjunto.nombre}`);
      nombre.addEventListener("click", () => abrirVistaPrevia(adjunto, ver));
      datosFila.appendChild(nombre);
    } else {
      datosFila.appendChild(adjNodo("span", "adjunto-nombre", adjunto.nombre));
    }
    datosFila.appendChild(adjNodo(
      "span", "adjunto-meta",
      `${formatoTamano(adjunto.tamano)} · ${adjunto.subido_por || "Sistema"} · ${adjFecha(adjunto.creado)}`
        + (adjunto.por_correo ? " · por correo" : ""),
    ));
    fila.appendChild(datosFila);

    /* Acciones de texto chicas a la derecha: «Descargar · Eliminar». */
    const botones = adjNodo("div", "adjunto-acciones");
    const descargar = adjNodo("button", "adjunto-accion", "Descargar");
    descargar.type = "button";
    descargar.setAttribute("aria-label", `Descargar ${adjunto.nombre}`);
    descargar.addEventListener("click", () => descargarAdjunto(adjunto));
    botones.appendChild(descargar);
    if (adjunto.puede_eliminar) {
      const separador = adjNodo("span", "adjunto-separador", "·");
      separador.setAttribute("aria-hidden", "true");
      botones.appendChild(separador);
      const borrar = adjNodo("button", "adjunto-accion adjunto-accion-peligro", "Eliminar");
      borrar.type = "button";
      borrar.setAttribute("aria-label", `Eliminar ${adjunto.nombre}`);
      borrar.addEventListener("click", () => eliminarAdjunto(adjunto));
      botones.appendChild(borrar);
    }
    fila.appendChild(botones);
    el.lista.appendChild(fila);
  });
  el.lista.hidden = false;
}

async function cargarAdjuntos() {
  const id = adjTicketId();
  const el = adjElementos();
  if (id === null || !el.seccion) return;
  try {
    const response = await fetchWithAuth(`/api/tickets/${id}/adjuntos`);
    if (response.status === 404) {
      el.seccion.hidden = true;
      return;
    }
    if (!response.ok) {
      adjMostrarEstado(`No se pudieron cargar los adjuntos (HTTP ${response.status}).`, "error");
      return;
    }
    el.seccion.hidden = false;
    renderAdjuntos(await response.json());
  } catch (error) {
    adjMostrarEstado("No se pudieron cargar los adjuntos.", "error");
  }
}

function adjEsTactil() {
  return typeof window.matchMedia === "function" && window.matchMedia("(pointer: coarse)").matches;
}

/* Lado mayor a ADJ_LADO_MAX o formato que no es jpg/png (p. ej. HEIC de
   la cámara): se redibuja en un canvas y se guarda como JPG. Si el
   navegador no puede abrir la imagen, se sube tal cual (el servidor decide). */
async function achicarImagen(archivo) {
  const ext = extensionDe(archivo.name);
  const esJpgPng = [".jpg", ".jpeg", ".png"].includes(ext);
  if (typeof createImageBitmap !== "function" || typeof archivo.type !== "string" || !archivo.type.startsWith("image/")) {
    return archivo;
  }
  let imagen;
  try {
    imagen = await createImageBitmap(archivo);
  } catch (error) {
    return archivo;
  }
  const lado = Math.max(imagen.width, imagen.height);
  if (esJpgPng && lado <= ADJ_LADO_MAX && archivo.size <= adjDatos.max_bytes) {
    if (typeof imagen.close === "function") imagen.close();
    return archivo;
  }
  const escala = Math.min(1, ADJ_LADO_MAX / lado);
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(imagen.width * escala);
  canvas.height = Math.round(imagen.height * escala);
  canvas.getContext("2d").drawImage(imagen, 0, 0, canvas.width, canvas.height);
  if (typeof imagen.close === "function") imagen.close();
  const comoPng = ext === ".png";
  const exportar = (tipo, calidad) => new Promise((resolver) => canvas.toBlob(resolver, tipo, calidad));
  let blob = comoPng ? await exportar("image/png") : null;
  let nombre = archivo.name;
  if (!blob || blob.size > adjDatos.max_bytes) {
    blob = await exportar("image/jpeg", ADJ_CALIDAD_JPG);
    nombre = `${archivo.name.replace(/\.[^.]*$/, "") || "foto"}.jpg`;
  }
  if (!blob) return archivo;
  return { name: nombre, size: blob.size, type: blob.type, blob };
}

/* Revisión rápida antes de subir (el servidor vuelve a validar todo). */
function adjProblema(archivo) {
  if (!ADJ_EXTENSIONES.includes(extensionDe(archivo.name))) {
    return `«${archivo.name}»: tipo no permitido. Se aceptan ${ADJ_TIPOS_TEXTO}.`;
  }
  if (!archivo.size) return `«${archivo.name}» está vacío.`;
  if (archivo.size > adjDatos.max_bytes) return `«${archivo.name}» pesa más de 4 MB.`;
  return null;
}

/* Sube un archivo ya preparado (achicado si era una foto) al ticket ``id``.
   Devuelve ``null`` si quedó guardado o el motivo para mostrar. También lo
   usa el formulario de Nuevo ticket (crear.js). */
async function adjSubirUno(id, archivo) {
  try {
    const response = await fetchWithAuth(
      `/api/tickets/${id}/adjuntos?nombre=${encodeURIComponent(archivo.name)}`,
      { method: "POST", headers: { "Content-Type": "application/octet-stream" }, body: archivo.blob || archivo },
    );
    if (response.status === 201) return null;
    return await adjMensaje(response, `No se pudo subir «${archivo.name}».`);
  } catch (error) {
    return `No se pudo subir «${archivo.name}».`;
  }
}

async function subirArchivos(lista) {
  const id = adjTicketId();
  const archivos = Array.from(lista || []);
  if (id === null || archivos.length === 0 || adjOcupado) return;
  const libres = adjDatos.max_archivos - (adjDatos.adjuntos || []).length;
  const errores = [];
  if (archivos.length > libres) {
    errores.push(`Solo se pueden agregar ${Math.max(libres, 0)} archivo(s) más (máximo ${adjDatos.max_archivos} por ticket).`);
    archivos.splice(Math.max(libres, 0));
  }
  adjOcupado = true;
  const el = adjElementos();
  if (el.subir) el.subir.disabled = true;
  if (el.foto) el.foto.disabled = true;
  let subidos = 0;
  try {
    for (const [i, original] of archivos.entries()) {
      adjMostrarEstado(`Subiendo ${i + 1} de ${archivos.length}: ${original.name}…`, "cargando");
      const archivo = await achicarImagen(original);
      const problema = adjProblema(archivo);
      if (problema) {
        errores.push(problema);
        continue;
      }
      const error = await adjSubirUno(id, archivo);
      if (error) errores.push(error);
      else subidos += 1;
    }
  } finally {
    adjOcupado = false;
    if (el.subir) el.subir.disabled = false;
    if (el.foto) el.foto.disabled = false;
    if (el.archivos) el.archivos.value = "";
    if (el.camara) el.camara.value = "";
  }
  if (subidos) adjAvisar(subidos === 1 ? "Archivo adjuntado." : `${subidos} archivos adjuntados.`, "exito");
  await cargarAdjuntos();
  if (errores.length) adjMostrarEstado(errores.join(" "), "error");
}

/* detalle.js avisa cada vez que pinta el ticket: si cambió de estado (por
   ejemplo, a Cerrado) se vuelven a pedir los adjuntos y sus permisos. */
function adjuntosTicketActualizado(ticket) {
  const anterior = adjEstadoTicket;
  adjEstadoTicket = ticket ? ticket.state : null;
  if (anterior !== null && anterior !== adjEstadoTicket) cargarAdjuntos();
}

async function iniciarAdjuntos() {
  const el = adjElementos();
  if (!el.seccion || adjTicketId() === null) return;
  el.subir.addEventListener("click", () => el.archivos.click());
  el.archivos.addEventListener("change", () => subirArchivos(el.archivos.files));
  if (el.foto && el.camara) {
    el.foto.addEventListener("click", () => el.camara.click());
    el.camara.addEventListener("change", () => subirArchivos(el.camara.files));
  }
  await cargarAdjuntos();
}

if (typeof document !== "undefined") {
  document.addEventListener("DOMContentLoaded", iniciarAdjuntos);
}
