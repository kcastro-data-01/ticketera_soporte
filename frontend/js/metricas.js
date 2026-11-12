/* Página de métricas (solo Administrador) como informe de gestión:
   consulta GET /api/metricas (el período y el anterior de la misma
   duración) y pinta tablas (Resumen, Situación de hoy, Tickets por
   categoría, Por técnico) y dos gráficos de barras clásicos (Chart.js):
   tickets por estado y creados por día.
   Los números los calcula el servidor; aquí solo se muestran.
   Cada gráfico tiene debajo su tabla («Ver datos»); si Chart.js no carga
   (sin internet), las tablas quedan abiertas y la página sirve igual.
   «Imprimir» imprime solo el informe, con los gráficos en grises.
   Todo lo que llega del servidor se pinta como texto, nunca como HTML. */

const API_METRICAS_URL = "/api/metricas";
const ZONA = "America/Costa_Rica";
const DIAS_POR_DEFECTO = 30;
/* Un solo color para las barras: el azul de la app (--color-primario);
   texto, ejes y líneas de fondo en grises. */
const COLORES_POR_DEFECTO = {
  barra: "#1746e0",
  texto: "#5d6880",
  eje: "#c4cddd",
  rejilla: "#eef1f5",
};
/* En la hoja impresa: blanco y negro. */
const COLORES_IMPRESION = { barra: "#555555", texto: "#000000", eje: "#000000", rejilla: "#dddddd" };

/* Letra del sitio (la de body en estilos.css) para ejes, leyendas y
   tooltips; sin esto Chart.js usa la suya. */
const FUENTE_SITIO = '"Inter", system-ui, "Segoe UI", Roboto, Arial, sans-serif';


/* --- Fechas (días de Costa Rica) ------------------------------------- */

function fechaLocal(instante = new Date()) {
  /* «en-CA» da YYYY-MM-DD. */
  return instante.toLocaleDateString("en-CA", { timeZone: ZONA });
}

function sumarDias(fecha, dias) {
  const [a, m, d] = fecha.split("-").map(Number);
  const utc = new Date(Date.UTC(a, m - 1, d + dias));
  return utc.toISOString().slice(0, 10);
}

function rangoPorDefecto(hoy = fechaLocal()) {
  return { desde: sumarDias(hoy, -(DIAS_POR_DEFECTO - 1)), hasta: hoy };
}

/* Días entre dos fechas YYYY-MM-DD, contando las dos. */
function diasDelRango(desde, hasta) {
  const ms = Date.parse(`${hasta}T00:00:00Z`) - Date.parse(`${desde}T00:00:00Z`);
  return Math.round(ms / 86400000) + 1;
}

/* El período anterior de la misma duración, justo antes de «desde»:
   del 01/10 al 05/10 (5 días) → del 26/09 al 30/09. */
function rangoAnterior(desde, hasta) {
  const dias = diasDelRango(desde, hasta);
  return { desde: sumarDias(desde, -dias), hasta: sumarDias(desde, -1) };
}

/* ``area``: un id de área, «sin» (Sin área) o vacío (todas). */
function urlMetricas(desde, hasta, area = "") {
  const params = new URLSearchParams();
  if (desde) params.set("desde", desde);
  if (hasta) params.set("hasta", hasta);
  if (area === "sin") params.set("sin_area", "true");
  else if (/^\d+$/.test(String(area || ""))) params.set("area", String(area));
  return `${API_METRICAS_URL}?${params.toString()}`;
}

/* 2026-10-01 → 01/10/2026. */
function fechaLarga(fecha) {
  const [a, m, d] = String(fecha || "").split("-");
  return a && m && d ? `${d}/${m}/${a}` : "—";
}

function diaCorto(fecha) {
  const [, m, d] = fecha.split("-");
  return `${d}/${m}`;
}

/* 0.5 → «menos de 1 h», 5 → «5 h», 28 → «1 d 4 h», null → «—». */
function formatearHoras(horas) {
  if (horas === null || horas === undefined) return "—";
  if (horas < 1) return "menos de 1 h";
  const total = Math.round(horas);
  const dias = Math.floor(total / 24);
  const resto = total % 24;
  if (!dias) return `${total} h`;
  return resto ? `${dias} d ${resto} h` : `${dias} d`;
}

