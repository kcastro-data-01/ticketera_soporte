import { describe, expect, it } from "vitest";
import {
  antiguedadValida, buildTicketsUrl, estadoFiltro, filtrosDeUrl, ordenarTickets, siguienteOrden, textoTotal,
} from "./filtros.js";

const params = (url) => new URL(url, "http://x").searchParams;

describe("buildTicketsUrl", () => {
  it("sin filtros pide todos con el tope de 1000", () => {
    expect(buildTicketsUrl({})).toBe("/api/tickets?limit=1000");
  });

  it("manda cada filtro con el nombre de la API", () => {
    const p = params(buildTicketsUrl({
      search: "  impresora ", category: "Red", priority: "Alta", state: "Resuelto",
      mios: true, asignado: "7", area: "2", fecha: "2026-11-10",
    }));
    expect(p.get("search")).toBe("impresora");
    expect(p.get("category")).toBe("Red");
    expect(p.get("priority")).toBe("Alta");
    expect(p.getAll("state")).toEqual(["Resuelto"]);
    expect(p.get("mios")).toBe("true");
    expect(p.get("assigned_to")).toBe("7");
    expect(p.get("area")).toBe("2");
    expect(p.get("desde")).toBe("2026-11-10");
    expect(p.get("hasta")).toBe("2026-11-10");
  });

  it("«Abiertos» pide Nuevo y En proceso", () => {
    expect(params(buildTicketsUrl({ state: "abiertos" })).getAll("state")).toEqual(["Nuevo", "En proceso"]);
  });

  it("«Sin asignar» y «Sin departamento»", () => {
    const p = params(buildTicketsUrl({ asignado: "sin", area: "sin" }));
    expect(p.get("sin_asignar")).toBe("true");
    expect(p.get("sin_area")).toBe("true");
    expect(p.has("assigned_to")).toBe(false);
  });

  it("valores inválidos no se mandan", () => {
    const p = params(buildTicketsUrl({ state: "Pendientes", asignado: "x", area: "1;DROP" }));
    expect([...p.keys()]).toEqual(["limit"]);
  });

  it("antigüedad: creado_antes N días atrás", () => {
    const ahora = Date.parse("2026-11-19T12:00:00Z");
    expect(params(buildTicketsUrl({ antiguedad: 3 }, ahora)).get("creado_antes")).toBe("2026-11-16T12:00:00.000Z");
    expect(params(buildTicketsUrl({ antiguedad: 999 }, ahora)).has("creado_antes")).toBe(false);
  });
});

describe("filtros de la dirección", () => {
  const areas = [{ id: 1, name: "Redes" }];
  const usuarios = [{ id: 5, name: "Pedro" }];

  it("aplica solo los valores que existen", () => {
    const r = filtrosDeUrl("?area=1&estado=abiertos&prioridad=Crítica&asignado=5&antiguedad=7", { areas, usuarios });
    expect(r).toEqual({ filtros: { area: "1", state: "abiertos", priority: "Crítica", asignado: "5" }, antiguedad: 7 });
    expect(filtrosDeUrl("?area=9&asignado=8&prioridad=Urgente", { areas, usuarios }).filtros).toEqual({});
  });

  it("el Solicitante solo usa el estado", () => {
    expect(filtrosDeUrl("?area=1&estado=Nuevo&antiguedad=3", { solicitante: true, areas })).toEqual({ filtros: { state: "Nuevo" }, antiguedad: 0 });
  });
});

describe("orden y textos", () => {
  const tickets = [
    { id: 1, title: "b", priority: "Baja", state: "Cerrado", created_at: "2026-01-02" },
    { id: 2, title: "A", priority: "Crítica", state: "Nuevo", created_at: "2026-01-01" },
    { id: 3, title: "c", priority: "Alta", state: "En proceso", created_at: "2026-01-03" },
  ];
  it("ordena prioridad de Crítica a Baja y estado según el flujo", () => {
    expect(ordenarTickets(tickets, { campo: "priority", dir: "asc" }).map((t) => t.id)).toEqual([2, 3, 1]);
    expect(ordenarTickets(tickets, { campo: "state", dir: "desc" }).map((t) => t.id)).toEqual([1, 3, 2]);
    expect(ordenarTickets(tickets, { campo: "title", dir: "asc" }).map((t) => t.id)).toEqual([2, 1, 3]);
    expect(ordenarTickets(tickets, null)).toEqual(tickets);
  });
  it("primer clic ascendente, segundo descendente", () => {
    expect(siguienteOrden(null, "id")).toEqual({ campo: "id", dir: "asc" });
    expect(siguienteOrden({ campo: "id", dir: "asc" }, "id")).toEqual({ campo: "id", dir: "desc" });
  });
  it("total del listado", () => {
    expect(textoTotal(1)).toBe("1 ticket");
    expect(textoTotal(23)).toBe("23 tickets");
    expect(textoTotal(1500, 1000)).toBe("Se muestran 1000 de 1500 tickets. Use los filtros para acotar la lista.");
  });
  it("valida estado y antigüedad", () => {
    expect(estadoFiltro("Resuelto,Cerrado")).toBe("");
    expect(antiguedadValida("2.5")).toBe(0);
    expect(antiguedadValida("30")).toBe(30);
  });
});
