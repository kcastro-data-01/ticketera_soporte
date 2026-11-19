import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { conSesion, renderApp, respuesta, simularFetch } from "../pruebas/ayudas.jsx";
import { fraseCambio, leerHash, tituloDia } from "../historial/frases.js";

const PERSONAS = [
  { clave: "2", nombre: "Tomás Técnico", rol: "Técnico", departamento: "Redes", cambios: 3 },
  { clave: "sistema", nombre: "Sistema", rol: null, departamento: null, cambios: 1 },
  { clave: "5", nombre: "Sin cambios", rol: "Técnico", departamento: null, cambios: 0 },
];
const CAMBIOS = [
  { id: 1, ticket_id: 9, ticket_title: "VPN caída", action: "commented", new_value: "Ya revisé", author: "Tomás Técnico", created_at: "2026-11-19T15:00:00Z" },
  { id: 2, ticket_id: 9, ticket_title: "VPN caída", action: "state_changed", old_value: "Nuevo", new_value: "En proceso", author: "Tomás Técnico", created_at: "2026-11-19T14:00:00Z" },
  { id: 3, ticket_id: 4, ticket_title: "Impresora", action: "Cierre automático", author: "", created_at: "2026-11-18T14:00:00Z" },
];

function servidor({ total = 4, cajas = { cambios: 4, tickets: 2, comentarios: 1, cambios_estado: 1 }, estado = 200 } = {}) {
  return simularFetch([
    [(u) => u.startsWith("/api/history/resumen"), () => (estado === 200
      ? respuesta({ personas: PERSONAS, total, cajas })
      : respuesta({ detail: "x" }, { status: estado }))],
    [(u) => u.startsWith("/api/history?"), (u) => respuesta(new URL(u, "http://x").searchParams.get("offset") === "0" ? CAMBIOS : [CAMBIOS[2]])],
    ["/api/tickets/summary", respuesta({ mios_abiertos: 0 })],
    ["/api/tickets", respuesta([])],
  ]);
}

const ultimo = (llamadas, prefijo) => new URL(llamadas.filter((l) => l.url.startsWith(prefijo)).at(-1).url, "http://x").searchParams;

describe("Historial (/historial)", () => {
  it("solo con historial_global: el Solicitante ve Acceso restringido", async () => {
    conSesion("Solicitante");
    servidor();
    renderApp("/historial");
    expect(await screen.findByRole("heading", { name: "Acceso restringido" })).toBeInTheDocument();
  });

  it("personas a la izquierda, cajas y cambios por día con enlaces a /tickets/N", async () => {
    conSesion("Técnico");
    servidor();
    renderApp("/historial");
    const lista = await screen.findByRole("tablist", { name: "Personas" });
    const pestanas = within(lista).getAllByRole("tab");
    expect(pestanas.map((p) => p.querySelector(".depto-boton-nombre").textContent)).toEqual(["Todas las personas", "Tomás Técnico", "Sistema"]);
    expect(pestanas[0]).toHaveAttribute("aria-selected", "true");
    expect(pestanas[0]).toHaveTextContent("4 cambios");
    const cajas = screen.getByRole("list", { name: "Resumen del período" });
    expect(within(cajas).getAllByRole("listitem").map((li) => li.textContent)).toEqual(["4Cambios", "2Tickets tocados", "1Comentarios", "1Cambios de estado"]);
    expect(screen.getAllByRole("link", { name: "#9" })[0]).toHaveAttribute("href", "/tickets/9");
    expect(screen.getByText("comentó «Ya revisé»")).toBeInTheDocument();
    expect(screen.getByText("lo cerró automáticamente")).toBeInTheDocument();
    expect(document.querySelectorAll(".hist-dia")).toHaveLength(2);
    expect(screen.getByRole("button", { name: "Ver más cambios (faltan 1)" })).toBeVisible();
  });

  it("elegir persona, período y búsqueda filtran y quedan en la dirección", async () => {
    conSesion("Administrador");
    const { llamadas } = servidor();
    renderApp("/historial#persona=2&periodo=30");
    await waitFor(() => expect(screen.getByRole("tab", { name: /Tomás Técnico/ })).toHaveAttribute("aria-selected", "true"));
    expect(ultimo(llamadas, "/api/history/resumen").get("periodo")).toBe("30");
    expect(ultimo(llamadas, "/api/history/resumen").get("persona")).toBe("2");
    expect(screen.getByText("Técnico · Redes")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: /Sistema/ }));
    await waitFor(() => expect(ultimo(llamadas, "/api/history/resumen").get("persona")).toBe("sistema"));
    await userEvent.selectOptions(screen.getByLabelText("Período"), "hoy");
    await waitFor(() => expect(ultimo(llamadas, "/api/history/resumen").get("periodo")).toBe("hoy"));
    await userEvent.type(screen.getByLabelText("Buscar ticket"), "VPN{Enter}");
    await waitFor(() => expect(ultimo(llamadas, "/api/history?").get("buscar")).toBe("VPN"));
  });

  it("las flechas pasan a la persona vecina", async () => {
    conSesion("Técnico");
    servidor();
    renderApp("/historial");
    const todas = await screen.findByRole("tab", { name: /Todas las personas/ });
    todas.focus();
    await userEvent.keyboard("{ArrowDown}");
    await waitFor(() => expect(screen.getByRole("tab", { name: /Tomás Técnico/ })).toHaveFocus());
    await userEvent.keyboard("{End}");
    await waitFor(() => expect(screen.getByRole("tab", { name: /Sistema/ })).toHaveAttribute("aria-selected", "true"));
  });

  it("Ver más agrega la página siguiente", async () => {
    conSesion("Técnico");
    const { llamadas } = servidor();
    renderApp("/historial");
    await userEvent.click(await screen.findByRole("button", { name: "Ver más cambios (faltan 1)" }));
    await waitFor(() => expect(ultimo(llamadas, "/api/history?").get("offset")).toBe("3"));
    await waitFor(() => expect(screen.getAllByText("lo cerró automáticamente")).toHaveLength(2));
  });

  it("403 muestra el motivo", async () => {
    conSesion("Técnico");
    servidor({ estado: 403 });
    renderApp("/historial");
    expect(await screen.findByText("Su rol no tiene permiso para ver el historial.")).toBeInTheDocument();
  });

  it("frases, días y dirección", () => {
    expect(leerHash("#persona=Sistema&periodo=99")).toEqual({ persona: "sistema", periodo: "7" });
    expect(leerHash("#persona=<x>")).toEqual({ persona: "todas", periodo: "7" });
    expect(fraseCambio({ action: "assigned", new_value: "7" })).toBe("asignó el ticket a Usuario #7");
    expect(fraseCambio({ action: "updated", field: "priority", old_value: "Baja", new_value: "Alta" })).toBe("cambió la prioridad: Baja → Alta");
    const ahora = new Date("2026-11-19T18:00:00Z");
    expect(tituloDia("2026-11-19T15:00:00Z", ahora).texto).toBe("Hoy · jueves 19 de noviembre");
    expect(tituloDia("2026-11-18T15:00:00Z", ahora).texto).toBe("Ayer · miércoles 18 de noviembre");
    expect(tituloDia("2025-03-01T15:00:00Z", ahora).texto).toBe("Sábado 1 de marzo de 2025");
  });
});
