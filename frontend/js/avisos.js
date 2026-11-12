/* Avisos flotantes: el resultado de una acción (guardar, comentar, asignar,
   adjuntar, agregar un usuario…). Una sola función para toda la app:

     avisar("Comentario agregado correctamente.");          // éxito
     avisar("No se pudo guardar el comentario.", "error");  // error

   - Arriba a la derecha, debajo de la barra del título; si hay varios se
     apilan (el más nuevo abajo). En el celular, a todo el ancho arriba.
   - Éxito: verde suave, se va solo a los 4 segundos (se pausa mientras el
     mouse o el foco están encima). Error: rojo suave, queda hasta cerrarlo.
   - Los dos se cierran con la ✕ (botón, también con teclado) o con Escape
     estando el foco en el aviso.
   - El lector de pantalla los anuncia: la zona es aria-live="polite" y los
     errores llevan role="alert".
   - Con una ventana modal abierta (<dialog>) el aviso va adentro de ella,
     para que se vea y se pueda cerrar; al cerrarla vuelve a la página.
   Los errores de un campo (debajo del campo) y los «Cargando…» o «No hay
   datos» no usan avisos. */

"use strict";

const AVISO_EXITO_MS = 4000;
const AVISO_SALIDA_MS = 200;
const AVISOS_MAXIMO = 4;
const AVISO_PENDIENTE_KEY = "aviso_pendiente";

function documentoAvisos(doc) {
  if (doc) return doc;
  return typeof document !== "undefined" ? document : null;
}

/* La zona donde se apilan: una sola por página, en el <body> o en la
   ventana modal abierta. */
function zonaAvisos(doc) {
  let zona = doc.getElementById("avisos");
  if (!zona) {
    zona = doc.createElement("div");
    zona.id = "avisos";
    zona.className = "avisos";
    zona.setAttribute("aria-live", "polite");
    zona.setAttribute("aria-label", "Avisos");
  }
  const modal = typeof doc.querySelector === "function" ? doc.querySelector("dialog[open]") : null;
  const destino = modal || doc.body;
  if (zona.parentNode !== destino) {
    destino.appendChild(zona);
    if (modal && typeof modal.addEventListener === "function") {
      modal.addEventListener("close", () => {
        if (zona.parentNode === modal) doc.body.appendChild(zona);
      }, { once: true });
    }
  }
  ubicarZona(zona, doc, modal);
  return zona;
}

/* Justo debajo de la barra del título (.cabecera) mientras se ve; si ya se
   bajó en la página, arriba con un margen. En la ventana modal, arriba. */
const AVISOS_MARGEN_PX = 12;

function ubicarZona(zona, doc, modal) {
  if (!zona.style || typeof zona.style.setProperty !== "function") return;
  const cabecera = !modal && typeof doc.querySelector === "function" ? doc.querySelector(".cabecera") : null;
  const borde = cabecera && typeof cabecera.getBoundingClientRect === "function"
    ? Math.max(cabecera.getBoundingClientRect().bottom, 0)
    : 0;
  zona.style.setProperty("--avisos-arriba", `${Math.round(borde + AVISOS_MARGEN_PX)}px`);
}

function cerrarAviso(aviso) {
  if (!aviso || aviso.cerrando) return;
  aviso.cerrando = true;
  if (aviso.temporizador) clearTimeout(aviso.temporizador);
  aviso.classList.add("saliendo");
  setTimeout(() => aviso.remove(), AVISO_SALIDA_MS);
}

function programarCierre(aviso) {
  if (aviso.temporizador) clearTimeout(aviso.temporizador);
  aviso.temporizador = setTimeout(() => cerrarAviso(aviso), AVISO_EXITO_MS);
}

function avisar(texto, tipo = "exito", doc) {
  const d = documentoAvisos(doc);
  if (!texto || !d || !d.body || typeof d.createElement !== "function") return null;
  const clase = tipo === "error" ? "error" : "exito";
  const zona = zonaAvisos(d);

  /* El mismo aviso dos veces seguidas no se repite: se renueva. */
  const previos = Array.from(zona.children || []);
  previos.forEach((otro) => {
    if (otro.texto === texto && otro.tipo === clase) cerrarAviso(otro);
  });
  const visibles = previos.filter((otro) => !otro.cerrando);
  visibles.slice(0, Math.max(0, visibles.length - AVISOS_MAXIMO + 1)).forEach(cerrarAviso);

  const aviso = d.createElement("div");
  aviso.className = `aviso ${clase}`;
  aviso.texto = texto;
  aviso.tipo = clase;
  if (clase === "error") aviso.setAttribute("role", "alert");

  const mensaje = d.createElement("p");
  mensaje.className = "aviso-texto";
  mensaje.textContent = texto;
  aviso.appendChild(mensaje);

  const cerrar = d.createElement("button");
  cerrar.type = "button";
  cerrar.className = "aviso-cerrar";
  cerrar.setAttribute("aria-label", "Cerrar aviso");
  cerrar.textContent = "✕";
  cerrar.addEventListener("click", () => cerrarAviso(aviso));
  aviso.appendChild(cerrar);

  aviso.addEventListener("keydown", (evento) => {
    if (evento.key === "Escape") {
      /* Solo el aviso: la ventana modal de abajo sigue abierta. */
      evento.preventDefault();
      evento.stopPropagation();
      cerrarAviso(aviso);
    }
  });

  if (clase === "exito") {
    /* Mientras se lee (mouse o foco encima) no se va. */
    const pausar = () => clearTimeout(aviso.temporizador);
    const seguir = () => { if (!aviso.cerrando) programarCierre(aviso); };
    aviso.addEventListener("mouseenter", pausar);
    aviso.addEventListener("mouseleave", seguir);
    aviso.addEventListener("focusin", pausar);
    aviso.addEventListener("focusout", seguir);
    programarCierre(aviso);
  }

  zona.appendChild(aviso);
  return aviso;
}

/* Para un aviso que se tiene que ver en la página siguiente (por
   ejemplo, después de crear o eliminar un ticket se va al listado). */
function avisoPendiente(texto, tipo = "exito") {
  try {
    sessionStorage.setItem(AVISO_PENDIENTE_KEY, JSON.stringify({ texto, tipo }));
  } catch (error) {
    /* Sin sessionStorage el aviso simplemente no se muestra. */
  }
}

function mostrarAvisoPendiente(doc) {
  try {
    const guardado = JSON.parse(sessionStorage.getItem(AVISO_PENDIENTE_KEY) || "null");
    sessionStorage.removeItem(AVISO_PENDIENTE_KEY);
    if (guardado && guardado.texto) avisar(guardado.texto, guardado.tipo, doc);
  } catch (error) {
    /* Nada que mostrar. */
  }
}

if (typeof document !== "undefined" && typeof document.addEventListener === "function") {
  document.addEventListener("DOMContentLoaded", () => mostrarAvisoPendiente());
}
