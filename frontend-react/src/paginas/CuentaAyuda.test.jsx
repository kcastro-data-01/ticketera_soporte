import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { conSesion, renderApp, respuesta, simularFetch } from "../pruebas/ayudas.jsx";

const servidor = () => simularFetch([["/api/tickets/summary", respuesta({ mios_abiertos: 0 })], ["/api/", respuesta([])]]);

describe("Mi cuenta (/cuenta)", () => {
  it("muestra los datos de la sesión y marca el menú de usuario", async () => {
    conSesion("Solicitante");
    servidor();
    renderApp("/cuenta");
    expect(await screen.findByRole("heading", { name: "Mi cuenta" })).toBeInTheDocument();
    expect(document.getElementById("cuenta-nombre")).toHaveTextContent("Sara Solicitante");
    expect(document.getElementById("cuenta-email")).toHaveTextContent("sara@empresa.com");
    expect(document.getElementById("cuenta-rol")).toHaveTextContent("Solicitante");
    expect(screen.getByRole("button", { name: "Menú de Sara Solicitante" })).toHaveClass("activo");
  });
});

describe("Ayuda (/ayuda)", () => {
  it("abre «Crear un ticket» y cambia de tema con clic y teclado", async () => {
    conSesion("Técnico");
    servidor();
    renderApp("/ayuda");
    const crear = await screen.findByRole("tab", { name: "Crear un ticket" });
    expect(crear).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("heading", { name: "¿Qué es la ticketera?" })).toBeVisible();
    await userEvent.click(screen.getByRole("tab", { name: "Adjuntos" }));
    expect(screen.getByRole("tab", { name: "Adjuntos" })).toHaveAttribute("aria-selected", "true");
    expect(document.getElementById("tema-adjuntos")).toBeVisible();
    expect(document.getElementById("tema-crear")).not.toBeVisible();
    screen.getByRole("tab", { name: "Adjuntos" }).focus();
    await userEvent.keyboard("{End}");
    await waitFor(() => expect(screen.getByRole("tab", { name: "Preguntas frecuentes" })).toHaveFocus());
    await userEvent.keyboard("{ArrowRight}");
    await waitFor(() => expect(screen.getByRole("tab", { name: "Crear un ticket" })).toHaveFocus());
  });

  it("/ayuda#correo abre ese tema; un tema inexistente abre el primero", async () => {
    conSesion("Técnico");
    servidor();
    renderApp("/ayuda#correo");
    expect(await screen.findByRole("tab", { name: "Tickets por correo" })).toHaveAttribute("aria-selected", "true");
    expect(document.getElementById("tema-correo")).toBeVisible();
  });

  it("tema inexistente", async () => {
    conSesion("Técnico");
    servidor();
    renderApp("/ayuda#no-existe");
    expect(await screen.findByRole("tab", { name: "Crear un ticket" })).toHaveAttribute("aria-selected", "true");
  });
});
