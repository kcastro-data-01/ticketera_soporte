/* Barras clásicas con Chart.js (la misma versión 4.4.1 que la app actual,
   empaquetada en vez del CDN): un color, ejes visibles, rejilla suave y el
   número arriba de cada barra. */
import { BarController, BarElement, CategoryScale, Chart, LinearScale, Tooltip } from "chart.js";

Chart.register(BarController, BarElement, CategoryScale, LinearScale, Tooltip);

export const COLORES_POR_DEFECTO = { barra: "#1746e0", texto: "#5d6880", eje: "#c4cddd", rejilla: "#eef1f5" };
export const COLORES_IMPRESION = { barra: "#555555", texto: "#000000", eje: "#000000", rejilla: "#dddddd" };
const FUENTE_SITIO = '"Inter", system-ui, "Segoe UI", Roboto, Arial, sans-serif';

export function coloresDelTema() {
  const valores = { ...COLORES_POR_DEFECTO };
  const estilo = getComputedStyle(document.documentElement);
  const leer = (variable, actual) => (estilo.getPropertyValue(variable) || "").trim() || actual;
  valores.barra = leer("--color-primario", valores.barra);
  valores.texto = leer("--color-tenue", valores.texto);
  valores.eje = leer("--color-borde-fuerte", valores.eje);
  valores.rejilla = leer("--color-borde", valores.rejilla);
  return valores;
}

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

export function barras(canvas, etiquetas, valores, c, { muchas = false } = {}) {
  if (Chart.defaults && Chart.defaults.font) Chart.defaults.font.family = FUENTE_SITIO;
  return new Chart(canvas, {
    type: "bar",
    data: {
      labels: etiquetas,
      datasets: [{ label: "Tickets", data: valores, backgroundColor: c.barra, borderWidth: 0, categoryPercentage: 0.8, barPercentage: 0.9, maxBarThickness: 56 }],
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
        x: { grid: { display: false }, border: { display: true, color: c.eje }, ticks: { color: c.texto, autoSkip: true, maxRotation: 0, maxTicksLimit: muchas ? 10 : undefined } },
        y: { beginAtZero: true, grid: { color: c.rejilla }, border: { display: true, color: c.eje }, ticks: { color: c.texto, precision: 0 } },
      },
    },
    plugins: [valoresEnBarras],
  });
}