/* --- DOM ---------------------------------------------------------------- */

function elementos() {
  return {
    form: document.getElementById("form-rango"),
    desde: document.getElementById("desde"),
    hasta: document.getElementById("hasta"),
    area: document.getElementById("m-area"),
    aplicar: document.getElementById("aplicar"),
    imprimir: document.getElementById("imprimir-informe"),
    estado: document.getElementById("estado-carga"),
    informe: document.getElementById("informe"),
    alcance: document.getElementById("informe-alcance"),
  };
}

function mostrarEstado(mensaje, tipo = "") {
  const { estado } = elementos();
  estado.textContent = mensaje;
  estado.className = `estado ${tipo}`.trim();
  estado.hidden = !mensaje;
}

function nodo(tag, clase, texto) {
  const el = document.createElement(tag);
  if (clase) el.className = clase;
  if (texto !== undefined) el.textContent = texto;
  return el;
}

/* --- Números ------------------------------------------------------------- */

const MENOS = "\u2212"; // «−», el signo menos tipográfico

function porcentaje(parte, total) {
  if (!total) return "—";
  return `${Math.round((parte * 100) / total)} %`;
}

function conSigno(valor, texto = String(Math.abs(valor))) {
  if (valor > 0) return `+${texto}`;
  if (valor < 0) return `${MENOS}${texto}`;
  return texto;
}

/* Variación frente al período anterior, sin colores: «+3 (+25 %)»,
   «−2 h (−10 %)», «Sin cambio» o «—» si no hay dato anterior. */
function variacion(actual, anterior, { horas = false } = {}) {
  if (actual === null || actual === undefined || anterior === null || anterior === undefined) return "—";
  const diferencia = horas ? Math.round((actual - anterior) * 10) / 10 : actual - anterior;
  if (diferencia === 0) return "Sin cambio";
  const cantidad = conSigno(diferencia, horas ? formatearHoras(Math.abs(diferencia)) : String(Math.abs(diferencia)));
  if (!anterior) return cantidad;
  const pct = Math.round((Math.abs(diferencia) * 100) / Math.abs(anterior));
  return `${cantidad} (${conSigno(diferencia, `${pct} %`)})`;
}

/* «5 (42 %)»: cantidad y parte de los creados. */
function cantidadYParte(cantidad, total) {
  if (cantidad === null || cantidad === undefined) return "—";
  return total ? `${cantidad} (${porcentaje(cantidad, total)})` : String(cantidad);
}

/* --- Tablas -------------------------------------------------------------- */

/* Llena el <tbody> de una tabla: cada fila es una lista de celdas; las
   que no son la primera van alineadas a la derecha (números) salvo que se
   pida texto. ``total`` pinta la fila en negrita. */
function llenarTabla(id, filas, { textos = [0] } = {}) {
  const tabla = document.getElementById(id);
  if (!tabla) return;
  const cuerpo = tabla.querySelector("tbody");
  cuerpo.replaceChildren();
  filas.forEach(({ celdas, total = false, vacia = false }) => {
    const tr = nodo("tr", total ? "fila-total" : "");
    if (vacia) {
      const td = nodo("td", "celda-vacia", celdas[0]);
      td.colSpan = tabla.querySelectorAll("thead th").length || 1;
      tr.appendChild(td);
    } else {
      celdas.forEach((valor, i) => {
        const celda = nodo(i === 0 ? "th" : "td", textos.includes(i) ? "" : "num", String(valor));
        if (i === 0) celda.scope = "row";
        tr.appendChild(celda);
      });
    }
    cuerpo.appendChild(tr);
  });
}

