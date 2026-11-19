import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { conSesion, renderApp, respuesta, simularFetch, USUARIOS } from "../pruebas/ayudas.jsx";

const TICKETS = [
  { id: 11, title: "Impresora sin tóner", category: "Hardware", priority: "Alta", state: "Nuevo", assigned_to_id: null, created_by_id: 3, created_at: "2026-11-10T15:00:00Z" },
  { id: 12, title: "<img src=x onerror=alert(1)>", category: "Red", priority: "Crítica", state: "En proceso", assigned_to_id: 2, created_by_id: 1, created_at: "2026-11-11T15:00:00Z" },
  { id: 13, title: "Clave de correo", category: "Accesos", priority: "Baja", state: "Resuelto", assigned_to_id: 3, created_by_id: 3, created_at: "2026-11-12T15:00:00Z" },
];
const USERS = [
  { id: 1, name: "Ana Admin", is_active: true },
  { id: 2, name: "Tomás Técnico", is_active: true },
  { id: 3, name: "Sara Solicitante", is_active: true },
  { id: 4, name: "Inactivo", is_active: false },
];
const AREAS = [{ id: 1, name: "Redes" }, { id: 2, name: "Soporte" }];

function servidor({ tickets = TICKETS, total, estado = 200, resumen = { mios_abiertos: 3 } } = {}) {
  return simularFetch([
    ["/api/tickets/summary", respuesta(resumen)],
    [(u) => u === "/api/tickets?state=Nuevo", respuesta(TICKETS.filter((t) => t.state === "Nuevo"))],
    ["/api/tickets", estado === 200
      ? respuesta(tickets, { headers: { "X-Total-Count": String(total ?? tickets.length) } })
      : respuesta({ detail: "Algo falló" }, { status: estado })],
    ["/api/users", respuesta(USERS)],
    ["/api/areas", respuesta(AREAS)],
  ]);
}

const pedidosListado = (llamadas) => llamadas
  .map((l) => l.url).filter((u) => u.startsWith("/api/tickets?") && u.includes("limit="));
const ultimo = (llamadas) => new URL(pedidosListado(llamadas).at(-1), "http://x").searchParams;

