import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { conSesion, renderApp, respuesta, simularFetch } from "../pruebas/ayudas.jsx";

const AREAS = [{ id: 1, name: "Soporte IT" }, { id: 2, name: "Redes e Infraestructura" }];

function servidor({ crear = 201, adjunto = () => respuesta({ id: 1 }, { status: 201 }), areas = AREAS } = {}) {
  return simularFetch([
    [(u, o) => u === "/api/tickets" && o.method === "POST", () => (crear === 201
      ? respuesta({ id: 42 }, { status: 201 })
      : respuesta({ detail: [{ loc: ["body", "title"], msg: "muy corto" }] }, { status: crear }))],
    [(u, o) => u.startsWith("/api/tickets/42/adjuntos?nombre=") && o.method === "POST", adjunto],
    ["/api/areas", respuesta(areas)],
    ["/api/tickets/summary", respuesta({ mios_abiertos: 0 })],
    ["/api/tickets", respuesta([], { headers: { "X-Total-Count": "0" } })],
    ["/api/users", respuesta([])],
  ]);
}

const cuerpoCrear = (llamadas) => JSON.parse(llamadas.find((l) => l.url === "/api/tickets" && l.opciones.method === "POST").opciones.body);

async function abrir(rol = "Solicitante", opciones) {
  conSesion(rol);
  const s = servidor(opciones);
  renderApp("/crear");
  await screen.findByRole("heading", { name: "Nuevo ticket" });
  return s;
}

async function llenar() {
  await userEvent.type(screen.getByLabelText("Título *"), "  La impresora no imprime ");
  await userEvent.type(screen.getByLabelText("Descripción *"), "Desde hoy muestra un error.");
  await waitFor(() => expect(screen.getByRole("option", { name: "Redes e Infraestructura" })).toBeInTheDocument());
  await userEvent.selectOptions(screen.getByLabelText("Departamento *"), "2");
}