function filasResumen(t, a) {
  const anterior = (campo) => (a ? a[campo] : null);
  return [
    { celdas: ["Tickets creados", t.creados_periodo, a ? a.creados_periodo : "—",
      variacion(t.creados_periodo, anterior("creados_periodo"))] },
    { celdas: ["Tickets resueltos", t.resueltos_periodo, a ? a.resueltos_periodo : "—",
      variacion(t.resueltos_periodo, anterior("resueltos_periodo"))] },
    { celdas: ["Tiempo promedio de resolución", formatearHoras(t.tiempo_promedio_horas),
      a ? formatearHoras(a.tiempo_promedio_horas) : "—",
      variacion(t.tiempo_promedio_horas, anterior("tiempo_promedio_horas"), { horas: true })] },
    { celdas: ["Creados por correo", cantidadYParte(t.por_correo, t.creados_periodo),
      a ? cantidadYParte(a.por_correo, a.creados_periodo) : "—", variacion(t.por_correo, anterior("por_correo"))] },
    { celdas: ["Creados por la web", cantidadYParte(t.por_web, t.creados_periodo),
      a ? cantidadYParte(a.por_web, a.creados_periodo) : "—", variacion(t.por_web, anterior("por_web"))] },
  ];
}

function filasHoy(t) {
  const nuevo = t.nuevo !== undefined ? t.nuevo : t.abiertos - t.en_proceso;
  return [
    { celdas: ["Nuevo", nuevo, porcentaje(nuevo, t.abiertos)] },
    { celdas: ["En proceso", t.en_proceso, porcentaje(t.en_proceso, t.abiertos)] },
    { celdas: ["Total abiertos", t.abiertos, t.abiertos ? "100 %" : "—"], total: true },
  ];
}

function filasCategoria(categorias) {
  const total = categorias.reduce((suma, c) => suma + c.total, 0);
  return [
    ...categorias.map((c) => ({ celdas: [c.nombre, c.total, porcentaje(c.total, total)] })),
    { celdas: ["Total", total, total ? "100 %" : "—"], total: true },
  ];
}

function nombreTecnico(p) {
  const rol = p.rol && p.rol !== "Técnico" ? ` (${p.rol})` : "";
  return `${p.nombre}${rol}${p.activo ? "" : " · desactivado"}`;
}

/* Ordenada por abiertos hoy (el servidor ya la manda así); «Sin asignar»
   al final, con los abiertos que no tienen persona. */
function filasTecnicos(datos) {
  const filas = [...datos.por_persona]
    .sort((x, y) => y.abiertos - x.abiertos || y.resueltos - x.resueltos)
    .map((p) => ({ celdas: [nombreTecnico(p), p.area || "—", p.abiertos, p.resueltos] }));
  if (datos.sin_asignar_abiertos) {
    filas.push({ celdas: ["Sin asignar", "—", datos.sin_asignar_abiertos, "—"] });
  }
  return filas.length ? filas : [{ celdas: ["No hay tickets asignados en el período."], vacia: true }];
}

function pintarTablas(datos, anteriores) {
  llenarTabla("tabla-resumen", filasResumen(datos.tarjetas, anteriores));
  llenarTabla("tabla-hoy", filasHoy(datos.tarjetas));
  llenarTabla("tabla-categoria", filasCategoria(datos.por_categoria));
  llenarTabla("tabla-tecnicos", filasTecnicos(datos), { textos: [0, 1] });
}

/* «Período: 01/10/2026 al 30/10/2026 · Departamento: Todos». */
function textoAlcance(desde, hasta, departamento) {
  return `Período: ${fechaLarga(desde)} al ${fechaLarga(hasta)} · Departamento: ${departamento || "Todos"}`;
}

function nombreDepartamento() {
  const { area } = elementos();
  if (!area || area.selectedIndex === undefined || area.selectedIndex < 0 || !area.options) return "Todos";
  const opcion = area.options[area.selectedIndex];
  return opcion ? opcion.textContent : "Todos";
}

/* Tabla de datos debajo de cada gráfico («Ver datos»). */
function tablaDatos(encabezados, filas) {
  const t = nodo("table", "tabla-informe");
  const thead = nodo("thead");
  const fila = nodo("tr");
  encabezados.forEach((e, i) => fila.appendChild(nodo("th", i ? "num" : "", e)));
  thead.appendChild(fila);
  t.appendChild(thead);
  const tbody = nodo("tbody");
  filas.forEach((valores) => {
    const tr = nodo("tr");
    valores.forEach((v, i) => tr.appendChild(nodo("td", i ? "num" : "", String(v))));
    tbody.appendChild(tr);
  });
  t.appendChild(tbody);
  return t;
}

