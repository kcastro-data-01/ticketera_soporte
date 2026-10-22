/* Página de métricas (Supervisor y Administrador): consulta
   GET /api/metricas?desde=&hasta= y pinta tarjetas y gráficos (Chart.js).
   Los números los calcula el servidor; aquí solo se muestran.
   Cada gráfico tiene debajo su tabla («Ver datos»); si Chart.js no carga
   (sin internet), las tablas quedan abiertas y la página sirve igual.
   Todo lo que llega del servidor se pinta como texto, nunca como HTML. */

const API_METRICAS_URL = "/api/metricas";
const ZONA = "America/Costa_Rica";
const DIAS_POR_DEFECTO = 30;
/* Paleta validada (dataviz): serie 1 azul, serie 2 naranja. Se pueden
   cambiar en estilos.css con --color-serie-1 / --color-serie-2. */
const COLORES_POR_DEFECTO = {
  serie1: "#2a78d6",
  serie2: "#eb6834",
  texto: "#5d6880",
  rejilla: "#dde3ee",
  superficie: "#ffffff",
  radio: 6,
};

/* Letra del sitio (la de body en estilos.css) para ejes, leyendas y
   tooltips; sin esto Chart.js usa la suya. */
const FUENTE_SITIO = '"Inter", system-ui, "Segoe UI", Roboto, Arial, sans-serif';

let graficos = [];

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

function urlMetricas(desde, hasta) {
  const params = new URLSearchParams({ desde, hasta });
  return `${API_METRICAS_URL}?${params.toString()}`;
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
    aplicar: document.getElementById("aplicar"),
    estado: document.getElementById("estado-carga"),
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

function ponerTexto(id, texto) {
  const el = document.getElementById(id);
  if (el) el.textContent = texto;
}

function pintarTarjetas(datos) {
  const t = datos.tarjetas;
  ponerTexto("m-abiertos", String(t.abiertos));
  ponerTexto("m-en-proceso", String(t.en_proceso));
  ponerTexto("m-resueltos", String(t.resueltos_periodo));
  ponerTexto("m-promedio", formatearHoras(t.tiempo_promedio_horas));
  ponerTexto("m-origen", `${t.por_correo} / ${t.por_web}`);
  const porcentaje = t.creados_periodo ? Math.round((t.por_correo * 100) / t.creados_periodo) : 0;
  ponerTexto(
    "m-origen-nota",
    t.creados_periodo
      ? `${t.creados_periodo} creados en el período · ${porcentaje}% por correo`
      : "Ningún ticket creado en el período"
  );
}

/* --- Comparación con el período anterior --------------------------------
   Cada tarjeta del período muestra «▲ 12 % vs. período anterior», en verde
   si el cambio es bueno y en rojo si es malo. «Abiertos» y «En proceso»
   son el valor de hoy (no dependen del rango), así que no se comparan. */

const COMPARACIONES = [
  { id: "c-resueltos", campo: "resueltos_periodo", mejor: "subir" },
  { id: "c-promedio", campo: "tiempo_promedio_horas", mejor: "bajar" },
  { id: "c-origen", campo: "creados_periodo", mejor: "neutro", sufijo: " creados" },
];
const SIN_COMPARACION = ["c-abiertos", "c-en-proceso"];

/* Devuelve { texto, tono } con tono «bueno», «malo» o «neutro». */
function cambioVsAnterior(actual, anterior, mejor = "subir", sufijo = "") {
  const fin = " vs. período anterior";
  if (actual === null || actual === undefined || anterior === null || anterior === undefined) {
    return { texto: "Sin datos del período anterior", tono: "neutro" };
  }
  if (actual === anterior) return { texto: `= igual${fin}`, tono: "neutro" };
  const sube = actual > anterior;
  const flecha = sube ? "▲" : "▼";
  const tono = mejor === "neutro" ? "neutro" : sube === (mejor === "subir") ? "bueno" : "malo";
  if (!anterior) return { texto: `${flecha} desde 0${sufijo} en el período anterior`, tono };
  const porcentaje = Math.round((Math.abs(actual - anterior) * 100) / Math.abs(anterior));
  return { texto: `${flecha} ${porcentaje} %${sufijo}${fin}`, tono };
}

function pintarComparacion(tarjetas, anteriores) {
  COMPARACIONES.forEach(({ id, campo, mejor, sufijo }) => {
    const el = document.getElementById(id);
    if (!el) return;
    if (!anteriores) {
      el.hidden = true;
      return;
    }
    const { texto, tono } = cambioVsAnterior(tarjetas[campo], anteriores[campo], mejor, sufijo);
    el.textContent = texto;
    el.className = `metrica-cambio ${tono}`;
    el.hidden = false;
  });
  SIN_COMPARACION.forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.hidden = !anteriores;
  });
}

