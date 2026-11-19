/* Métricas (port de frontend/js/metricas.js, sin DOM): fechas de Costa
   Rica, el período anterior y las filas de cada tabla. Los números los
   calcula el servidor. */
const ZONA = "America/Costa_Rica";
const DIAS_POR_DEFECTO = 30;
const MENOS = "−";

export const fechaLocal = (instante = new Date()) => instante.toLocaleDateString("en-CA", { timeZone: ZONA });

export function sumarDias(fecha, dias) {
  const [a, m, d] = fecha.split("-").map(Number);
  return new Date(Date.UTC(a, m - 1, d + dias)).toISOString().slice(0, 10);
}

export const rangoPorDefecto = (hoy = fechaLocal()) => ({ desde: sumarDias(hoy, -(DIAS_POR_DEFECTO - 1)), hasta: hoy });

export function diasDelRango(desde, hasta) {
  return Math.round((Date.parse(`${hasta}T00:00:00Z`) - Date.parse(`${desde}T00:00:00Z`)) / 86400000) + 1;
}

export function rangoAnterior(desde, hasta) {
  const dias = diasDelRango(desde, hasta);
  return { desde: sumarDias(desde, -dias), hasta: sumarDias(desde, -1) };
}

export function urlMetricas(desde, hasta, area = "") {
  const params = new URLSearchParams();
  if (desde) params.set("desde", desde);
  if (hasta) params.set("hasta", hasta);
  if (area === "sin") params.set("sin_area", "true");
  else if (/^\d+$/.test(String(area || ""))) params.set("area", String(area));
  return `/api/metricas?${params.toString()}`;
}

export function fechaLarga(fecha) {
  const [a, m, d] = String(fecha || "").split("-");
  return a && m && d ? `${d}/${m}/${a}` : "—";
}

export function diaCorto(fecha) {
  const [, m, d] = fecha.split("-");
  return `${d}/${m}`;
}

export function formatearHoras(horas) {
  if (horas === null || horas === undefined) return "—";
  if (horas < 1) return "menos de 1 h";
  const total = Math.round(horas);
  const dias = Math.floor(total / 24);
  const resto = total % 24;
  if (!dias) return `${total} h`;
  return resto ? `${dias} d ${resto} h` : `${dias} d`;
}

export const porcentaje = (parte, total) => (total ? `${Math.round((parte * 100) / total)} %` : "—");

function conSigno(valor, texto = String(Math.abs(valor))) {
  if (valor > 0) return `+${texto}`;
  if (valor < 0) return `${MENOS}${texto}`;
  return texto;
}

export function variacion(actual, anterior, { horas = false } = {}) {
  if (actual === null || actual === undefined || anterior === null || anterior === undefined) return "—";
  const diferencia = horas ? Math.round((actual - anterior) * 10) / 10 : actual - anterior;
  if (diferencia === 0) return "Sin cambio";
  const cantidad = conSigno(diferencia, horas ? formatearHoras(Math.abs(diferencia)) : String(Math.abs(diferencia)));
  if (!anterior) return cantidad;
  const pct = Math.round((Math.abs(diferencia) * 100) / Math.abs(anterior));
  return `${cantidad} (${conSigno(diferencia, `${pct} %`)})`;
}

function cantidadYParte(cantidad, total) {
  if (cantidad === null || cantidad === undefined) return "—";
  return total ? `${cantidad} (${porcentaje(cantidad, total)})` : String(cantidad);
}

export function filasResumen(t, a) {
  const anterior = (campo) => (a ? a[campo] : null);
  return [
    { celdas: ["Tickets creados", t.creados_periodo, a ? a.creados_periodo : "—", variacion(t.creados_periodo, anterior("creados_periodo"))] },
    { celdas: ["Tickets resueltos", t.resueltos_periodo, a ? a.resueltos_periodo : "—", variacion(t.resueltos_periodo, anterior("resueltos_periodo"))] },
    { celdas: ["Tiempo promedio de resolución", formatearHoras(t.tiempo_promedio_horas), a ? formatearHoras(a.tiempo_promedio_horas) : "—",
      variacion(t.tiempo_promedio_horas, anterior("tiempo_promedio_horas"), { horas: true })] },
    { celdas: ["Creados por correo", cantidadYParte(t.por_correo, t.creados_periodo), a ? cantidadYParte(a.por_correo, a.creados_periodo) : "—",
      variacion(t.por_correo, anterior("por_correo"))] },
    { celdas: ["Creados por la web", cantidadYParte(t.por_web, t.creados_periodo), a ? cantidadYParte(a.por_web, a.creados_periodo) : "—",
      variacion(t.por_web, anterior("por_web"))] },
  ];
}

export function filasHoy(t) {
  const nuevo = t.nuevo !== undefined ? t.nuevo : t.abiertos - t.en_proceso;
  return [
    { celdas: ["Nuevo", nuevo, porcentaje(nuevo, t.abiertos)] },
    { celdas: ["En proceso", t.en_proceso, porcentaje(t.en_proceso, t.abiertos)] },
    { celdas: ["Total abiertos", t.abiertos, t.abiertos ? "100 %" : "—"], total: true },
  ];
}

export function filasCategoria(categorias) {
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

export function filasTecnicos(datos) {
  const filas = [...datos.por_persona]
    .sort((x, y) => y.abiertos - x.abiertos || y.resueltos - x.resueltos)
    .map((p) => ({ celdas: [nombreTecnico(p), p.area || "—", p.abiertos, p.resueltos] }));
  if (datos.sin_asignar_abiertos) filas.push({ celdas: ["Sin asignar", "—", datos.sin_asignar_abiertos, "—"] });
  return filas.length ? filas : [{ celdas: ["No hay tickets asignados en el período."], vacia: true }];
}

export const textoAlcance = (desde, hasta, departamento) =>
  `Período: ${fechaLarga(desde)} al ${fechaLarga(hasta)} · Departamento: ${departamento || "Todos"}`;
