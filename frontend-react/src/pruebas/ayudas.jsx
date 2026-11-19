import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";
import { FUTURO, Proveedores, Rutas } from "../App.jsx";

export const MIN = 60 * 1000;
export const HORA = 60 * MIN;

/* Un token como los del servidor (la firma no importa en el navegador). */
export function token({ iat = Math.floor(Date.now() / 1000), exp = iat + 3600, ini = iat, max = ini + 10 * 3600, role = "Técnico" } = {}) {
  const b64 = (o) => btoa(JSON.stringify(o)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  return `${b64({ alg: "HS256" })}.${b64({ sub: "1", role, iat, exp, ini, max })}.firma`;
}

export const USUARIOS = {
  Administrador: { id: 1, name: "Ana Admin", email: "ana@empresa.com", role: "Administrador" },
  Técnico: { id: 2, name: "Tomás Técnico", email: "tomas@empresa.com", role: "Técnico" },
  Solicitante: { id: 3, name: "Sara Solicitante", email: "sara@empresa.com", role: "Solicitante" },
};

export function conSesion(rol = "Técnico") {
  localStorage.setItem("access_token", token({ role: rol }));
  localStorage.setItem("user", JSON.stringify(USUARIOS[rol]));
  return USUARIOS[rol];
}

export function respuesta(cuerpo, { status = 200, headers = {} } = {}) {
  return new Response(typeof cuerpo === "string" ? cuerpo : JSON.stringify(cuerpo), {
    status, headers: { "Content-Type": "application/json", ...headers },
  });
}

/* fetch falso: ``rutas`` es una lista de [prueba(url, opciones), respuesta]. */
export function simularFetch(rutas) {
  const llamadas = [];
  const espia = vi.fn(async (url, opciones = {}) => {
    llamadas.push({ url: String(url), opciones });
    for (const [coincide, resultado] of rutas) {
      const ok = typeof coincide === "function" ? coincide(String(url), opciones) : String(url).startsWith(coincide);
      if (ok) return typeof resultado === "function" ? resultado(String(url), opciones) : resultado.clone();
    }
    return respuesta({ detail: "no simulado" }, { status: 404 });
  });
  vi.stubGlobal("fetch", espia);
  return { espia, llamadas };
}

export function renderApp(ruta = "/") {
  return render(
    <MemoryRouter initialEntries={[ruta]} future={FUTURO}>
      <Proveedores><Rutas /></Proveedores>
    </MemoryRouter>,
  );
}
