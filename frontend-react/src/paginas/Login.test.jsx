import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderApp, respuesta, simularFetch, token, USUARIOS } from "../pruebas/ayudas.jsx";

const msal = vi.hoisted(() => ({
  handleRedirectPromise: vi.fn(),
  loginRedirect: vi.fn(),
  getAllAccounts: vi.fn(),
  acquireTokenSilent: vi.fn(),
  ssoSilent: vi.fn(),
  config: null,
}));

vi.mock("@azure/msal-browser", () => ({
  PublicClientApplication: {
    createPublicClientApplication: vi.fn(async (config) => {
      msal.config = config;
      return msal;
    }),
  },
}));

const CONFIG = { tenant: "t-123", client_id: "c-456", login_local: false, sesion_maxima_horas: 10 };

function servidor({ config = CONFIG, login, microsoft } = {}) {
  return simularFetch([
    ["/api/auth/config", respuesta(config)],
    ["/api/auth/login", login || respuesta({ access_token: token({ role: "Técnico" }) })],
    ["/api/auth/microsoft", microsoft || respuesta({ access_token: token({ role: "Técnico" }) })],
    ["/api/auth/me", respuesta(USUARIOS.Técnico)],
    ["/api/tickets/summary", respuesta({ mios_abiertos: 0 })],
    ["/api/tickets", respuesta([], { headers: { "X-Total-Count": "0" } })],
    ["/api/users", respuesta([])],
    ["/api/areas", respuesta([])],
  ]);
}

beforeEach(() => {
  msal.handleRedirectPromise.mockReset().mockResolvedValue(null);
  msal.loginRedirect.mockReset().mockResolvedValue(undefined);
  msal.getAllAccounts.mockReset().mockReturnValue([]);
  msal.acquireTokenSilent.mockReset();
  msal.ssoSilent.mockReset().mockRejectedValue(new Error("sin sesión"));
});