/* Tabla simple: encabezados + filas de texto. */
function tabla(encabezados, filas) {
  const t = nodo("table", "listado tabla-datos");
  const thead = nodo("thead");
  const fila = nodo("tr");
  encabezados.forEach((e) => fila.appendChild(nodo("th", "", e)));
  thead.appendChild(fila);
  t.appendChild(thead);
  const tbody = nodo("tbody");
  filas.forEach((valores) => {
    const tr = nodo("tr");
    valores.forEach((v) => tr.appendChild(nodo("td", "", String(v))));
    tbody.appendChild(tr);
  });
  t.appendChild(tbody);
  return t;
}

function etiquetaPersona(p) {
  return `${p.nombre} (${p.rol})${p.activo ? "" : " · desactivado"}`;
}

/* Lo que muestra cada gráfico, ya preparado para Chart.js y para la tabla. */
function series(datos) {
  const personas = datos.por_persona.map((p) => ({
    etiqueta: etiquetaPersona(p), abiertos: p.abiertos, resueltos: p.resueltos,
  }));
  if (datos.sin_asignar_abiertos) {
    personas.push({ etiqueta: "Sin asignar", abiertos: datos.sin_asignar_abiertos, resueltos: 0 });
  }
  return {
    estado: datos.por_estado,
    categoria: datos.por_categoria,
    personas,
    dias: datos.por_dia,
  };
}

function pintarTablas(s) {
  const bloques = {
    "g-estado": tabla(["Estado", "Tickets"], s.estado.map((e) => [e.nombre, e.total])),
    "g-categoria": tabla(["Categoría", "Tickets"], s.categoria.map((c) => [c.nombre, c.total])),
    "g-persona": s.personas.length
      ? tabla(["Persona (rol)", "Abiertos hoy", "Resueltos en el período"],
          s.personas.map((p) => [p.etiqueta, p.abiertos, p.resueltos]))
      : nodo("p", "estado", "No hay tickets asignados."),
    "g-dia": tabla(["Día", "Tickets creados"], s.dias.map((d) => [diaCorto(d.fecha), d.total])),
  };
  Object.entries(bloques).forEach(([id, contenido]) => {
    const figura = document.getElementById(id);
    if (!figura) return;
    figura.querySelector(".grafico-datos > div").replaceChildren(contenido);
  });
}

/* --- Gráficos (Chart.js) ----------------------------------------------- */

function colores() {
  const valores = { ...COLORES_POR_DEFECTO };
  if (typeof getComputedStyle !== "function" || !document.documentElement) return valores;
  const estilo = getComputedStyle(document.documentElement);
  const leer = (variable, actual) => (estilo.getPropertyValue(variable) || "").trim() || actual;
  valores.serie1 = leer("--color-serie-1", valores.serie1);
  valores.serie2 = leer("--color-serie-2", valores.serie2);
  valores.texto = leer("--color-tenue", valores.texto);
  valores.rejilla = leer("--color-borde", valores.rejilla);
  valores.superficie = leer("--color-superficie", valores.superficie);
  /* Esquinas de las barras: las mismas que el resto (--radio-suave). */
  const radio = Number.parseFloat(leer("--radio-suave", ""));
  if (Number.isFinite(radio)) valores.radio = radio;
  return valores;
}