function pintarDatosDeGraficos(s) {
  const bloques = {
    "g-estado": tablaDatos(["Estado", "Tickets"], s.estado.map((e) => [e.nombre, e.total])),
    "g-dia": tablaDatos(["Día", "Tickets creados"], s.dias.map((d) => [fechaLarga(d.fecha), d.total])),
  };
  Object.entries(bloques).forEach(([id, contenido]) => {
    const figura = document.getElementById(id);
    if (figura) figura.querySelector(".grafico-datos > div").replaceChildren(contenido);
  });
}

/* --- Gráficos (Chart.js) ----------------------------------------------- */

function colores() {
  const valores = { ...COLORES_POR_DEFECTO };
  if (typeof getComputedStyle !== "function" || !document.documentElement) return valores;
  const estilo = getComputedStyle(document.documentElement);
  const leer = (variable, actual) => (estilo.getPropertyValue(variable) || "").trim() || actual;
  valores.barra = leer("--color-primario", valores.barra);
  valores.texto = leer("--color-tenue", valores.texto);
  valores.eje = leer("--color-borde-fuerte", valores.eje);
  valores.rejilla = leer("--color-borde", valores.rejilla);
  return valores;
}

/* Escribe el número arriba de cada barra. */
const valoresEnBarras = {
  id: "valoresEnBarras",
  afterDatasetsDraw(chart, _args, opciones) {
    if (!opciones || !opciones.activo) return;
    const { ctx } = chart;
    ctx.save();
    ctx.fillStyle = opciones.color;
    ctx.font = `600 ${opciones.chico ? 10 : 12}px ${FUENTE_SITIO}`;
    ctx.textAlign = "center";
    ctx.textBaseline = "bottom";
    chart.getDatasetMeta(0).data.forEach((barra, i) => {
      const valor = chart.data.datasets[0].data[i];
      if (opciones.ocultarCeros && !valor) return;
      ctx.fillText(String(valor), barra.x, barra.y - 3);
    });
    ctx.restore();
  },
};

/* Barras clásicas: un color, ejes visibles, líneas de fondo suaves y el
   número arriba de cada barra. Sin esquinas redondeadas ni leyenda. */
