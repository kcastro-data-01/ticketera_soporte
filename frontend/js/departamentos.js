/* Pantalla «Departamentos» (solo Administrador): GET
   /api/departamentos/resumen. Los números los calcula el servidor; aquí solo
   se pintan (con textContent: nunca como HTML). Cada número es un enlace a
   la lista de tickets con ese departamento y ese estado. */

const API_DEPARTAMENTOS_URL = "/api/departamentos/resumen";
/* Columnas de estado, en el orden de la tabla. */
const ESTADOS_DEPARTAMENTO = ["Nuevo", "En proceso", "Resuelto", "Cerrado"];

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

function deptoNodo(tag, clase, texto) {
  const el = document.createElement(tag);
  if (clase) el.className = clase;
  if (texto !== undefined) el.textContent = texto;
  return el;
}

/* Celda con el número como enlace (un 0 también se puede tocar). */
function celdaNumero(fila, valor, estado, etiqueta, columna) {
  const td = deptoNodo("td", "celda-numero");
  /* En el celular cada fila es una tarjeta: la etiqueta va al lado del número. */
  td.setAttribute("data-label", columna);
  const a = deptoNodo("a", "enlace-numero", String(valor));
  a.href = urlListaDepartamento(fila.area_id, estado);
  a.setAttribute("aria-label", `${fila.nombre}: ${textoTickets(valor)} ${etiqueta}`);
  td.appendChild(a);
  return td;
}

function celdaTecnicos(fila) {
  const td = deptoNodo("td", "celda-tecnicos");
  td.setAttribute("data-label", "Técnicos activos");
  const nombres = (fila.tecnicos || []).map((t) => t.name);
  if (fila.area_id === null || fila.area_id === undefined) {
    td.textContent = "—";
    return td;
  }
  td.appendChild(deptoNodo("span", "tecnicos-cantidad", String(nombres.length)));
  if (nombres.length) {
    td.title = nombres.join(", ");
    td.appendChild(deptoNodo("span", "tecnicos-nombres", nombres.join(", ")));
  } else {
    td.appendChild(deptoNodo("span", "tecnicos-nombres", "Sin técnicos"));
  }
  return td;
}

function pintarResumen(datos) {
  const total = document.getElementById("d-total-abiertos");
  const mas = document.getElementById("d-mas-abiertos");
  const nota = document.getElementById("d-mas-abiertos-nota");
  if (total) total.textContent = String(datos.total_abiertos);
  if (mas && nota) {
    if (datos.mas_abiertos) {
      mas.textContent = datos.mas_abiertos.nombre;
      const n = datos.mas_abiertos.abiertos;
      nota.textContent = n === 1 ? "1 ticket abierto" : `${n} tickets abiertos`;
    } else {
      mas.textContent = "—";
      nota.textContent = "Ningún departamento tiene tickets abiertos";
    }
  }
}

function pintarTabla(departamentos) {
  const cuerpo = document.getElementById("cuerpo-departamentos");
  const tabla = document.getElementById("tabla-departamentos");
  cuerpo.replaceChildren();
  departamentos.forEach((fila) => {
    const tr = deptoNodo("tr", fila.area_id === null || fila.area_id === undefined ? "fila-sin-departamento" : "");
    const nombre = deptoNodo("th", "", fila.nombre);
    nombre.setAttribute("scope", "row");
    tr.appendChild(nombre);
    tr.appendChild(celdaNumero(fila, fila.total, "", "en total", "Total"));
    tr.appendChild(celdaNumero(fila, fila.abiertos, "abiertos", "abiertos", "Abiertos"));
    ESTADOS_DEPARTAMENTO.forEach((estado) => {
      tr.appendChild(celdaNumero(fila, (fila.por_estado || {})[estado] || 0, estado, `en ${estado}`, estado));
    });
    tr.appendChild(celdaTecnicos(fila));
    cuerpo.appendChild(tr);
  });
  tabla.hidden = false;
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
    pintarResumen(datos);
    pintarTabla(datos.departamentos);
    avisoDepartamentos("", "");
  } catch (error) {
    avisoDepartamentos("Error al comunicarse con el servidor.", "error");
  }
}

if (typeof document !== "undefined" && typeof document.addEventListener === "function") {
  document.addEventListener("DOMContentLoaded", cargarDepartamentos);
}
