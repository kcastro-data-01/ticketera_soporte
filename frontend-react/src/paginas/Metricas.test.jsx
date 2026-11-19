import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { conSesion, renderApp, respuesta, simularFetch } from "../pruebas/ayudas.jsx";
import { formatearHoras, rangoAnterior, variacion } from "../metricas/calculos.js";

const dibujos = vi.hoisted(() => ({ creados: [] }));
vi.mock("../metricas/graficos.js", () => ({
  COLORES_IMPRESION: { barra: "#555555" },
  coloresDelTema: () => ({ barra: "#1746e0" }),
  barras: vi.fn((canvas, etiquetas, valores, colores) => {
    const g = { etiquetas, valores, colores, destroy: vi.fn() };
    dibujos.creados.push(g);
    return g;
  }),
}));

const DATOS = {
  desde: "2026-10-21", hasta: "2026-11-19",
  tarjetas: { creados_periodo: 12, resueltos_periodo: 8, tiempo_promedio_horas: 28, por_correo: 3, por_web: 9, abiertos: 6, en_proceso: 2, nuevo: 4 },
  por_estado: [{ nombre: "Nuevo", total: 4 }, { nombre: "En proceso", total: 2 }],
  por_categoria: [{ nombre: "Hardware", total: 6 }, { nombre: "Red", total: 6 }],
  por_dia: [{ fecha: "2026-11-18", total: 3 }, { fecha: "2026-11-19", total: 1 }],
  por_persona: [{ nombre: "Tomás Técnico", rol: "Técnico", activo: true, area: "Redes", abiertos: 3, resueltos: 5 },
    { nombre: "Ana Admin", rol: "Administrador", activo: false, area: null, abiertos: 4, resueltos: 1 }],
  sin_asignar_abiertos: 2,
};

function servidor() {
  return simularFetch([
    [(u) => u.startsWith("/api/metricas") && u.includes("desde=2026-10-21"), () => respuesta(DATOS)],
    [(u) => u.startsWith("/api/metricas"), () => respuesta({ ...DATOS, tarjetas: { ...DATOS.tarjetas, creados_periodo: 8, tiempo_promedio_horas: 30 } })],
    ["/api/areas", respuesta([{ id: 1, name: "Soporte IT" }])],
    ["/api/tickets/summary", respuesta({ mios_abiertos: 0 })],
    ["/api/tickets", respuesta([])],
  ]);
}

const filas = (id) => [...document.querySelectorAll(`#${id} tbody tr`)].map((tr) => [...tr.children].map((c) => c.textContent));

describe("Métricas (/metricas)", () => {
  it("solo Administrador", async () => {
    conSesion("Técnico");
    servidor();
    renderApp("/metricas");
    expect(await screen.findByRole("heading", { name: "Acceso restringido" })).toBeInTheDocument();
  });

  it("informe completo: resumen con el período anterior, hoy, categorías, técnicos y gráficos", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-11-19T18:00:00Z"));
    conSesion("Administrador");
    const { llamadas } = servidor();
    renderApp("/metricas");
    await waitFor(() => expect(filas("tabla-resumen")).toHaveLength(5));
    expect(screen.getByLabelText("Desde")).toHaveValue("2026-10-21");
    expect(screen.getByLabelText("Hasta")).toHaveValue("2026-11-19");
    expect(llamadas.some((l) => l.url === "/api/metricas?desde=2026-09-21&hasta=2026-10-20")).toBe(true);
    expect(filas("tabla-resumen")[0]).toEqual(["Tickets creados", "12", "8", "+4 (+50 %)"]);
    expect(filas("tabla-resumen")[2]).toEqual(["Tiempo promedio de resolución", "1 d 4 h", "1 d 6 h", "−2 h (−7 %)"]);
    expect(filas("tabla-hoy")).toEqual([["Nuevo", "4", "67 %"], ["En proceso", "2", "33 %"], ["Total abiertos", "6", "100 %"]]);
    expect(filas("tabla-categoria").at(-1)).toEqual(["Total", "12", "100 %"]);
    expect(filas("tabla-tecnicos")).toEqual([
      ["Ana Admin (Administrador) · desactivado", "—", "4", "1"], ["Tomás Técnico", "Redes", "3", "5"], ["Sin asignar", "—", "2", "—"],
    ]);
    expect(screen.getByText("Período: 21/10/2026 al 19/11/2026 · Departamento: Todos")).toBeInTheDocument();
    await waitFor(() => expect(dibujos.creados.length).toBeGreaterThanOrEqual(2));
    expect(dibujos.creados.at(-1).etiquetas).toEqual(["18/11", "19/11"]);
    const datos = within(document.getElementById("g-dia")).getByText("18/11/2026");
    expect(datos).toBeInTheDocument();
  });

  it("cambiar de departamento vuelve a pedir con ese filtro", async () => {
    conSesion("Administrador");
    const { llamadas } = servidor();
    renderApp("/metricas");
    await waitFor(() => expect(screen.getByRole("option", { name: "Soporte IT" })).toBeInTheDocument());
    await userEvent.selectOptions(screen.getByLabelText("Departamento"), "sin");
    await waitFor(() => expect(llamadas.some((l) => l.url.includes("sin_area=true"))).toBe(true));
    await userEvent.selectOptions(screen.getByLabelText("Departamento"), "1");
    await waitFor(() => expect(llamadas.some((l) => /area=1(&|$)/.test(l.url))).toBe(true));
    await waitFor(() => expect(screen.getByText(/Departamento: Soporte IT/)).toBeInTheDocument());
  });

  it("al imprimir los gráficos se redibujan en grises", async () => {
    conSesion("Administrador");
    servidor();
    renderApp("/metricas");
    await waitFor(() => expect(dibujos.creados.length).toBeGreaterThanOrEqual(2));
    window.dispatchEvent(new Event("beforeprint"));
    expect(dibujos.creados.at(-1).colores).toEqual({ barra: "#555555" });
  });

  it("cálculos", () => {
    expect(rangoAnterior("2026-10-01", "2026-10-05")).toEqual({ desde: "2026-09-26", hasta: "2026-09-30" });
    expect(formatearHoras(0.5)).toBe("menos de 1 h");
    expect(formatearHoras(48)).toBe("2 d");
    expect(variacion(5, 5)).toBe("Sin cambio");
    expect(variacion(3, 0)).toBe("+3");
    expect(variacion(null, 2)).toBe("—");
  });
});
