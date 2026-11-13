/* Pantalla «Departamentos» (solo Administrador): GET
   /api/departamentos/resumen. A la izquierda, un botón por departamento
   (pestañas: role="tab"); a la derecha, el detalle del elegido. Los números
   los calcula el servidor; aquí solo se pintan (con textContent: nunca como
   HTML). Por la CSP no hay atributos style="": los anchos de las barritas y
   los colores de estado se ponen con element.style. El departamento elegido
   queda en la dirección (#programacion) para que al recargar se mantenga. */

const API_DEPARTAMENTOS_URL = "/api/departamentos/resumen";
const ESTADOS_DEPARTAMENTO = ["Nuevo", "En proceso", "Resuelto", "Cerrado"];
const COLORES_ESTADO = {
  Nuevo: "#1d4ed8",
  "En proceso": "#7c9fe8",
  Resuelto: "#0e8a7d",
  Cerrado: "#a3abbb",
};
/* El servidor manda como máximo esta cantidad de abiertos por departamento. */
const MAX_ABIERTOS_DETALLE = 10;

let departamentosActuales = [];
let deptoElegido = null;

/* Enlace a la lista: ``area`` es el id o «sin» (Sin departamento);
   ``estado`` un estado, «abiertos» (Nuevo + En proceso) o vacío (todos). */
function urlListaDepartamento(areaId, estado = "") {
  const params = new URLSearchParams();
  params.set("area", areaId === null || areaId === undefined ? "sin" : String(areaId));
  if (estado) params.set("estado", estado);
  return `index.html?${params.toString()}`;
}

function textoTickets(n) {
  return n === 1 ? "1 ticket" : `${n} tickets`;
}

function textoAbiertos(n) {
  return n === 1 ? "1 abierto" : `${n} abiertos`;
}

