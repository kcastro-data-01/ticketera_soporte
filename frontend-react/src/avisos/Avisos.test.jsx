import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { AvisosProvider, avisoPendiente, useAvisos } from "./Avisos.jsx";

function Botones() {
  const { avisar } = useAvisos();
  return (
    <>
      <button type="button" onClick={() => avisar("Guardado.")}>exito</button>
      <button type="button" onClick={() => avisar("Falló.", "error")}>error</button>
      <button type="button" onClick={() => ["1", "2", "3", "4", "5"].forEach((n) => avisar(`Aviso ${n}`, "error"))}>cinco</button>
    </>
  );
}

const montar = () => render(<MemoryRouter><AvisosProvider><Botones /></AvisosProvider></MemoryRouter>);

describe("avisos flotantes", () => {
  it("éxito se va solo a los 4 s; error queda y se cierra con ✕", async () => {
    vi.useFakeTimers();
    montar();
    act(() => screen.getByText("exito").click());
    act(() => screen.getByText("error").click());
    const zona = document.getElementById("avisos");
    expect(zona).toHaveAttribute("aria-live", "polite");
    expect(screen.getByText("Guardado.").closest(".aviso")).toHaveClass("aviso", "exito");
    expect(screen.getByRole("alert")).toHaveTextContent("Falló.");
    act(() => vi.advanceTimersByTime(4300));
    expect(screen.queryByText("Guardado.")).toBeNull();
    expect(screen.getByText("Falló.")).toBeInTheDocument();
    act(() => screen.getByRole("button", { name: "Cerrar aviso" }).click());
    act(() => vi.advanceTimersByTime(300));
    expect(screen.queryByText("Falló.")).toBeNull();
  });

  it("máximo 4 a la vista y el repetido no se duplica", async () => {
    vi.useFakeTimers();
    montar();
    act(() => screen.getByText("cinco").click());
    act(() => vi.advanceTimersByTime(300));
    expect(screen.getAllByRole("alert").map((a) => a.textContent)).toEqual(["Aviso 2✕", "Aviso 3✕", "Aviso 4✕", "Aviso 5✕"]);
    act(() => screen.getByText("error").click());
    act(() => screen.getByText("error").click());
    act(() => vi.advanceTimersByTime(300));
    expect(screen.getAllByText("Falló.")).toHaveLength(1);
  });

  it("Escape cierra el aviso enfocado", async () => {
    montar();
    await userEvent.click(screen.getByText("error"));
    screen.getByRole("button", { name: "Cerrar aviso" }).focus();
    await userEvent.keyboard("{Escape}");
    await new Promise((r) => setTimeout(r, 300));
    expect(screen.queryByText("Falló.")).toBeNull();
  });

  it("el aviso pendiente se muestra al llegar a la pantalla", () => {
    avisoPendiente("Ticket #3 guardado correctamente.");
    montar();
    expect(screen.getByText("Ticket #3 guardado correctamente.")).toBeInTheDocument();
    expect(sessionStorage.getItem("aviso_pendiente")).toBeNull();
  });
});