/* Escribe el valor al final de cada barra (gráficos de una sola serie). */
const valoresEnBarras = {
  id: "valoresEnBarras",
  afterDatasetsDraw(chart, _args, opciones) {
    if (!opciones || !opciones.activo) return;
    const { ctx } = chart;
    ctx.save();
    ctx.fillStyle = opciones.color;
    ctx.font = `600 12px ${FUENTE_SITIO}`;
    ctx.textAlign = "center";
    ctx.textBaseline = "bottom";
    chart.getDatasetMeta(0).data.forEach((barra, i) => {
      const valor = chart.data.datasets[0].data[i];
      ctx.fillText(String(valor), barra.x, barra.y - 4);
    });
    ctx.restore();
  },
};

function base(c) {
  return {
    responsive: true,
    maintainAspectRatio: false,
    animation: false,
    plugins: {
      legend: { display: false },
      tooltip: { displayColors: false },
      valoresEnBarras: { activo: false, color: c.texto },
    },
    scales: {
      x: { grid: { display: false }, ticks: { color: c.texto } },
      y: { beginAtZero: true, grid: { color: c.rejilla }, border: { display: false },
           ticks: { color: c.texto, precision: 0 } },
    },
  };
}

function barrasSimples(canvas, filas, c) {
  const opciones = base(c);
  opciones.plugins.valoresEnBarras.activo = true;
  opciones.layout = { padding: { top: 20 } };
  return new Chart(canvas, {
    type: "bar",
    data: {
      labels: filas.map((f) => f.nombre),
      datasets: [{
        label: "Tickets", data: filas.map((f) => f.total), backgroundColor: c.serie1,
        borderRadius: c.radio, borderSkipped: "start", maxBarThickness: 48,
      }],
    },
    options: opciones,
    plugins: [valoresEnBarras],
  });
}

function barrasPersonas(canvas, personas, c) {
  const opciones = base(c);
  opciones.indexAxis = "y";
  opciones.plugins.legend = { display: true, position: "top", align: "start",
                              labels: { color: c.texto, boxWidth: 12, boxHeight: 12 } };
  opciones.plugins.tooltip = { displayColors: true };
  opciones.scales = {
    x: { beginAtZero: true, grid: { color: c.rejilla }, border: { display: false },
         ticks: { color: c.texto, precision: 0 } },
    y: { grid: { display: false }, ticks: { color: c.texto } },
  };
  const barra = { borderRadius: c.radio, borderSkipped: "start", borderColor: c.superficie,
                  borderWidth: 1, categoryPercentage: 0.7, barPercentage: 0.9, maxBarThickness: 18 };
  return new Chart(canvas, {
    type: "bar",
    data: {
      labels: personas.map((p) => p.etiqueta),
      datasets: [
        { ...barra, label: "Abiertos hoy", data: personas.map((p) => p.abiertos), backgroundColor: c.serie1 },
        { ...barra, label: "Resueltos en el período", data: personas.map((p) => p.resueltos), backgroundColor: c.serie2 },
      ],
    },
    options: opciones,
  });
}

function lineaDias(canvas, dias, c) {
  const opciones = base(c);
  opciones.interaction = { mode: "index", intersect: false };
  opciones.scales.x.ticks = { color: c.texto, autoSkip: true, maxRotation: 0, maxTicksLimit: 8 };
  return new Chart(canvas, {
    type: "line",
    data: {
      labels: dias.map((d) => diaCorto(d.fecha)),
      datasets: [{
        label: "Tickets creados", data: dias.map((d) => d.total), borderColor: c.serie1,
        backgroundColor: c.serie1, borderWidth: 2, tension: 0, pointRadius: dias.length > 45 ? 0 : 3,
        pointHoverRadius: 5, pointBorderColor: c.superficie, pointBorderWidth: 2,
      }],
    },
    options: opciones,
  });
}

