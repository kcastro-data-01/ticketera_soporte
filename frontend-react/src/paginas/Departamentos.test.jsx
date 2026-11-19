import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { conSesion, renderApp, respuesta, simularFetch } from "../pruebas/ayudas.jsx";
import { slugDepartamento } from "./Departamentos.jsx";

const RESUMEN = {
  departamentos: [
    { area_id: 1, nombre: "Soporte IT", atiende: "computadoras e impresoras", total: 5, abiertos: 3,
      por_estado: { Nuevo: 2, "En proceso": 1, Resuelto: 1, Cerrado: 1 },
      tecnicos: [{ id: 2, name: "Tomás Técnico", abiertos: 3, resueltos_mes: 4 }],
      tickets_abiertos: [{ id: 11, title: "Impresora <b>", state: "Nuevo", priority: "Alta", assigned_to_name: null }] },
    { area_id: 2, nombre: "Redes e Infraestructura", atiende: "internet", total: 12, abiertos: 11,
      por_estado: { Nuevo: 11, "En proceso": 0, Resuelto: 1, Cerrado: 0 }, tecnicos: [],
      tickets_abiertos: Array.from({ length: 10 }, (_, i) => ({ id: 20 + i, title: `T${i}`, state: "Nuevo", priority: "Baja", assigned_to_name: "Ana Admin" })) },
    { area_id: null, nombre: "Sin departamento", total: 0, abiertos: 0, por_estado: {}, tecnicos: [], tickets_abiertos: [] },
  ],
  atencion: { criticos: 2, altos: 0, sin_asignar: 1, nuevos_viejos: 4, dias_nuevo: 2 },
};

function servidor() {
  return simularFetch([
    ["/api/departamentos/resumen", respuesta(RESUMEN)],
    ["/api/tickets/summary", respuesta({ mios_abiertos: 0 })],
    ["/api/tickets", respuesta([])],
    ["/api/users", respuesta([])],
    ["/api/areas", respuesta([])],
  ]);
}

describe("Departamentos (/departamentos)", () => {
  it("solo Administrador", async () => {
    conSesion("Técnico");
    servidor();
    renderApp("/departamentos");
    expect(await screen.findByRole("heading", { name: "Acceso restringido" })).toBeInTheDocument();
  });

  it("lista, detalle con cifras, técnicos y abiertos; «Sin departamento» sin tickets no aparece", async () => {
    conSesion("Administrador");
    servidor();
    renderApp("/departamentos");
    const lista = await screen.findByRole("tablist", { name: "Departamentos" });
    expect(within(lista).getAllByRole("tab")).toHaveLength(2);
    expect(within(lista).getAllByRole("tab")[0]).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("heading", { name: "Soporte IT" })).toBeInTheDocument();
    expect(screen.getByText("Atiende computadoras e impresoras")).toBeInTheDocument();
    const cajas = screen.getByRole("list", { name: "Tickets por estado" });
    expect(within(cajas).getAllByRole("listitem").map((li) => li.textContent)).toEqual(["3Abiertos", "2Nuevo", "1En proceso", "1Resuelto", "1Cerrado"]);
    expect(within(cajas).getAllByRole("listitem")[1].style.borderTopColor).toBe("rgb(29, 78, 216)");
    expect(screen.getByText("Tomás Técnico")).toHaveAttribute("data-iniciales", "TT");
    expect(screen.getByText("Impresora <b>")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "#11" })).toHaveAttribute("href", "/tickets/11");
    expect(screen.getByRole("link", { name: "Ver todos los tickets de Soporte IT" })).toHaveAttribute("href", "/?area=1");
    const barra = within(lista).getAllByRole("tab")[0].querySelectorAll(".depto-barra-parte");
    expect([...barra].map((p) => p.style.width)).toEqual(["40%", "20%", "20%", "20%"]);
  });

  it("«Requieren atención» lleva a la lista de React filtrada", async () => {
    conSesion("Administrador");
    servidor();
    renderApp("/departamentos");
    const criticos = await screen.findByRole("link", { name: "Críticos abiertos: 2. Abrir la lista de tickets" });
    expect(criticos).toHaveAttribute("href", "/?prioridad=Cr%C3%ADtica&estado=abiertos");
    expect(criticos).toHaveClass("con-valor");
    expect(screen.getByRole("link", { name: "Altos abiertos: 0. Abrir la lista de tickets" })).toHaveClass("en-cero");
    expect(screen.getByRole("link", { name: "Sin asignar: 1. Abrir la lista de tickets" })).toHaveAttribute("href", "/?asignado=sin&estado=abiertos");
    expect(screen.getByRole("link", { name: "Más de 2 días en Nuevo: 4. Abrir la lista de tickets" })).toHaveAttribute("href", "/?estado=Nuevo&antiguedad=2");
    await userEvent.click(criticos);
    expect(await screen.findByRole("heading", { name: "Tickets" })).toBeInTheDocument();
  });

  it("elegir otro (clic, flechas o #slug) y con más de 10 abiertos «Ver todos» va a los abiertos", async () => {
    conSesion("Administrador");
    servidor();
    renderApp(`/departamentos#${slugDepartamento("Redes e Infraestructura")}`);
    await waitFor(() => expect(screen.getByRole("heading", { level: 2, name: "Redes e Infraestructura" })).toBeInTheDocument());
    expect(screen.getByRole("link", { name: /Ver todos los tickets de Redes/ })).toHaveAttribute("href", "/?area=2&estado=abiertos");
    expect(screen.getByText("Se muestran 10 de 11 abiertos. «Ver todos sus tickets» muestra el resto.")).toBeInTheDocument();
    expect(screen.getByText("Este departamento no tiene técnicos activos.")).toBeVisible();
    const tab = screen.getByRole("tab", { name: /Redes/ });
    tab.focus();
    await userEvent.keyboard("{ArrowDown}");
    await waitFor(() => expect(screen.getByRole("tab", { name: /Soporte IT/ })).toHaveFocus());
    expect(screen.getByRole("heading", { level: 2, name: "Soporte IT" })).toBeInTheDocument();
  });

  it("slug de la dirección", () => {
    expect(slugDepartamento("Redes e Infraestructura")).toBe("redes-e-infraestructura");
    expect(slugDepartamento("Programación")).toBe("programacion");
  });
});