function barras(canvas, etiquetas, valores, c, { muchas = false } = {}) {
  return new Chart(canvas, {
    type: "bar",
    data: {
      labels: etiquetas,
      datasets: [{ label: "Tickets", data: valores, backgroundColor: c.barra, borderWidth: 0,
                   categoryPercentage: 0.8, barPercentage: 0.9, maxBarThickness: 56 }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      layout: { padding: { top: 18 } },
      plugins: {
        legend: { display: false },
        tooltip: { displayColors: false },
        valoresEnBarras: { activo: true, color: c.texto, chico: muchas, ocultarCeros: muchas },
      },
      scales: {
        x: { grid: { display: false }, border: { display: true, color: c.eje },
             ticks: { color: c.texto, autoSkip: true, maxRotation: 0, maxTicksLimit: muchas ? 10 : undefined } },
        y: { beginAtZero: true, grid: { color: c.rejilla }, border: { display: true, color: c.eje },
             ticks: { color: c.texto, precision: 0 } },
      },
    },
    plugins: [valoresEnBarras],
  });
}

function lienzo(id) {
  const figura = document.getElementById(id);
  return figura ? figura.querySelector("canvas") : null;
}

let graficos = [];

function pintarGraficos(s, c = colores()) {
  graficos.forEach((g) => g.destroy());
  graficos = [];
  const disponible = typeof Chart === "function";
  document.querySelectorAll(".informe-grafico").forEach((figura) => {
    figura.querySelector(".grafico-lienzo").hidden = !disponible;
    figura.querySelector(".grafico-datos").open = !disponible;
  });
  if (!disponible) return false;
  if (Chart.defaults && Chart.defaults.font) Chart.defaults.font.family = FUENTE_SITIO;
  graficos = [
    barras(lienzo("g-estado"), s.estado.map((e) => e.nombre), s.estado.map((e) => e.total), c),
    barras(lienzo("g-dia"), s.dias.map((d) => diaCorto(d.fecha)), s.dias.map((d) => d.total), c,
      { muchas: s.dias.length > 31 }),
  ];
  return true;
}

let ultimasSeries = null;

function pintar(datos, anteriores) {
  const { alcance } = elementos();
  if (alcance) alcance.textContent = textoAlcance(datos.desde, datos.hasta, nombreDepartamento());
  pintarTablas(datos, anteriores);
  const s = { estado: datos.por_estado, dias: datos.por_dia };
  ultimasSeries = s;
  pintarDatosDeGraficos(s);
  return pintarGraficos(s);
}

/* Al cambiar entre modo claro y oscuro se vuelven a dibujar los gráficos
   con los colores nuevos; al imprimir, en grises, y al terminar, como
   estaban. */
if (typeof window !== "undefined" && typeof window.addEventListener === "function") {
  window.addEventListener("beforeprint", () => { if (ultimasSeries) pintarGraficos(ultimasSeries, COLORES_IMPRESION); });
  window.addEventListener("afterprint", () => { if (ultimasSeries) pintarGraficos(ultimasSeries); });
}
if (typeof document !== "undefined" && typeof document.addEventListener === "function") {
  document.addEventListener("tema-cambiado", () => {
    if (ultimasSeries) pintarGraficos(ultimasSeries);
  });
}

/* --- Carga ------------------------------------------------------------- */

async function cargarTarjetasAnteriores({ desde, hasta }, area = "") {
  try {
    const response = await fetchWithAuth(urlMetricas(desde, hasta, area));
    if (!response.ok) return null;
    const datos = await response.json();
    return datos && datos.tarjetas ? datos.tarjetas : null;
  } catch (error) {
    console.error("GET /api/metricas (período anterior):", error);
    return null;
  }
}

async function cargarMetricas() {
  const { desde, hasta, aplicar, area, informe } = elementos();
  const areaElegida = area ? String(area.value || "") : "";
  if (!desde.value || !hasta.value) {
    mostrarEstado("Seleccione las dos fechas.", "error");
    return;
  }
  aplicar.disabled = true;
  mostrarEstado("");
  const zonas = [informe];
  zonas.forEach((zona) => marcarCargando(zona, true));
  const previo = rangoAnterior(desde.value, hasta.value);
  try {
    /* Las dos consultas salen juntas; si falla la del período anterior,
       el informe se muestra igual, con «—» en esa columna. */
    const [response, anteriores] = await Promise.all([
      fetchWithAuth(urlMetricas(desde.value, hasta.value, areaElegida)),
      cargarTarjetasAnteriores(previo, areaElegida),
    ]);
    const datos = await response.json().catch(() => null);
    if (response.ok && datos) {
      const conGraficos = pintar(datos, anteriores);
      mostrarEstado(
        conGraficos ? "" : "No se pudieron cargar los gráficos. Los datos se muestran en tablas.",
        conGraficos ? "" : "vacio"
      );
    } else if (response.status === 403) {
      mostrarEstado("Su rol no tiene permiso para ver las métricas.", "error");
    } else {
      const detalle = datos && typeof datos.detail === "string" ? datos.detail : "";
      mostrarEstado(detalle || `No se pudieron cargar las métricas (${response.status}).`, "error");
    }
  } catch (error) {
    console.error("GET /api/metricas:", error);
    mostrarEstado("Error al comunicarse con la API.", "error");
  } finally {
    zonas.forEach((zona) => marcarCargando(zona, false));
    aplicar.disabled = false;
  }
}

async function iniciarMetricas() {
  const { form, desde, hasta, area, imprimir } = elementos();
  if (!form) return;
  if (area && typeof cargarAreas === "function") {
    llenarSelectAreas(area, await cargarAreas(), { primera: "Todos", sinArea: true });
    area.addEventListener("change", () => cargarMetricas());
  }
  const rango = rangoPorDefecto();
  desde.value = rango.desde;
  hasta.value = rango.hasta;
  desde.max = rango.hasta;
  hasta.max = rango.hasta;
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    cargarMetricas();
  });
  if (imprimir) imprimir.addEventListener("click", () => window.print());
  await cargarMetricas();
}

if (typeof document !== "undefined") {
  document.addEventListener("DOMContentLoaded", iniciarMetricas);
}