function lienzo(id) {
  const figura = document.getElementById(id);
  return figura ? figura.querySelector("canvas") : null;
}

function pintarGraficos(s) {
  graficos.forEach((g) => g.destroy());
  graficos = [];
  const disponible = typeof Chart === "function";
  document.querySelectorAll(".grafico").forEach((figura) => {
    figura.querySelector(".grafico-lienzo").hidden = !disponible;
    figura.querySelector(".grafico-datos").open = !disponible;
  });
  if (!disponible) return false;

  if (Chart.defaults && Chart.defaults.font) Chart.defaults.font.family = FUENTE_SITIO;
  const c = colores();
  /* El gráfico de personas crece con la cantidad de filas. */
  const alto = Math.max(220, 46 * s.personas.length + 70);
  document.querySelector("#g-persona .grafico-lienzo").style.height = `${alto}px`;
  graficos = [
    barrasSimples(lienzo("g-estado"), s.estado, c),
    barrasSimples(lienzo("g-categoria"), s.categoria, c),
    barrasPersonas(lienzo("g-persona"), s.personas, c),
    lineaDias(lienzo("g-dia"), s.dias, c),
  ];
  return true;
}

let ultimasSeries = null;

function pintar(datos) {
  pintarTarjetas(datos);
  const s = series(datos);
  ultimasSeries = s;
  pintarTablas(s);
  return pintarGraficos(s);
}

/* Al cambiar entre modo claro y oscuro se vuelven a dibujar los gráficos
   con los colores nuevos (los datos son los mismos). */
if (typeof document !== "undefined" && typeof document.addEventListener === "function") {
  document.addEventListener("tema-cambiado", () => {
    if (ultimasSeries) pintarGraficos(ultimasSeries);
  });
}

/* --- Carga ------------------------------------------------------------- */

async function cargarTarjetasAnteriores({ desde, hasta }) {
  try {
    const response = await fetchWithAuth(urlMetricas(desde, hasta));
    if (!response.ok) return null;
    const datos = await response.json();
    return datos && datos.tarjetas ? datos.tarjetas : null;
  } catch (error) {
    console.error("GET /api/metricas (período anterior):", error);
    return null;
  }
}

async function cargarMetricas() {
  const { desde, hasta, aplicar } = elementos();
  if (!desde.value || !hasta.value) {
    mostrarEstado("Seleccione las dos fechas.", "error");
    return;
  }
  aplicar.disabled = true;
  mostrarEstado("");
  const zonas = [document.querySelector(".metricas-tarjetas"), document.querySelector(".metricas-graficos")];
  zonas.forEach((zona) => marcarCargando(zona, true));
  const previo = rangoAnterior(desde.value, hasta.value);
  try {
    /* Las dos consultas salen juntas; si falla la del período anterior,
       la página se muestra igual, sin comparación. */
    const [response, anteriores] = await Promise.all([
      fetchWithAuth(urlMetricas(desde.value, hasta.value)),
      cargarTarjetasAnteriores(previo),
    ]);
    const datos = await response.json().catch(() => null);
    if (response.ok && datos) {
      const conGraficos = pintar(datos);
      pintarComparacion(datos.tarjetas, anteriores);
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
  const { form, desde, hasta } = elementos();
  if (!form) return;
  const rango = rangoPorDefecto();
  desde.value = rango.desde;
  hasta.value = rango.hasta;
  desde.max = rango.hasta;
  hasta.max = rango.hasta;
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    cargarMetricas();
  });
  await cargarMetricas();
}

if (typeof document !== "undefined") {
  document.addEventListener("DOMContentLoaded", iniciarMetricas);
}
