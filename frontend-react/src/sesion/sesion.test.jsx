import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import AvisoSesion from "../componentes/AvisoSesion.jsx";
import { HORA, MIN, respuesta, token } from "../pruebas/ayudas.jsx";
import { navegador } from "./almacen.js";
import { SESION_TIEMPOS, formatoCuenta, iniciarSesion } from "./control.js";
import { useSesionDeslizante } from "./useSesionDeslizante.js";

const INICIO = Date.parse("2026-11-19T14:00:00Z");
const seg = (ms) => Math.floor(ms / 1000);

function entrar({ iat = seg(Date.now()), max } = {}) {
  const t = token({ iat, exp: iat + 3600, ini: iat, max: max ?? iat + 10 * 3600 });
  localStorage.setItem("access_token", t);
  localStorage.setItem("user", JSON.stringify({ id: 2, role: "Técnico" }));
  return t;
}

const mover = () => document.dispatchEvent(new MouseEvent("mousemove"));

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["setInterval", "clearInterval", "setTimeout", "clearTimeout", "Date"] });
  vi.setSystemTime(INICIO);
});

describe("sesión deslizante (control.js)", () => {
  it("usa los mismos tiempos que la ticketera actual", () => {
    expect(SESION_TIEMPOS).toEqual({ INACTIVIDAD_MS: 30 * MIN, AVISO_MS: 2 * MIN, RENOVAR_CADA_MS: 5 * MIN });
    expect(formatoCuenta(2 * MIN)).toBe("2:00");
    expect(formatoCuenta(65 * 1000)).toBe("1:05");
  });

  it("con actividad renueva en /api/auth/renovar pasados 5 minutos", async () => {
    entrar();
    const nuevo = token({ iat: seg(INICIO + 6 * MIN) });
    const fetchFalso = vi.fn(async () => respuesta({ access_token: nuevo }));
    vi.stubGlobal("fetch", fetchFalso);
    const control = iniciarSesion({ tiempos: SESION_TIEMPOS });
    await vi.advanceTimersByTimeAsync(4 * MIN);
    mover();
    await vi.advanceTimersByTimeAsync(1000);
    expect(fetchFalso).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(MIN + 1000);
    mover();
    await vi.advanceTimersByTimeAsync(1000);
    expect(fetchFalso).toHaveBeenCalledWith("/api/auth/renovar", expect.objectContaining({ method: "POST" }));
    expect(localStorage.getItem("access_token")).toBe(nuevo);
    control.detener();
  });

  it("abrir la página cuenta como actividad (una renovación) y después, sin actividad, no renueva más; a los 30 min avisa con 2:00 y a los 32 min cierra", async () => {
    entrar();
    const fetchFalso = vi.fn(async () => respuesta({}));
    vi.stubGlobal("fetch", fetchFalso);
    const cambios = [];
    iniciarSesion({ tiempos: SESION_TIEMPOS, alCambiar: (e) => cambios.push(e) });
    await vi.advanceTimersByTimeAsync(30 * MIN);
    expect(fetchFalso).toHaveBeenCalledTimes(1);
    expect(cambios.at(-1)).toEqual({ abierta: true, restanteMs: 2 * MIN });
    /* Con el aviso abierto mover el mouse no cuenta. */
    mover();
    await vi.advanceTimersByTimeAsync(2 * MIN);
    expect(localStorage.getItem("access_token")).toBeNull();
    expect(localStorage.getItem("sesion_cierre")).toBe("inactividad");
    expect(navegador.ir).toHaveBeenCalledWith("/login");
  });

  it("«Seguir conectado» cierra el aviso y renueva", async () => {
    entrar();
    const fetchFalso = vi.fn(async () => respuesta({ access_token: token() }));
    vi.stubGlobal("fetch", fetchFalso);
    const cambios = [];
    const control = iniciarSesion({ tiempos: SESION_TIEMPOS, alCambiar: (e) => cambios.push(e) });
    await vi.advanceTimersByTimeAsync(31 * MIN);
    expect(control.abierta()).toBe(true);
    const antes = fetchFalso.mock.calls.length;
    await control.seguir();
    expect(control.abierta()).toBe(false);
    expect(fetchFalso).toHaveBeenCalledTimes(antes + 1);
    await vi.advanceTimersByTimeAsync(5 * MIN);
    expect(localStorage.getItem("access_token")).toBeTruthy();
    control.detener();
  });

  it("pasado el máximo de horas (claim max) cierra con «maxima»", async () => {
    const ahora = seg(INICIO);
    entrar({ iat: ahora, max: ahora + 60 });
    vi.stubGlobal("fetch", vi.fn());
    iniciarSesion({ tiempos: SESION_TIEMPOS });
    mover();
    await vi.advanceTimersByTimeAsync(61 * 1000);
    expect(localStorage.getItem("sesion_cierre")).toBe("maxima");
    expect(localStorage.getItem("sesion_inicio")).toBeNull();
  });

  it("401 al renovar: sesión vencida, vuelve al login con la ruta actual", async () => {
    window.history.replaceState(null, "", "/?estado=Nuevo");
    entrar();
    vi.stubGlobal("fetch", vi.fn(async () => respuesta({ detail: "No autenticado" }, { status: 401 })));
    iniciarSesion({ tiempos: SESION_TIEMPOS });
    await vi.advanceTimersByTimeAsync(5 * MIN);
    mover();
    await vi.advanceTimersByTimeAsync(2000);
    expect(localStorage.getItem("sesion_cierre")).toBe("vencida");
    expect(navegador.ir).toHaveBeenCalledWith("/login?volver=%2F%3Festado%3DNuevo");
    window.history.replaceState(null, "", "/");
  });

  it("si otra pestaña cierra la sesión, esta va al login", async () => {
    entrar();
    vi.stubGlobal("fetch", vi.fn());
    iniciarSesion({ tiempos: SESION_TIEMPOS });
    localStorage.removeItem("access_token");
    window.dispatchEvent(new StorageEvent("storage", { key: "access_token" }));
    expect(navegador.ir).toHaveBeenCalledWith("/login");
  });

  it("otra pestaña con actividad mantiene viva esta", async () => {
    entrar();
    vi.stubGlobal("fetch", vi.fn(async () => respuesta({ access_token: token() })));
    const control = iniciarSesion({ tiempos: SESION_TIEMPOS });
    await vi.advanceTimersByTimeAsync(29 * MIN);
    localStorage.setItem("sesion_actividad", String(Date.now()));
    await vi.advanceTimersByTimeAsync(2 * MIN);
    expect(control.abierta()).toBe(false);
    control.detener();
  });
});