describe("Tickets (/)", () => {
  it("sin sesión va al login", async () => {
    servidor();
    renderApp("/");
    expect(await screen.findByRole("heading", { name: "Iniciar sesión" })).toBeInTheDocument();
  });

  it("lista los tickets con los nombres, el total y enlaces a /tickets/:id", async () => {
    conSesion("Administrador");
    servidor({ total: 3 });
    renderApp("/");
    expect(await screen.findByText("Impresora sin tóner")).toBeInTheDocument();
    expect(screen.getByText("3 tickets")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "11" })).toHaveAttribute("href", "/tickets/11");
    const fila = screen.getByText("Impresora sin tóner").closest("tr");
    expect(fila).toHaveClass("fila-alta");
    expect(within(fila).getByText("—")).toHaveClass("sin-asignar");
    const tecnico = within(screen.getByText("Clave de correo").closest("tr")).getByText("Sara Solicitante");
    expect(tecnico).toHaveClass("con-avatar");
    expect(tecnico).toHaveAttribute("data-iniciales", "SS");
    /* El Administrador puede editar todo lo no cerrado. */
    expect(within(fila).getByRole("button", { name: "Editar" })).toBeInTheDocument();
    expect(document.title).toBe("Tickets · American Data Networks");
  });

  it("el texto de los usuarios se muestra como texto", async () => {
    conSesion("Técnico");
    servidor();
    renderApp("/");
    expect(await screen.findByText("<img src=x onerror=alert(1)>")).toBeInTheDocument();
    expect(document.querySelector("img[src='x']")).toBeNull();
  });

  it("filtros: busca con Buscar, «Mis tickets» y Limpiar", async () => {
    conSesion("Técnico");
    const { llamadas } = servidor();
    renderApp("/");
    await screen.findByText("Impresora sin tóner");
    await userEvent.type(screen.getByLabelText("Buscar"), "correo");
    await userEvent.selectOptions(screen.getByLabelText("Categoría"), "Accesos");
    await userEvent.selectOptions(screen.getByLabelText("Prioridad"), "Baja");
    await userEvent.selectOptions(screen.getByLabelText("Estado"), "abiertos");
    await userEvent.selectOptions(screen.getByLabelText("Asignado a"), "sin");
    await userEvent.selectOptions(screen.getByLabelText("Departamento"), "2");
    await userEvent.type(screen.getByLabelText("Fecha de creación"), "2026-11-10");
    const antes = pedidosListado(llamadas).length;
    await userEvent.click(screen.getByRole("button", { name: "Buscar" }));
    await waitFor(() => expect(pedidosListado(llamadas).length).toBe(antes + 1));
    let p = ultimo(llamadas);
    expect(p.get("search")).toBe("correo");
    expect(p.get("category")).toBe("Accesos");
    expect(p.get("priority")).toBe("Baja");
    expect(p.getAll("state")).toEqual(["Nuevo", "En proceso"]);
    expect(p.get("sin_asignar")).toBe("true");
    expect(p.get("area")).toBe("2");
    expect(p.get("desde")).toBe("2026-11-10");

    await userEvent.click(screen.getByRole("button", { name: "Mis tickets" }));
    await waitFor(() => expect(ultimo(llamadas).get("mios")).toBe("true"));
    expect(screen.getByRole("button", { name: "Mis tickets" })).toHaveAttribute("aria-pressed", "true");

    await userEvent.click(screen.getByRole("button", { name: "Limpiar filtros" }));
    await waitFor(() => expect([...ultimo(llamadas).keys()]).toEqual(["limit"]));
    expect(screen.getByLabelText("Buscar")).toHaveValue("");
  });

  it("«Asignado a» ofrece Sin asignar y los usuarios activos; Departamento las áreas", async () => {
    conSesion("Administrador");
    servidor();
    renderApp("/");
    await screen.findByText("Impresora sin tóner");
    const asignado = within(screen.getByLabelText("Asignado a")).getAllByRole("option").map((o) => o.textContent);
    expect(asignado).toEqual(["Todos", "Sin asignar", "Ana Admin", "Sara Solicitante", "Tomás Técnico"]);
    const areas = within(screen.getByLabelText("Departamento")).getAllByRole("option").map((o) => o.textContent);
    expect(areas).toEqual(["Todos", "Sin departamento", "Redes", "Soporte"]);
  });

  it("aplica los filtros de la dirección (desde Departamentos) y el aviso de antigüedad", async () => {
    conSesion("Administrador");
    const { llamadas } = servidor();
    renderApp("/?area=1&estado=abiertos&antiguedad=5");
    expect(await screen.findByText("Solo los creados hace más de 5 días.")).toBeVisible();
    const p = ultimo(llamadas);
    expect(p.get("area")).toBe("1");
    expect(p.getAll("state")).toEqual(["Nuevo", "En proceso"]);
    expect(p.has("creado_antes")).toBe(true);
    expect(screen.getByLabelText("Departamento")).toHaveValue("1");
    await userEvent.click(screen.getByRole("button", { name: "Quitar" }));
    await waitFor(() => expect(ultimo(llamadas).has("creado_antes")).toBe(false));
  });

  it("ordena por columna y lo recuerda", async () => {
    conSesion("Técnico");
    servidor();
    renderApp("/");
    await screen.findByText("Impresora sin tóner");
    const ids = () => screen.getAllByRole("link").filter((a) => /^\/tickets\//.test(a.getAttribute("href")) && a.closest("tbody")).map((a) => a.textContent);
    await userEvent.click(screen.getByRole("button", { name: "Prioridad" }));
    expect(ids()).toEqual(["12", "11", "13"]);
    expect(screen.getByRole("button", { name: "Prioridad" }).closest("th")).toHaveAttribute("aria-sort", "ascending");
    await userEvent.click(screen.getByRole("button", { name: "Prioridad" }));
    expect(ids()).toEqual(["13", "11", "12"]);
    expect(JSON.parse(localStorage.getItem("orden_listado"))).toEqual({ campo: "priority", dir: "desc" });
  });

  it("vista Tablero: una columna por estado con tarjetas que abren el ticket", async () => {
    conSesion("Técnico");
    servidor();
    renderApp("/");
    await screen.findByText("Impresora sin tóner");
    await userEvent.click(screen.getByRole("button", { name: "Tablero" }));
    expect(localStorage.getItem("vista_listado")).toBe("tablero");
    expect(document.getElementById("tabla-tickets")).not.toBeVisible();
    const tablero = document.getElementById("tablero");
    const columnas = within(tablero).getAllByRole("heading", { level: 2 }).map((h) => h.textContent);
    expect(columnas).toEqual(["Nuevo1", "En proceso1", "Resuelto1", "Cerrado0"]);
    expect(within(tablero).getByText("Sin tickets")).toBeInTheDocument();
    expect(within(tablero).getByText("Impresora sin tóner").closest("a")).toHaveAttribute("href", "/tickets/11");
    expect(within(tablero).getByText("Sin asignar")).toBeInTheDocument();
    expect(document.getElementById("densidad")).not.toBeVisible();
  });

  it("densidad compacta", async () => {
    conSesion("Técnico");
    servidor();
    renderApp("/");
    await screen.findByText("Impresora sin tóner");
    await userEvent.click(screen.getByRole("button", { name: "Compacta" }));
    expect(document.getElementById("tabla-tickets")).toHaveClass("densidad-compacta");
    expect(localStorage.getItem("densidad_listado")).toBe("compacta");
  });

  it("mensajes de vacío y de error de la API", async () => {
    conSesion("Técnico");
    servidor({ tickets: [] });
    renderApp("/");
    expect(await screen.findByText("No hay tickets para mostrar.")).toBeInTheDocument();
  });

  it("error de la API con el detalle", async () => {
    conSesion("Técnico");
    servidor({ estado: 500 });
    renderApp("/");
    expect(await screen.findByText("Error de API (500): Algo falló")).toBeInTheDocument();
  });

  describe("Solicitante", () => {
    it("ve «Mis solicitudes» sin datos del equipo", async () => {
      conSesion("Solicitante");
      const { llamadas } = servidor();
      renderApp("/");
      expect(await screen.findByRole("heading", { name: "Mis solicitudes" })).toBeInTheDocument();
      await screen.findByText("Impresora sin tóner");
      expect(screen.queryByLabelText("Categoría")).toBeNull();
      expect(screen.queryByLabelText("Asignado a")).toBeNull();
      expect(screen.queryByRole("button", { name: "Tablero" })).toBeNull();
      expect(screen.queryByRole("button", { name: "Mis tickets" })).toBeNull();
      expect(screen.getByRole("columnheader", { name: "Atendido por" })).toBeInTheDocument();
      expect(screen.getByText("Pendiente de asignar")).toBeInTheDocument();
      expect(screen.getByText("Asignado a usted")).toBeInTheDocument();
      expect(screen.getByText("Impresora sin tóner").closest("tr")).not.toHaveClass("fila-alta");
      /* Su ticket Nuevo lo puede editar; el resto, ver. */
      expect(within(screen.getByText("Impresora sin tóner").closest("tr")).getByRole("button")).toHaveTextContent("Editar");
      expect(within(screen.getByText("Clave de correo").closest("tr")).getByRole("button")).toHaveTextContent("Ver");
      expect(llamadas.some((l) => l.url.startsWith("/api/areas"))).toBe(false);
    });

    it("sin solicitudes invita a crear la primera", async () => {
      conSesion("Solicitante");
      servidor({ tickets: [] });
      renderApp("/");
      expect(await screen.findByText("Todavía no ha creado solicitudes.")).toBeVisible();
      expect(document.getElementById("tabla-tickets")).not.toBeVisible();
    });
  });
});

