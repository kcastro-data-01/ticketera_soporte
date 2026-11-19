import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { conSesion, renderApp, respuesta, simularFetch } from "../pruebas/ayudas.jsx";

const LISTA = [
  { id: 1, name: "Ana Admin", email: "ana@empresa.com", role: "Administrador", area_id: 1, area_name: "Soporte IT", is_active: true },
  { id: 2, name: "Tomás Técnico", email: "tomas@empresa.com", role: "Técnico", area_id: null, is_active: true },
  { id: 3, name: "Sara Solicitante", email: "sara@empresa.com", role: "Solicitante", is_active: false },
];

function servidor({ loginLocal = false, crear = () => respuesta({ id: 9 }, { status: 201 }), editar = () => respuesta({}) } = {}) {
  return simularFetch([
    ["/api/auth/config", respuesta({ login_local: loginLocal })],
    [(u, o) => u === "/api/users" && o.method === "POST", crear],
    [(u, o) => /^\/api\/users\/\d+$/.test(u) && o.method === "PATCH", editar],
    ["/api/users", respuesta(LISTA)],
    ["/api/areas", respuesta([{ id: 1, name: "Soporte IT" }, { id: 2, name: "Redes" }])],
    ["/api/tickets/summary", respuesta({ mios_abiertos: 0 })],
    ["/api/tickets", respuesta([])],
  ]);
}

const cuerpo = (llamadas, metodo, re) => JSON.parse(llamadas.filter((l) => l.opciones.method === metodo && re.test(l.url)).at(-1).opciones.body);
const dialogo = () => document.getElementById("dialogo-usuario");

async function abrir(opciones) {
  conSesion("Administrador");
  const s = servidor(opciones);
  renderApp("/usuarios");
  await screen.findByText("tomas@empresa.com");
  return s;
}

