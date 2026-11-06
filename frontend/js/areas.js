/* Áreas de IT (solo Administrador): crear, renombrar, desactivar y
   reactivar, contra /api/areas. Los datos se pintan con textContent: nunca
   se interpretan como HTML. */

const API_AREAS_URL = "/api/areas";
let areasOcupado = false;

function areasElementos() {
  return {
    form: document.getElementById("form-area"),
    nombre: document.getElementById("area-nombre"),
    crear: document.getElementById("crear-area"),
    estado: document.getElementById("estado-area"),
    tabla: document.getElementById("tabla-areas"),
    cuerpo: document.getElementById("cuerpo-areas"),
    listaEstado: document.getElementById("areas-estado"),
    seccionRenombrar: document.getElementById("seccion-renombrar"),
    formRenombrar: document.getElementById("form-renombrar"),
    renombrarId: document.getElementById("renombrar-id"),
    renombrarNombre: document.getElementById("renombrar-nombre"),
    cancelarRenombrar: document.getElementById("cancelar-renombrar"),
  };
}

function areasAviso(mensaje, tipo) {
  const el = areasElementos().estado;
  el.textContent = mensaje;
  el.className = `estado ${tipo}`;
  el.hidden = false;
  if (typeof mostrarAviso === "function") mostrarAviso(mensaje, tipo === "error" ? "error" : "exito");
}

/* Mismo largo que el backend (schemas._validate_area_name). */
function validarNombreArea(nombre) {
  const limpio = String(nombre || "").split(/\s+/).filter(Boolean).join(" ");
  if (limpio.length < 2) return { error: "El nombre del área debe tener al menos 2 caracteres." };
  if (limpio.length > 60) return { error: "El nombre del área debe tener como máximo 60 caracteres." };
  return { nombre: limpio };
}

async function areasDetalle(response) {
  const body = await response.json().catch(() => null);
  if (body && typeof body.detail === "string") return body.detail;
  return `No se pudo guardar (HTTP ${response.status}).`;
}

function renderAreas(areas) {
  const el = areasElementos();
  el.cuerpo.replaceChildren();
  if (!areas.length) {
    el.tabla.hidden = true;
    el.listaEstado.textContent = "Todavía no hay áreas de IT.";
    el.listaEstado.className = "estado vacio";
    el.listaEstado.hidden = false;
    return;
  }
  el.listaEstado.hidden = true;
  areas.forEach((area) => {
    const fila = document.createElement("tr");
    const celda = (texto) => {
      const td = document.createElement("td");
      td.textContent = texto;
      fila.appendChild(td);
      return td;
    };
    celda(area.name);
    celda(String(area.tecnicos || 0));
    const estado = celda("");
    const badge = document.createElement("span");
    badge.className = area.is_active ? "badge badge-activo" : "badge badge-inactivo";
    badge.textContent = area.is_active ? "Activa" : "Desactivada";
    estado.appendChild(badge);

    const acciones = celda("");
    acciones.className = "celda-acciones";
    const renombrar = document.createElement("button");
    renombrar.type = "button";
    renombrar.className = "btn-accion";
    renombrar.textContent = "Renombrar";
    renombrar.addEventListener("click", () => abrirRenombrar(area));
    const activar = document.createElement("button");
    activar.type = "button";
    activar.className = area.is_active ? "btn-accion secundario" : "btn-accion";
    activar.textContent = area.is_active ? "Desactivar" : "Reactivar";
    activar.addEventListener("click", () => cambiarActiva(area, !area.is_active));
    acciones.append(renombrar, activar);
    el.cuerpo.appendChild(fila);
  });
  el.tabla.hidden = false;
}

async function recargarAreas() {
  renderAreas(await cargarAreas(true));
}

async function guardarArea(url, metodo, datos, exito) {
  if (areasOcupado) return false;
  areasOcupado = true;
  try {
    const response = await fetchWithAuth(url, {
      method: metodo,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(datos),
    });
    if (!response.ok) {
      areasAviso(await areasDetalle(response), "error");
      return false;
    }
    areasAviso(exito, "exito");
    areasOcupado = false;
    await recargarAreas();
    return true;
  } catch (error) {
    areasAviso("No se pudo conectar con el servidor.", "error");
    return false;
  } finally {
    areasOcupado = false;
  }
}

async function crearArea() {
  const el = areasElementos();
  const { nombre, error } = validarNombreArea(el.nombre.value);
  if (error) {
    areasAviso(error, "error");
    return;
  }
  if (await guardarArea(API_AREAS_URL, "POST", { name: nombre }, `Área «${nombre}» creada.`)) {
    el.form.reset();
  }
}

function abrirRenombrar(area) {
  const el = areasElementos();
  el.renombrarId.value = String(area.id);
  el.renombrarNombre.value = area.name;
  el.seccionRenombrar.hidden = false;
  el.renombrarNombre.focus();
}

async function renombrarArea() {
  const el = areasElementos();
  const { nombre, error } = validarNombreArea(el.renombrarNombre.value);
  if (error) {
    areasAviso(error, "error");
    return;
  }
  const url = `${API_AREAS_URL}/${el.renombrarId.value}`;
  if (await guardarArea(url, "PATCH", { name: nombre }, `Área renombrada a «${nombre}».`)) {
    el.seccionRenombrar.hidden = true;
  }
}

async function cambiarActiva(area, activar) {
  if (!activar) {
    const ok = await confirmarAccion({
      titulo: "Desactivar área",
      mensaje: `¿Desactivar «${area.name}»? No se ofrecerá al crear tickets; los tickets y técnicos que ya la tienen la conservan.`,
      aceptar: "Desactivar",
      peligro: true,
    });
    if (!ok) return;
  }
  await guardarArea(`${API_AREAS_URL}/${area.id}`, "PATCH", { is_active: activar },
    activar ? `Área «${area.name}» reactivada.` : `Área «${area.name}» desactivada.`);
}

function initAreas() {
  const el = areasElementos();
  el.form.addEventListener("submit", (event) => {
    event.preventDefault();
    crearArea();
  });
  el.formRenombrar.addEventListener("submit", (event) => {
    event.preventDefault();
    renombrarArea();
  });
  el.cancelarRenombrar.addEventListener("click", () => {
    el.seccionRenombrar.hidden = true;
  });
  recargarAreas();
}

if (typeof document !== "undefined") {
  document.addEventListener("DOMContentLoaded", initAreas);
}