/* «Redes e Infraestructura» → «redes-e-infraestructura» (para la dirección). */
function slugDepartamento(nombre) {
  return String(nombre || "")
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

function deptoNodo(tag, clase, texto) {
  const el = document.createElement(tag);
  if (clase) el.className = clase;
  if (texto !== undefined) el.textContent = texto;
  return el;
}

/* Los departamentos que se muestran: los fijos siempre y «Sin departamento»
   solo si tiene tickets. */
function departamentosVisibles(departamentos) {
  return departamentos.filter((d) => d.area_id !== null && d.area_id !== undefined || d.total > 0);
}

/* Barrita fina con la mezcla de estados (ancho de cada parte = su %). */
function barraEstados(fila) {
  const barra = deptoNodo("span", "depto-barra");
  barra.setAttribute("aria-hidden", "true");
  const total = fila.total || 0;
  ESTADOS_DEPARTAMENTO.forEach((estado) => {
    const n = (fila.por_estado || {})[estado] || 0;
    if (!total || !n) return;
    const parte = deptoNodo("span", "depto-barra-parte");
    parte.style.width = `${(n * 100) / total}%`;
    parte.style.backgroundColor = COLORES_ESTADO[estado];
    barra.appendChild(parte);
  });
  return barra;
}

function pintarLista(departamentos) {
  const lista = document.getElementById("deptos-lista");
  lista.replaceChildren();
  departamentos.forEach((fila, indice) => {
    const slug = slugDepartamento(fila.nombre);
    const boton = deptoNodo("button", "depto-boton");
    boton.type = "button";
    boton.id = `tab-${slug}`;
    boton.setAttribute("role", "tab");
    boton.setAttribute("aria-controls", "deptos-detalle");
    boton.setAttribute("aria-selected", "false");
    boton.tabIndex = -1;
    if (boton.dataset) boton.dataset.slug = slug;
    if (fila.area_id === null || fila.area_id === undefined) boton.className += " sin-departamento";

    const textos = deptoNodo("span", "depto-boton-textos");
    textos.appendChild(deptoNodo("span", "depto-boton-nombre", fila.nombre));
    textos.appendChild(deptoNodo("span", "depto-boton-abiertos", textoAbiertos(fila.abiertos)));
    boton.appendChild(textos);
    const pastilla = deptoNodo("span", "depto-pastilla", String(fila.total));
    pastilla.setAttribute("aria-label", `${textoTickets(fila.total)} en total`);
    boton.appendChild(pastilla);
    boton.appendChild(barraEstados(fila));

    boton.addEventListener("click", () => elegirDepartamento(indice, { foco: false }));
    boton.addEventListener("keydown", (evento) => moverConTeclado(evento, indice));
    lista.appendChild(boton);
  });
}

/* Flechas, Inicio y Fin entre las pestañas (activación automática). */
function moverConTeclado(evento, indice) {
  const total = departamentosActuales.length;
  let destino = null;
  if (evento.key === "ArrowDown" || evento.key === "ArrowRight") destino = (indice + 1) % total;
  else if (evento.key === "ArrowUp" || evento.key === "ArrowLeft") destino = (indice - 1 + total) % total;
  else if (evento.key === "Home") destino = 0;
  else if (evento.key === "End") destino = total - 1;
  if (destino === null) return;
  evento.preventDefault();
  elegirDepartamento(destino, { foco: true });
}

function elegirDepartamento(indice, { foco = false, guardar = true } = {}) {
  const fila = departamentosActuales[indice];
  if (!fila) return;
  deptoElegido = indice;
  const lista = document.getElementById("deptos-lista");
  Array.from(lista.children || []).forEach((boton, i) => {
    const elegido = i === indice;
    boton.setAttribute("aria-selected", elegido ? "true" : "false");
    boton.tabIndex = elegido ? 0 : -1;
    const base = String(boton.className).replace(/\s*\belegido\b/g, "");
    boton.className = elegido ? `${base} elegido` : base;
    if (elegido && foco && typeof boton.focus === "function") boton.focus();
  });
  const slug = slugDepartamento(fila.nombre);
  document.getElementById("deptos-detalle").setAttribute("aria-labelledby", `tab-${slug}`);
  pintarDetalle(fila);
  if (guardar && typeof window !== "undefined" && window.history && typeof window.history.replaceState === "function") {
    window.history.replaceState(null, "", `#${slug}`);
  }
}

function cajaEstado(etiqueta, valor, clase, color) {
  const li = deptoNodo("li", `depto-caja ${clase}`);
  if (color) li.style.borderTopColor = color;
  li.appendChild(deptoNodo("span", "depto-caja-numero", String(valor)));
  li.appendChild(deptoNodo("span", "depto-caja-etiqueta", etiqueta));
  return li;
}

function pintarCajas(fila) {
  const cajas = document.getElementById("depto-cajas");
  cajas.replaceChildren(cajaEstado("Abiertos", fila.abiertos, "depto-caja-abiertos"));
  ESTADOS_DEPARTAMENTO.forEach((estado) => {
    cajas.appendChild(cajaEstado(estado, (fila.por_estado || {})[estado] || 0, "", COLORES_ESTADO[estado]));
  });
}

function celdaTexto(texto, clase) {
  return deptoNodo("td", clase || "", texto);
}

function pintarTecnicos(fila) {
  const cuerpo = document.getElementById("depto-tecnicos");
  const vacio = document.getElementById("depto-tecnicos-vacio");
  const tecnicos = fila.tecnicos || [];
  cuerpo.replaceChildren();
  tecnicos.forEach((t) => {
    const tr = deptoNodo("tr");
    const persona = deptoNodo("td", "celda-persona");
    pintarPersona(persona, t.name);
    tr.appendChild(persona);
    const abiertos = celdaTexto(String(t.abiertos || 0), "celda-num");
    abiertos.setAttribute("data-label", "Abiertos");
    const resueltos = celdaTexto(String(t.resueltos_mes || 0), "celda-num");
    resueltos.setAttribute("data-label", "Resueltos este mes");
    tr.appendChild(abiertos);
    tr.appendChild(resueltos);
    cuerpo.appendChild(tr);
  });
  if (cuerpo.parentNode) cuerpo.parentNode.hidden = !tecnicos.length;
  vacio.hidden = tecnicos.length > 0;
  vacio.textContent = fila.area_id === null || fila.area_id === undefined
    ? "Los tickets sin departamento no tienen técnicos propios."
    : "Este departamento no tiene técnicos activos.";
}

function celdaBadge(texto) {
  const td = deptoNodo("td");
  td.appendChild(deptoNodo("span", claseBadge(texto), texto));
  return td;
}

function pintarAbiertos(fila) {
  const cuerpo = document.getElementById("depto-abiertos");
  const vacio = document.getElementById("depto-abiertos-vacio");
  const nota = document.getElementById("depto-abiertos-nota");
  const tickets = (fila.tickets_abiertos || []).slice(0, MAX_ABIERTOS_DETALLE);
  cuerpo.replaceChildren();
  tickets.forEach((t) => {
    const tr = deptoNodo("tr");
    const celda = deptoNodo("td", "celda-ticket");
    const enlace = deptoNodo("a", "enlace-tabla", `#${t.id}`);
    enlace.href = `detalle.html?id=${t.id}`;
    celda.appendChild(enlace);
    celda.appendChild(deptoNodo("span", "celda-ticket-titulo", t.title));
    tr.appendChild(celda);
    tr.appendChild(celdaBadge(t.state));
    tr.appendChild(celdaBadge(t.priority));
    const asignado = deptoNodo("td", t.assigned_to_name ? "celda-persona" : "celda-persona sin-asignar");
    pintarPersona(asignado, t.assigned_to_name || "—");
    tr.appendChild(asignado);
    cuerpo.appendChild(tr);
  });
  if (cuerpo.parentNode) cuerpo.parentNode.hidden = !tickets.length;
  vacio.hidden = tickets.length > 0;
  vacio.textContent = "No tiene tickets abiertos.";
  const resto = (fila.abiertos || 0) - tickets.length;
  nota.hidden = resto <= 0;
  nota.textContent = resto > 0
    ? `Se muestran ${tickets.length} de ${fila.abiertos} abiertos. «Ver todos sus tickets» muestra el resto.`
    : "";
}

function pintarDetalle(fila) {
  document.getElementById("depto-nombre").textContent = fila.nombre;
  const atiende = document.getElementById("depto-atiende");
  atiende.textContent = fila.atiende ? `Atiende ${fila.atiende}` : "";
  atiende.hidden = !fila.atiende;
  document.getElementById("depto-total").textContent = `${textoTickets(fila.total)} en total`;
  const verTodos = document.getElementById("depto-ver-todos");
  /* Con más de 10 abiertos, el botón lleva a todos sus abiertos (el resto). */
  verTodos.href = urlListaDepartamento(fila.area_id, (fila.abiertos || 0) > MAX_ABIERTOS_DETALLE ? "abiertos" : "");
  verTodos.setAttribute("aria-label", `Ver todos los tickets de ${fila.nombre}`);
  pintarCajas(fila);
  pintarTecnicos(fila);
  pintarAbiertos(fila);
}

/* Índice del departamento de la dirección (#programacion); si no hay o no
   existe, el primero. */
function indiceDesdeHash(hash) {
  const slug = String(hash || "").replace(/^#/, "");
  const indice = departamentosActuales.findIndex((d) => slugDepartamento(d.nombre) === slug);
  return indice >= 0 ? indice : 0;
}

function avisoDepartamentos(mensaje, tipo) {
  const el = document.getElementById("estado-carga");
  if (!el) return;
  el.textContent = mensaje;
  el.className = tipo ? `estado ${tipo}` : "estado";
  el.hidden = !mensaje;
}

async function cargarDepartamentos() {
  avisoDepartamentos("Cargando…", "cargando");
  try {
    const response = await fetchWithAuth(API_DEPARTAMENTOS_URL);
    if (response.status === 403) {
      avisoDepartamentos("Su rol no tiene permiso para ver los departamentos.", "error");
      return;
    }
    const datos = await response.json().catch(() => null);
    if (!response.ok || !datos || !Array.isArray(datos.departamentos)) {
      avisoDepartamentos(`No se pudieron cargar los departamentos (${response.status}).`, "error");
      return;
    }
    departamentosActuales = departamentosVisibles(datos.departamentos);
    pintarLista(departamentosActuales);
    const hash = typeof window !== "undefined" && window.location ? window.location.hash : "";
    /* Sin departamento en la dirección se elige el primero sin tocarla. */
    elegirDepartamento(indiceDesdeHash(hash), { guardar: Boolean(hash) });
    document.getElementById("deptos-layout").hidden = false;
    avisoDepartamentos("", "");
  } catch (error) {
    avisoDepartamentos("Error al comunicarse con el servidor.", "error");
  }
}

if (typeof document !== "undefined" && typeof document.addEventListener === "function") {
  document.addEventListener("DOMContentLoaded", cargarDepartamentos);
  if (typeof window !== "undefined" && typeof window.addEventListener === "function") {
    /* Atrás/adelante o un enlace con otro #departamento. */
    window.addEventListener("hashchange", () => {
      if (departamentosActuales.length) elegirDepartamento(indiceDesdeHash(window.location.hash), { guardar: false });
    });
  }
}