describe("menú lateral por rol", () => {
  const enlaces = () => within(screen.getByRole("navigation", { name: "Menú principal" }))
    .getAllByRole("link").map((a) => a.textContent.replace(/\d+\+?$/, ""));

  it("Administrador ve todo y el contador de nuevos sin asignar", async () => {
    conSesion("Administrador");
    servidor();
    renderApp("/");
    await screen.findByText("Impresora sin tóner");
    expect(enlaces()).toEqual(["Tickets", "Nuevo ticket", "Historial", "Métricas", "Departamentos", "Usuarios", "Ayuda"]);
    const tickets = await screen.findByRole("link", { name: "Tickets: 1 nuevos sin asignar" });
    expect(tickets).toHaveClass("activo");
    expect(tickets).toHaveAttribute("aria-current", "page");
  });

  it("Técnico: sin Administración y con sus tickets sin resolver", async () => {
    conSesion("Técnico");
    servidor({ resumen: { mios_abiertos: 120 } });
    renderApp("/");
    await screen.findByText("Impresora sin tóner");
    expect(enlaces()).toEqual(["Tickets", "Nuevo ticket", "Historial", "Ayuda"]);
    const tickets = await screen.findByRole("link", { name: "Tickets: 120 asignados a usted sin resolver" });
    expect(within(tickets).getByText("99+")).toBeInTheDocument();
  });

  it("Solicitante: Tickets, Nuevo ticket y Ayuda, sin contador", async () => {
    conSesion("Solicitante");
    servidor();
    renderApp("/");
    await screen.findByText("Impresora sin tóner");
    expect(enlaces()).toEqual(["Tickets", "Nuevo ticket", "Ayuda"]);
    expect(document.querySelector(".menu-contador")).toBeNull();
  });

  it("ruta con permiso que el rol no tiene → Acceso restringido", async () => {
    conSesion("Técnico");
    servidor();
    renderApp("/metricas");
    expect(await screen.findByRole("heading", { name: "Acceso restringido" })).toBeInTheDocument();
  });

  it("menú de usuario: nombre, rol y Cerrar sesión", async () => {
    conSesion("Técnico");
    servidor();
    renderApp("/");
    await screen.findByText("Impresora sin tóner");
    const boton = screen.getByRole("button", { name: `Menú de ${USUARIOS.Técnico.name}` });
    await userEvent.click(boton);
    expect(boton).toHaveAttribute("aria-expanded", "true");
    await userEvent.click(screen.getByRole("menuitem", { name: "Cerrar sesión" }));
    expect(localStorage.getItem("access_token")).toBeNull();
    expect(localStorage.getItem("sesion_cierre")).toBe("manual");
  });

  it("modo oscuro y menú plegado se recuerdan", async () => {
    conSesion("Técnico");
    servidor();
    renderApp("/");
    await screen.findByText("Impresora sin tóner");
    await userEvent.click(screen.getByRole("button", { name: "Activar modo oscuro" }));
    expect(document.documentElement).toHaveAttribute("data-tema", "oscuro");
    expect(localStorage.getItem("tema")).toBe("oscuro");
    expect(screen.getByRole("button", { name: "Activar modo claro" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Achicar menú" }));
    expect(document.body).toHaveClass("menu-plegado");
    expect(localStorage.getItem("menu_plegado")).toBe("1");
  });

  it("pantallas no migradas abren la versión actual", async () => {
    const { navegador } = await import("../sesion/almacen.js");
    conSesion("Técnico");
    servidor();
    renderApp("/tickets/12");
    await waitFor(() => expect(navegador.reemplazar).toHaveBeenCalledWith("/detalle.html?id=12"));
  });
});