function Prueba() {
  const s = useSesionDeslizante(true, { tiempos: SESION_TIEMPOS });
  return <AvisoSesion abierta={s.abierta} restanteMs={s.restanteMs} onSeguir={s.seguir} onSalir={s.salir} />;
}

describe("aviso «¿Sigue ahí?»", () => {
  it("aparece a los 30 min con la cuenta regresiva y «Cerrar sesión» cierra a mano", async () => {
    entrar();
    vi.stubGlobal("fetch", vi.fn());
    render(<Prueba />);
    expect(screen.queryByRole("alertdialog")).toBeNull();
    await act(() => vi.advanceTimersByTimeAsync(30 * MIN));
    const dialogo = screen.getByRole("alertdialog", { name: "¿Sigue ahí?" });
    expect(dialogo).toHaveTextContent("La sesión se cerrará en 2:00");
    await act(() => vi.advanceTimersByTimeAsync(65 * 1000));
    expect(dialogo).toHaveTextContent("0:55");
    expect(screen.getByRole("button", { name: "Seguir conectado" })).toHaveFocus();
    vi.useRealTimers();
    await userEvent.click(screen.getByRole("button", { name: "Cerrar sesión" }));
    expect(localStorage.getItem("sesion_cierre")).toBe("manual");
    expect(screen.queryByRole("alertdialog")).toBeNull();
  });

  it("«Seguir conectado» lo cierra", async () => {
    entrar();
    vi.stubGlobal("fetch", vi.fn(async () => respuesta({ access_token: token() })));
    render(<Prueba />);
    await act(() => vi.advanceTimersByTimeAsync(30 * MIN + HORA * 0));
    vi.useRealTimers();
    await userEvent.click(screen.getByRole("button", { name: "Seguir conectado" }));
    expect(screen.queryByRole("alertdialog")).toBeNull();
    expect(fetch).toHaveBeenCalledWith("/api/auth/renovar", expect.anything());
  });
});