describe("Nuevo ticket (/crear)", () => {
  it("el menú lo marca activo y ofrece los departamentos", async () => {
    await abrir();
    expect(screen.getByRole("link", { name: "Nuevo ticket" , current: "page" })).toHaveClass("activo");
    await waitFor(() => expect(within(screen.getByLabelText("Departamento *")).getAllByRole("option").map((o) => o.textContent))
      .toEqual(["Elija un departamento", "Soporte IT", "Redes e Infraestructura"]));
    expect(screen.getByRole("radio", { name: "Media" })).toBeChecked();
  });

  it("valida en el navegador: título, descripción y departamento", async () => {
    const { llamadas } = await abrir();
    await waitFor(() => expect(screen.getByRole("option", { name: "Soporte IT" })).toBeInTheDocument());
    await userEvent.click(screen.getByRole("button", { name: "Crear ticket" }));
    expect(await screen.findByText("El título y la descripción son obligatorios.")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Título *"), "Algo");
    await userEvent.click(screen.getByRole("button", { name: "Crear ticket" }));
    expect(await screen.findByText("La descripción es obligatoria.")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Descripción *"), "Detalle");
    await userEvent.click(screen.getByRole("button", { name: "Crear ticket" }));
    expect(await screen.findByText("Elija el departamento del ticket.")).toBeInTheDocument();
    expect(llamadas.some((l) => l.opciones.method === "POST")).toBe(false);
  });

  it("crea el ticket y vuelve al listado con el aviso", async () => {
    const { llamadas } = await abrir();
    await llenar();
    await userEvent.selectOptions(screen.getByLabelText("Categoría"), "Red");
    await userEvent.click(screen.getByRole("radio", { name: "Crítica" }));
    await userEvent.click(screen.getByRole("button", { name: "Crear ticket" }));
    expect(await screen.findByText("Ticket #42 guardado correctamente.", {}, { timeout: 3000 })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Mis solicitudes" })).toBeInTheDocument();
    expect(cuerpoCrear(llamadas)).toEqual({
      title: "La impresora no imprime", description: "Desde hoy muestra un error.", category: "Red", priority: "Crítica", area_id: 2,
    });
  });

  it("422 del servidor en un aviso legible", async () => {
    await abrir("Técnico", { crear: 422 });
    await llenar();
    await userEvent.click(screen.getByRole("button", { name: "Crear ticket" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Revise los datos enviados. title: muy corto");
    expect(screen.getByRole("button", { name: "Crear ticket" })).toBeEnabled();
  });

  it("adjuntos: lista con tamaño, ✕ para quitar y rechaza tipos no permitidos", async () => {
    await abrir();
    const input = screen.getByTestId("crear-adj-archivos");
    await userEvent.upload(input, [
      new File(["a".repeat(2048)], "captura.txt", { type: "text/plain" }),
      new File(["b"], "otro.pdf", { type: "application/pdf" }),
      new File(["c"], "script.js", { type: "text/javascript" }),
    ], { applyAccept: false });
    const lista = await screen.findByRole("list", { name: "Archivos elegidos" });
    expect(within(lista).getByText("captura.txt")).toBeInTheDocument();
    expect(within(lista).getByText("2 KB")).toBeInTheDocument();
    expect(screen.getByText("«script.js»: tipo no permitido. Se aceptan jpg, png, pdf, docx, xlsx o txt.")).toBeInTheDocument();
    await userEvent.click(within(lista).getByRole("button", { name: "Quitar captura.txt" }));
    expect(within(lista).queryByText("captura.txt")).toBeNull();
    expect(within(lista).getByRole("button", { name: "Quitar otro.pdf" })).toHaveFocus();
  });

  it("con adjuntos los sube después de crear y lo dice en el aviso", async () => {
    const { llamadas } = await abrir();
    await llenar();
    await userEvent.upload(screen.getByTestId("crear-adj-archivos"), [
      new File(["x"], "a.txt", { type: "text/plain" }), new File(["y"], "b.txt", { type: "text/plain" }),
    ], { applyAccept: false });
    await userEvent.click(screen.getByRole("button", { name: "Crear ticket" }));
    expect(await screen.findByText("Ticket #42 guardado correctamente con 2 adjuntos.", {}, { timeout: 3000 })).toBeInTheDocument();
    expect(llamadas.filter((l) => l.url.includes("/adjuntos?nombre=")).map((l) => l.url))
      .toEqual(["/api/tickets/42/adjuntos?nombre=a.txt", "/api/tickets/42/adjuntos?nombre=b.txt"]);
  });

  it("si un adjunto falla: el ticket queda creado y ofrece «Ir al ticket y reintentar»", async () => {
    await abrir("Solicitante", {
      adjunto: (u) => (u.endsWith("b.txt")
        ? respuesta({ detail: "«b.txt»: el contenido no corresponde al tipo." }, { status: 422 })
        : respuesta({ id: 1 }, { status: 201 })),
    });
    await llenar();
    await userEvent.upload(screen.getByTestId("crear-adj-archivos"), [
      new File(["x"], "a.txt", { type: "text/plain" }), new File(["y"], "b.txt", { type: "text/plain" }),
    ], { applyAccept: false });
    await userEvent.click(screen.getByRole("button", { name: "Crear ticket" }));
    const titulo = await screen.findByRole("heading", { name: "Ticket #42 creado" });
    await waitFor(() => expect(titulo).toHaveFocus());
    expect(screen.getByText("No se pudo subir 1 adjunto; el otro quedó guardado. Puede reintentarlos desde el detalle del ticket.")).toBeInTheDocument();
    expect(within(document.getElementById("crear-resultado-fallas")).getByText("b.txt").closest("li")).toHaveTextContent("b.txt: El contenido no corresponde al tipo.");
    expect(screen.getByRole("link", { name: "Ir al ticket y reintentar" })).toHaveAttribute("href", "/tickets/42");
    expect(screen.getByRole("alert")).toHaveTextContent("Ticket #42 creado. No se pudo subir 1 adjunto.");
    expect(document.getElementById("form-crear")).not.toBeVisible();
  });

  it("sin departamentos el ticket se crea igual (se elige por la categoría)", async () => {
    const { llamadas } = await abrir("Solicitante", { areas: [] });
    await waitFor(() => expect(screen.getByLabelText("Departamento *")).toHaveDisplayValue("No se pudieron cargar: se elige por la categoría"));
    await userEvent.type(screen.getByLabelText("Título *"), "Algo");
    await userEvent.type(screen.getByLabelText("Descripción *"), "Detalle");
    await userEvent.click(screen.getByRole("button", { name: "Crear ticket" }));
    await waitFor(() => expect(cuerpoCrear(llamadas)).not.toHaveProperty("area_id"));
  });
});