describe("Usuarios (/usuarios)", () => {
  it("solo Administrador", async () => {
    conSesion("Técnico");
    servidor();
    renderApp("/usuarios");
    expect(await screen.findByRole("heading", { name: "Acceso restringido" })).toBeInTheDocument();
  });

  it("listado con rol, departamento, estado y sin «Desactivar» para uno mismo", async () => {
    const { llamadas } = await abrir();
    expect(llamadas.some((l) => l.url === "/api/users?todos=true")).toBe(true);
    const filaAna = screen.getByText("ana@empresa.com").closest("tr");
    expect(within(filaAna).getByText("Administrador")).toHaveClass("badge", "rol-administrador");
    expect(within(filaAna).getByText("Soporte IT")).toBeInTheDocument();
    expect(within(filaAna).queryByRole("button", { name: "Desactivar" })).toBeNull();
    const filaTomas = screen.getByText("tomas@empresa.com").closest("tr");
    expect(within(filaTomas).getByText("Sin departamento")).toBeInTheDocument();
    const filaSara = screen.getByText("sara@empresa.com").closest("tr");
    expect(within(filaSara).getByText("—")).toBeInTheDocument();
    expect(within(filaSara).getByText("Inactivo")).toHaveClass("badge-inactivo");
    expect(within(filaSara).getByRole("button", { name: "Reactivar" })).toBeInTheDocument();
  });

  it("agregar: valida, el departamento solo para IT y sin contraseña sin LOGIN_LOCAL", async () => {
    const { llamadas } = await abrir();
    await userEvent.click(screen.getByRole("button", { name: "Agregar usuario" }));
    expect(dialogo()).toHaveAttribute("open");
    const form = document.getElementById("form-usuario");
    expect(document.getElementById("nombre")).toHaveFocus();
    expect(document.querySelector("#form-usuario .solo-login-local")).not.toBeVisible();
    await userEvent.click(within(form).getByRole("button", { name: "Agregar usuario" }));
    expect(document.getElementById("error-nombre")).toHaveTextContent("El nombre no puede estar vacío.");
    expect(document.getElementById("nombre")).toHaveAttribute("aria-invalid", "true");
    await userEvent.type(document.getElementById("nombre"), "Nuevo Técnico");
    await userEvent.type(document.getElementById("email"), "mal");
    await userEvent.click(within(form).getByRole("button", { name: "Agregar usuario" }));
    expect(document.getElementById("error-email")).toHaveTextContent("El correo electrónico no tiene un formato válido.");
    await userEvent.clear(document.getElementById("email"));
    await userEvent.type(document.getElementById("email"), "nuevo@empresa.com");
    await userEvent.selectOptions(within(form).getByLabelText("Departamento"), "2");
    await userEvent.click(within(form).getByRole("button", { name: "Agregar usuario" }));
    expect(await screen.findByText("Usuario agregado correctamente.")).toBeInTheDocument();
    expect(cuerpo(llamadas, "POST", /\/api\/users$/)).toEqual({ name: "Nuevo Técnico", email: "nuevo@empresa.com", role: "Técnico", area_id: 2 });
    expect(dialogo()).not.toHaveAttribute("open");
  });

  it("el Solicitante no tiene departamento", async () => {
    await abrir();
    await userEvent.click(screen.getByRole("button", { name: "Agregar usuario" }));
    const form = document.getElementById("form-usuario");
    await userEvent.selectOptions(within(form).getByLabelText("Rol *"), "Solicitante");
    expect(form.querySelector(".campo-area")).not.toBeVisible();
    expect(form.querySelector("#area")).toBeDisabled();
  });

  it("409: el correo repetido va debajo de su campo", async () => {
    await abrir({ crear: () => respuesta({ detail: "Ese correo electrónico ya está registrado." }, { status: 409 }) });
    await userEvent.click(screen.getByRole("button", { name: "Agregar usuario" }));
    const form = document.getElementById("form-usuario");
    await userEvent.type(document.getElementById("nombre"), "Ana");
    await userEvent.type(document.getElementById("email"), "ana@empresa.com");
    await userEvent.click(within(form).getByRole("button", { name: "Agregar usuario" }));
    await waitFor(() => expect(document.getElementById("error-email")).toHaveTextContent("Ese correo electrónico ya está registrado."));
    expect(document.getElementById("email")).toHaveFocus();
    expect(dialogo()).toHaveAttribute("open");
  });

  it("422 sin campo conocido va en un aviso dentro de la ventana", async () => {
    await abrir({ crear: () => respuesta({ detail: [{ loc: ["body", "area_id"], msg: "no existe" }] }, { status: 422 }) });
    await userEvent.click(screen.getByRole("button", { name: "Agregar usuario" }));
    const form = document.getElementById("form-usuario");
    await userEvent.type(document.getElementById("nombre"), "Ana");
    await userEvent.type(document.getElementById("email"), "ana2@empresa.com");
    await userEvent.click(within(form).getByRole("button", { name: "Agregar usuario" }));
    await waitFor(() => expect(dialogo().querySelector("#avisos")).toHaveTextContent("area_id: no existe"));
    expect(dialogo().querySelector("#avisos .aviso")).toHaveAttribute("role", "alert");
  });

  it("con LOGIN_LOCAL pide contraseña al agregar y la nueva es opcional al editar", async () => {
    const { llamadas } = await abrir({ loginLocal: true });
    await userEvent.click(screen.getByRole("button", { name: "Agregar usuario" }));
    const form = document.getElementById("form-usuario");
    await waitFor(() => expect(form.querySelector(".solo-login-local")).toBeVisible());
    await userEvent.type(document.getElementById("nombre"), "Con Clave");
    await userEvent.type(document.getElementById("email"), "clave@empresa.com");
    await userEvent.type(document.getElementById("password"), "123");
    await userEvent.click(within(form).getByRole("button", { name: "Agregar usuario" }));
    expect(document.getElementById("error-password")).toHaveTextContent("La contraseña debe tener al menos 6 caracteres.");
    await userEvent.type(document.getElementById("password"), "456");
    await userEvent.click(within(form).getByRole("button", { name: "Agregar usuario" }));
    await screen.findByText("Usuario agregado correctamente.");
    expect(cuerpo(llamadas, "POST", /\/api\/users$/).password).toBe("123456");

    await userEvent.click(within(screen.getByText("tomas@empresa.com").closest("tr")).getByRole("button", { name: "Editar" }));
    const editar = document.getElementById("form-editar-usuario");
    expect(within(editar).getByLabelText("Nueva contraseña")).toHaveValue("");
    await userEvent.click(within(editar).getByRole("button", { name: "Guardar cambios" }));
    await screen.findByText("Usuario actualizado correctamente.");
    expect(cuerpo(llamadas, "PATCH", /\/api\/users\/2$/)).toEqual({ name: "Tomás Técnico", email: "tomas@empresa.com", role: "Técnico", area_id: null });
  });

  it("editar: cambiar rol y departamento", async () => {
    const { llamadas } = await abrir();
    await userEvent.click(within(screen.getByText("ana@empresa.com").closest("tr")).getByRole("button", { name: "Editar" }));
    expect(screen.getByRole("heading", { name: "Editar usuario" })).toBeInTheDocument();
    const editar = document.getElementById("form-editar-usuario");
    expect(editar).toBeVisible();
    expect(document.getElementById("form-usuario")).not.toBeVisible();
    expect(within(editar).getByLabelText("Departamento")).toHaveValue("1");
    await userEvent.selectOptions(within(editar).getByLabelText("Rol *"), "Técnico");
    await userEvent.selectOptions(within(editar).getByLabelText("Departamento"), "2");
    await userEvent.click(within(editar).getByRole("button", { name: "Guardar cambios" }));
    await screen.findByText("Usuario actualizado correctamente.");
    expect(cuerpo(llamadas, "PATCH", /\/api\/users\/1$/)).toEqual({ name: "Ana Admin", email: "ana@empresa.com", role: "Técnico", area_id: 2 });
  });

  it("desactivar pide confirmación; reactivar no", async () => {
    const { llamadas } = await abrir();
    await userEvent.click(within(screen.getByText("tomas@empresa.com").closest("tr")).getByRole("button", { name: "Desactivar" }));
    const confirmar = screen.getByRole("alertdialog", { name: "Desactivar usuario" });
    expect(confirmar).toHaveTextContent("¿Desactivar a Tomás Técnico? No podrá iniciar sesión ni recibir tickets.");
    await userEvent.click(within(confirmar).getByRole("button", { name: "Desactivar" }));
    expect(await screen.findByText("Tomás Técnico fue desactivado.")).toBeInTheDocument();
    expect(cuerpo(llamadas, "PATCH", /\/api\/users\/2$/)).toEqual({ is_active: false });
    await userEvent.click(within(screen.getByText("sara@empresa.com").closest("tr")).getByRole("button", { name: "Reactivar" }));
    expect(await screen.findByText("Sara Solicitante fue reactivado.")).toBeInTheDocument();
    expect(cuerpo(llamadas, "PATCH", /\/api\/users\/3$/)).toEqual({ is_active: true });
  });
});