describe("Login", () => {
  it("configura MSAL con el tenant, el client id y /react/login, sin formulario de contraseña", async () => {
    servidor();
    renderApp("/login");
    await waitFor(() => expect(msal.config).not.toBeNull());
    expect(msal.config.auth.clientId).toBe("c-456");
    expect(msal.config.auth.authority).toBe("https://login.microsoftonline.com/t-123");
    expect(msal.config.auth.redirectUri).toBe(`${window.location.origin}/react/login`);
    expect(msal.config.cache.cacheLocation).toBe("localStorage");
    expect(document.getElementById("form-login")).not.toHaveClass("activo");
    expect(document.body).toHaveClass("pagina-login");
  });

  it("el botón de Microsoft abre el login con select_account y recuerda el destino", async () => {
    servidor();
    renderApp("/login?volver=%2Ftickets%2F5");
    const boton = await screen.findByRole("button", { name: /Iniciar sesión con Microsoft/ });
    await waitFor(() => expect(boton).toBeEnabled());
    await userEvent.click(boton);
    expect(msal.loginRedirect).toHaveBeenCalledWith({ scopes: ["openid", "profile", "email", "User.Read"], prompt: "select_account" });
    expect(sessionStorage.getItem("login_volver")).toBe("/tickets/5");
  });

  it("al volver de Microsoft valida el id_token en el servidor y entra", async () => {
    msal.handleRedirectPromise.mockResolvedValue({ idToken: "id-token-ms" });
    const { llamadas } = servidor();
    renderApp("/login");
    expect(await screen.findByText("Inicio de sesión correcto. Redirigiendo…")).toBeInTheDocument();
    const pedido = llamadas.find((l) => l.url === "/api/auth/microsoft");
    expect(JSON.parse(pedido.opciones.body)).toEqual({ id_token: "id-token-ms" });
    expect(localStorage.getItem("access_token")).toBeTruthy();
    expect(JSON.parse(localStorage.getItem("user")).name).toBe("Tomás Técnico");
    expect(await screen.findByRole("heading", { name: "Tickets" }, { timeout: 2000 })).toBeInTheDocument();
  });

  it("cuenta desactivada en Microsoft (403)", async () => {
    msal.handleRedirectPromise.mockResolvedValue({ idToken: "x" });
    servidor({ microsoft: respuesta({ detail: "x" }, { status: 403 }) });
    renderApp("/login");
    expect(await screen.findByRole("alert")).toHaveTextContent("Su cuenta está desactivada. Comuníquese con el administrador.");
  });

  it("sin tenant el botón queda deshabilitado", async () => {
    servidor({ config: { ...CONFIG, tenant: "" } });
    renderApp("/login");
    expect(await screen.findByRole("alert")).toHaveTextContent("El inicio de sesión con Microsoft no está disponible en este momento.");
    expect(screen.getByRole("button", { name: /Microsoft/ })).toBeDisabled();
  });

  describe("con LOGIN_LOCAL", () => {
    const local = { ...CONFIG, login_local: true };

    it("muestra el formulario y entra con contraseña, volviendo a la ruta pedida", async () => {
      const { llamadas } = servidor({ config: local });
      renderApp("/login?volver=%2F%3Festado%3DNuevo");
      await waitFor(() => expect(document.getElementById("form-login")).toHaveClass("activo"));
      await userEvent.type(screen.getByLabelText("Correo"), "tomas@empresa.com");
      await userEvent.type(screen.getByLabelText("Contraseña"), "secreta");
      await userEvent.click(screen.getByRole("button", { name: "Entrar con contraseña (desarrollo)" }));
      expect(await screen.findByText("Inicio de sesión correcto. Redirigiendo…")).toBeInTheDocument();
      const pedido = llamadas.find((l) => l.url === "/api/auth/login");
      expect(JSON.parse(pedido.opciones.body)).toEqual({ email: "tomas@empresa.com", password: "secreta" });
      expect(localStorage.getItem("sesion_cierre")).toBeNull();
      expect(await screen.findByRole("heading", { name: "Tickets" }, { timeout: 2000 })).toBeInTheDocument();
    });

    it("credenciales inválidas (401)", async () => {
      servidor({ config: local, login: respuesta({ detail: "x" }, { status: 401 }) });
      renderApp("/login");
      await waitFor(() => expect(document.getElementById("form-login")).toHaveClass("activo"));
      await userEvent.type(screen.getByLabelText("Correo"), "a@b.com");
      await userEvent.type(screen.getByLabelText("Contraseña"), "mala");
      await userEvent.click(screen.getByRole("button", { name: "Entrar con contraseña (desarrollo)" }));
      expect(await screen.findByRole("alert")).toHaveTextContent("Credenciales inválidas. Verifique su correo y contraseña.");
      expect(localStorage.getItem("access_token")).toBeNull();
    });

    it("el ojo muestra y oculta la contraseña", async () => {
      servidor({ config: local });
      renderApp("/login");
      const ojo = await screen.findByRole("button", { name: "Mostrar contraseña" });
      await userEvent.click(ojo);
      expect(screen.getByLabelText("Contraseña")).toHaveAttribute("type", "text");
      expect(ojo).toHaveAttribute("aria-pressed", "true");
    });
  });

  describe("renovación silenciosa", () => {
    it("con la sesión vencida vuelve a entrar con la caché de MSAL y la página silenciosa", async () => {
      localStorage.setItem("sesion_cierre", "vencida");
      localStorage.setItem("sesion_inicio", String(Date.now() - 60 * 60 * 1000));
      msal.getAllAccounts.mockReturnValue([{ username: "tomas@empresa.com" }]);
      msal.acquireTokenSilent.mockResolvedValue({ idToken: "silencioso" });
      const { llamadas } = servidor();
      renderApp("/login?volver=%2Ftickets%2F9");
      await waitFor(() => expect(localStorage.getItem("access_token")).toBeTruthy());
      const pedido = msal.acquireTokenSilent.mock.calls[0][0];
      expect(pedido.redirectUri).toBe(`${window.location.origin}/msal/silencioso.html`);
      expect(pedido.forceRefresh).toBe(true);
      const cuerpo = JSON.parse(llamadas.find((l) => l.url === "/api/auth/microsoft").opciones.body);
      expect(cuerpo.id_token).toBe("silencioso");
      expect(Number.isInteger(cuerpo.inicio)).toBe(true);
    });

    it("cerrada a mano no intenta entrar en silencio y explica el motivo", async () => {
      localStorage.setItem("sesion_cierre", "inactividad");
      servidor();
      renderApp("/login");
      expect(await screen.findByRole("status")).toHaveTextContent("Su sesión se cerró por inactividad.");
      expect(msal.ssoSilent).not.toHaveBeenCalled();
      expect(msal.acquireTokenSilent).not.toHaveBeenCalled();
    });

    it("pasado el máximo de horas no entra en silencio", async () => {
      localStorage.setItem("sesion_cierre", "vencida");
      localStorage.setItem("sesion_inicio", String(Date.now() - 11 * 60 * 60 * 1000));
      servidor();
      renderApp("/login");
      expect(await screen.findByRole("status")).toHaveTextContent("Su sesión llegó al máximo de horas permitido.");
      expect(msal.ssoSilent).not.toHaveBeenCalled();
    });
  });
});
