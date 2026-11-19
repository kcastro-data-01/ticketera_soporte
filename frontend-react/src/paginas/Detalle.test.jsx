import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { conSesion, renderApp, respuesta, simularFetch } from "../pruebas/ayudas.jsx";

const BASE = {
  id: 7, title: "Impresora sin tóner", description: "No imprime <script>alert(1)</script>", category: "Hardware",
  priority: "Alta", state: "Nuevo", assigned_to_id: null, created_by_id: 3, area_id: 1, area_name: "Soporte IT",
  created_at: "2026-11-10T15:00:00Z", updated_at: "2026-11-10T16:00:00Z",
};
const USERS = [
  { id: 1, name: "Ana Admin", role: "Administrador", area_name: "Soporte IT" },
  { id: 2, name: "Tomás Técnico", role: "Técnico", area_name: "Redes" },
  { id: 3, name: "Sara Solicitante", role: "Solicitante" },
];
const COMENTARIOS = [
  { id: 1, author: "Sara Solicitante", author_id: 3, author_es_it: false, origen: "app", content: "Hola", created_at: "2026-11-10T15:00:00Z" },
  { id: 2, author: "Sara Solicitante", author_id: 3, author_es_it: false, origen: "correo", content: "Sigue igual", created_at: "2026-11-10T15:05:00Z" },
  { id: 3, author: "Tomás Técnico", author_id: 2, author_es_it: true, origen: "estado", estado_nuevo: "En proceso", content: "voy", created_at: "2026-11-10T15:30:00Z" },
  { id: 4, author: "Tomás Técnico", author_id: 2, author_es_it: true, origen: "app", content: "Listo", created_at: "2026-11-10T16:00:00Z" },
];
const ADJUNTOS = (extra = {}) => ({
  adjuntos: [
    { id: 9, ticket_id: 7, nombre: "foto.png", tamano: 2048, subido_por: "Sara Solicitante", creado: "2026-11-10T15:00:00Z", es_imagen: true, por_correo: true, puede_eliminar: true },
    { id: 10, ticket_id: 7, nombre: "acta.pdf", tamano: 900, subido_por: "Ana Admin", creado: "2026-11-10T15:00:00Z", es_imagen: false, por_correo: false, puede_eliminar: false },
  ],
  puede_subir: true, cerrado: false, max_archivos: 10, max_bytes: 4194304, ...extra,
});

/* Servidor simulado con estado: el ticket cambia con PATCH. */
function servidor({ ticket = {}, adjuntos = ADJUNTOS(), estado = 200, comentarios = COMENTARIOS } = {}) {
  let actual = { ...BASE, ...ticket };
  const metodo = (m) => (u, o) => (o.method || "GET") === m;
  const ruta = (re, m = "GET") => (u, o) => re.test(u) && metodo(m)(u, o);
  const fetchs = simularFetch([
    [ruta(/^\/api\/tickets\/7\/comments$/), () => respuesta(comentarios)],
    [ruta(/^\/api\/tickets\/7\/comments$/, "POST"), () => respuesta({ id: 99 }, { status: 201 })],
    [ruta(/^\/api\/tickets\/7\/adjuntos\/\d+\/archivo$/), () => new Response(new Blob(["x"], { type: "image/png" }))],
    [ruta(/^\/api\/tickets\/7\/adjuntos\/\d+$/, "DELETE"), () => new Response(null, { status: 204 })],
    [ruta(/^\/api\/tickets\/7\/adjuntos\?nombre=/, "POST"), () => respuesta({ id: 11 }, { status: 201 })],
    [ruta(/^\/api\/tickets\/7\/adjuntos$/), () => respuesta(adjuntos)],
    [ruta(/^\/api\/tickets\/7\/history$/), () => respuesta([{ id: 1, action: "assigned", old_value: null, new_value: "Tomás Técnico", author: "Ana Admin", created_at: "2026-11-10T15:10:00Z" }])],
    [ruta(/^\/api\/tickets\/7\/explicacion$/), () => respuesta({ explicacion: null, ia_disponible: true })],
    [ruta(/^\/api\/tickets\/7\/explicacion/, "POST"), () => respuesta({
      explicacion: { explicacion: "Falta tóner.", certeza: "alta", posibles_causas: ["Cartucho vacío"], que_revisar_primero: ["Cambiarlo"] },
      vigente: true, claridad: "clara", motivo_claridad: "Se entiende.", modelo: "qwen", generada_en: "2026-11-10T17:00:00Z",
    })],
    [ruta(/^\/api\/tickets\/7\/state$/, "PATCH"), (u, o) => {
      if (estado !== 200) return respuesta({ detail: "La transición de estado no está permitida." }, { status: estado });
      actual = { ...actual, state: JSON.parse(o.body).state };
      return respuesta(actual);
    }],
    [ruta(/^\/api\/tickets\/7\/assign$/, "PATCH"), (u, o) => {
      actual = { ...actual, assigned_to_id: JSON.parse(o.body).assigned_to_id };
      return respuesta(actual);
    }],
    [ruta(/^\/api\/tickets\/7\/area$/, "PATCH"), (u, o) => {
      actual = { ...actual, area_id: JSON.parse(o.body).area_id, area_name: "Redes", assigned_to_id: 2 };
      return respuesta(actual);
    }],
    [ruta(/^\/api\/tickets\/7$/, "PATCH"), (u, o) => { actual = { ...actual, ...JSON.parse(o.body) }; return respuesta(actual); }],
    [ruta(/^\/api\/tickets\/7$/, "DELETE"), () => new Response(null, { status: 204 })],
    [ruta(/^\/api\/tickets\/7$/), () => respuesta(actual)],
    [ruta(/^\/api\/tickets\/404$/), () => respuesta({ detail: "No" }, { status: 404 })],
    [ruta(/^\/api\/tickets\/summary/), () => respuesta({ mios_abiertos: 0 })],
    [ruta(/^\/api\/tickets/), () => respuesta([], { headers: { "X-Total-Count": "0" } })],
    [ruta(/^\/api\/users/), () => respuesta(USERS)],
    [ruta(/^\/api\/areas/), () => respuesta([{ id: 1, name: "Soporte IT" }, { id: 2, name: "Redes" }])],
  ]);
  return { ...fetchs, ticket: () => actual };
}

const cuerpoDe = (llamadas, re, metodo) => {
  const l = llamadas.filter((x) => re.test(x.url) && (x.opciones.method || "GET") === metodo).at(-1);
  return l && l.opciones.body ? JSON.parse(l.opciones.body) : null;
};

async function abrir(rol, opciones, ruta = "/tickets/7") {
  conSesion(rol);
  const s = servidor(opciones);
  renderApp(ruta);
  await waitFor(() => expect(document.getElementById("ver-title")).toHaveTextContent("Impresora sin tóner"));
  return s;
}

describe("Detalle del ticket (/tickets/:id)", () => {
  it("muestra los datos, la ficha y la descripción como texto", async () => {
    await abrir("Administrador");
    expect(screen.getByRole("heading", { name: "Detalle del ticket" })).toBeInTheDocument();
    expect(screen.getByText("Ticket #7")).toBeInTheDocument();
    expect(document.getElementById("ver-description")).toHaveTextContent("No imprime <script>alert(1)</script>");
    expect(document.querySelector("#ver-description script")).toBeNull();
    expect(document.getElementById("ver-state")).toHaveClass("badge", "estado-nuevo");
    expect(document.getElementById("ver-priority")).toHaveClass("prioridad-alta");
    expect(document.getElementById("ver-area")).toHaveTextContent("Soporte IT");
    expect(document.getElementById("ver-assigned")).toHaveTextContent("—");
    const solicitante = document.getElementById("ver-creator");
    expect(solicitante).toHaveTextContent("Sara Solicitante");
    expect(solicitante).toHaveAttribute("data-iniciales", "SS");
    expect(document.getElementById("panel-ticket")).toHaveAttribute("aria-busy", "false");
    expect(screen.getByRole("link", { name: "Volver al listado" })).toHaveAttribute("href", "/");
  });

  it("ticket inexistente e id inválido", async () => {
    conSesion("Técnico");
    servidor();
    renderApp("/tickets/404");
    expect(await screen.findByText("No existe el ticket #404 o no tiene acceso a él.")).toBeInTheDocument();
    expect(document.getElementById("detalle-layout")).not.toBeVisible();
  });

  it("id inválido", async () => {
    conSesion("Técnico");
    servidor();
    renderApp("/tickets/abc");
    expect(await screen.findByText("El identificador del ticket no es válido. Regrese al listado y abra un ticket.")).toBeInTheDocument();
  });

  describe("recorrido de estados", () => {
    it("tocar un paso, confirmar con motivo y cambiar el estado", async () => {
      const { llamadas } = await abrir("Técnico");
      const pasos = document.getElementById("pasos-estado");
      expect(within(pasos).getByText("Nuevo").closest("li")).toHaveClass("actual");
      expect(within(pasos).getByText("Nuevo").closest("li")).toHaveAttribute("aria-current", "step");
      expect(screen.getByText("Toque un estado para cambiarlo.")).toBeVisible();
      await userEvent.click(screen.getByRole("button", { name: "Pasar el ticket a «Resuelto»" }));
      const dialogo = screen.getByRole("alertdialog", { name: "Cambiar estado" });
      expect(dialogo).toHaveTextContent("¿Pasar el ticket #7 a «Resuelto»?");
      await userEvent.type(within(dialogo).getByLabelText("Motivo (opcional)"), "  cambié el tóner ");
      await userEvent.click(within(dialogo).getByRole("button", { name: "Confirmar" }));
      expect(await screen.findByText("Estado actualizado a «Resuelto».")).toBeInTheDocument();
      expect(cuerpoDe(llamadas, /\/state$/, "PATCH")).toEqual({ state: "Resuelto", motivo: "cambié el tóner" });
      await waitFor(() => expect(within(pasos).getByText("Resuelto").closest("li")).toHaveClass("actual"));
      expect(within(pasos).getByText("Nuevo").closest("li")).toHaveClass("hecho");
      /* Desde Resuelto: Cerrado o reabrir a En proceso. */
      expect(screen.getByRole("button", { name: "Pasar el ticket a «En proceso»" })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Pasar el ticket a «Cerrado»" })).toBeInTheDocument();
    });

    it("cancelar no cambia nada y Cerrado avisa que no se reabre", async () => {
      const { llamadas } = await abrir("Administrador");
      await userEvent.click(screen.getByRole("button", { name: "Pasar el ticket a «Cerrado»" }));
      expect(screen.getByRole("alertdialog")).toHaveTextContent("Un ticket Cerrado ya no se puede reabrir.");
      expect(screen.getByLabelText("Motivo (opcional)")).toHaveFocus();
      await userEvent.click(screen.getByRole("button", { name: "Cancelar" }));
      expect(screen.queryByRole("alertdialog")).toBeNull();
      expect(llamadas.some((l) => /\/state$/.test(l.url))).toBe(false);
    });

    it("409 muestra el motivo del servidor", async () => {
      await abrir("Técnico", { estado: 409 });
      await userEvent.click(screen.getByRole("button", { name: "Pasar el ticket a «En proceso»" }));
      await userEvent.click(screen.getByRole("button", { name: "Confirmar" }));
      expect(await screen.findByRole("alert")).toHaveTextContent("La transición de estado no está permitida.");
    });

    it("el Solicitante no toca pasos (salvo que tenga el ticket asignado)", async () => {
      await abrir("Solicitante");
      expect(screen.queryByRole("button", { name: /Pasar el ticket/ })).toBeNull();
      expect(screen.getByText("Toque un estado para cambiarlo.")).not.toBeVisible();
    });

    it("el Solicitante con el ticket asignado sí lo cambia", async () => {
      await abrir("Solicitante", { ticket: { assigned_to_id: 3 } });
      expect(screen.getByRole("button", { name: "Pasar el ticket a «En proceso»" })).toBeInTheDocument();
    });
  });

  describe("permisos", () => {
    it("Administrador: editar, eliminar, asignación y departamento", async () => {
      await abrir("Administrador");
      expect(screen.getByRole("button", { name: "Editar ticket" })).toBeVisible();
      expect(screen.getByRole("button", { name: "Eliminar" })).toBeVisible();
      expect(screen.getByRole("heading", { name: "Asignación" })).toBeVisible();
      expect(screen.getByRole("heading", { name: "Cambiar departamento" })).toBeVisible();
      expect(screen.getByRole("tab", { name: "Explicación IA" })).toBeInTheDocument();
    });

    it("Técnico: sin editar (no lo creó), sin eliminar ni asignar; sí cambia departamento", async () => {
      await abrir("Técnico");
      expect(document.getElementById("editar")).not.toBeVisible();
      expect(screen.queryByRole("button", { name: "Eliminar" })).toBeNull();
      expect(screen.queryByRole("heading", { name: "Asignación" })).toBeNull();
      expect(screen.getByRole("heading", { name: "Cambiar departamento" })).toBeVisible();
    });

    it("Solicitante creador: edita solo en Nuevo, sin IA, asignación ni departamento", async () => {
      await abrir("Solicitante");
      expect(screen.getByRole("button", { name: "Editar ticket" })).toBeVisible();
      expect(screen.queryByRole("tab", { name: "Explicación IA" })).toBeNull();
      expect(screen.queryByRole("heading", { name: "Cambiar departamento" })).toBeNull();
      expect(screen.getByRole("link", { name: "Mis solicitudes" })).toHaveAttribute("href", "/");
    });

    it("Solicitante creador en En proceso: ya no edita", async () => {
      await abrir("Solicitante", { ticket: { state: "En proceso" } });
      expect(document.getElementById("editar")).not.toBeVisible();
    });

    it("el departamento solo se cambia en Nuevo", async () => {
      await abrir("Administrador", { ticket: { state: "En proceso" } });
      expect(screen.getByRole("heading", { name: "Cambiar departamento", hidden: true })).not.toBeVisible();
    });

    it("Cerrado es de solo lectura para todos, también el Administrador", async () => {
      await abrir("Administrador", { ticket: { state: "Cerrado" }, adjuntos: ADJUNTOS({ puede_subir: false, cerrado: true }) });
      expect(screen.getByText(/no admite cambios/)).toBeVisible();
      expect(document.getElementById("editar")).not.toBeVisible();
      expect(document.getElementById("eliminar")).not.toBeVisible();
      expect(document.getElementById("seccion-asignacion")).not.toBeVisible();
      expect(document.getElementById("form-comentario")).not.toBeVisible();
      expect(screen.queryByRole("button", { name: /Pasar el ticket/ })).toBeNull();
      expect(await screen.findByText("El ticket está Cerrado: no se agregan ni se eliminan adjuntos.")).toBeInTheDocument();
      expect(document.getElementById("adj-acciones")).not.toBeVisible();
    });
  });

  it("editar: guarda los cambios, valida y cancelar descarta", async () => {
    const { llamadas } = await abrir("Administrador");
    await userEvent.click(screen.getByRole("button", { name: "Editar ticket" }));
    const titulo = screen.getByLabelText("Título *");
    expect(titulo).toHaveFocus();
    await userEvent.clear(titulo);
    await userEvent.click(screen.getByRole("button", { name: "Guardar cambios" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("El título es obligatorio.");
    await userEvent.type(titulo, "Impresora sin tóner (piso 2)");
    await userEvent.selectOptions(screen.getByLabelText("Prioridad"), "Crítica");
    await userEvent.click(screen.getByRole("button", { name: "Guardar cambios" }));
    expect(await screen.findByText("Cambios guardados correctamente.")).toBeInTheDocument();
    expect(cuerpoDe(llamadas, /\/api\/tickets\/7$/, "PATCH")).toEqual({
      title: "Impresora sin tóner (piso 2)", description: BASE.description, category: "Hardware", priority: "Crítica",
    });
    await waitFor(() => expect(document.getElementById("seccion-edicion")).not.toBeVisible());
    expect(document.getElementById("ver-priority")).toHaveTextContent("Crítica");

    await userEvent.click(screen.getByRole("button", { name: "Editar ticket" }));
    await userEvent.type(screen.getByLabelText("Título *"), " XXX");
    await userEvent.click(screen.getByRole("button", { name: "Cancelar" }));
    expect(await screen.findByText("Edición cancelada. Los datos del ticket no se modificaron.")).toBeInTheDocument();
    expect(document.getElementById("ver-title")).toHaveTextContent("Impresora sin tóner (piso 2)");
  });

  it("asignación: solo Técnicos y Administradores", async () => {
    const { llamadas } = await abrir("Administrador");
    const select = screen.getByLabelText("Persona asignada");
    const opciones = within(select).getAllByRole("option").map((o) => o.textContent);
    expect(opciones).toEqual(["Sin asignar", "Ana Admin · Soporte IT", "Tomás Técnico · Redes"]);
    await userEvent.selectOptions(select, "2");
    await userEvent.click(screen.getByRole("button", { name: "Guardar asignación" }));
    expect(await screen.findByText("Asignación guardada correctamente.")).toBeInTheDocument();
    expect(cuerpoDe(llamadas, /\/assign$/, "PATCH")).toEqual({ assigned_to_id: 2 });
    await waitFor(() => expect(document.getElementById("ver-assigned")).toHaveTextContent("Tomás Técnico"));
  });

  it("un ticket viejo asignado a un Solicitante se ve aparte para reasignarlo", async () => {
    await abrir("Administrador", { ticket: { assigned_to_id: 3 } });
    expect(screen.getByRole("option", { name: "Sara Solicitante (Solicitante: reasígnelo)" })).toBeDisabled();
  });

  it("cambiar departamento con reasignación", async () => {
    const { llamadas } = await abrir("Administrador");
    await waitFor(() => expect(screen.getByLabelText("Nuevo departamento")).toHaveValue("1"));
    await userEvent.selectOptions(screen.getByLabelText("Nuevo departamento"), "2");
    await userEvent.click(screen.getByRole("button", { name: "Cambiar departamento" }));
    expect(await screen.findByText("El ticket pasó al departamento «Redes» y quedó asignado a Tomás Técnico.")).toBeInTheDocument();
    expect(cuerpoDe(llamadas, /\/area$/, "PATCH")).toEqual({ area_id: 2, reasignar: true });
  });

  describe("comentarios", () => {
    it("como conversación: agrupados, IT, por correo y avisos del sistema", async () => {
      await abrir("Técnico");
      const lista = await screen.findByLabelText("Conversación del ticket");
      const tarjetas = lista.querySelectorAll("article.comentario");
      expect(tarjetas).toHaveLength(3);
      expect(tarjetas[0]).toHaveClass("de-otro");
      expect(tarjetas[1]).toHaveClass("seguido");
      expect(within(tarjetas[1]).getByText("por correo")).toBeInTheDocument();
      expect(tarjetas[2]).toHaveClass("de-it");
      expect(within(tarjetas[2]).getByText("IT")).toBeInTheDocument();
      expect(lista.querySelector(".comentario-sistema")).toHaveTextContent("Pasó a En proceso · voy");
    });

    it("agrega un comentario y no acepta vacío", async () => {
      const { llamadas } = await abrir("Solicitante");
      await screen.findByLabelText("Conversación del ticket");
      await userEvent.click(screen.getByRole("button", { name: "Agregar comentario" }));
      expect(await screen.findByRole("alert")).toHaveTextContent("El comentario no puede estar vacío.");
      await userEvent.type(screen.getByLabelText("Nuevo comentario"), "Gracias");
      await userEvent.click(screen.getByRole("button", { name: "Agregar comentario" }));
      expect(await screen.findByText("Comentario agregado correctamente.")).toBeInTheDocument();
      expect(cuerpoDe(llamadas, /\/comments$/, "POST")).toEqual({ content: "Gracias" });
      expect(screen.getByLabelText("Nuevo comentario")).toHaveValue("");
    });

    it("sin comentarios", async () => {
      await abrir("Técnico", { comentarios: [] });
      expect(await screen.findByText("Todavía no hay comentarios.")).toBeInTheDocument();
    });
  });

  describe("adjuntos", () => {
    it("lista con miniatura, por correo, descargar y eliminar según permisos", async () => {
      await abrir("Solicitante");
      const lista = await waitFor(() => {
        const l = document.getElementById("adj-lista");
        expect(l).toBeVisible();
        return l;
      });
      expect(within(lista).getByText(/2 KB · Sara Solicitante · .* · por correo/)).toBeInTheDocument();
      expect(within(lista).getByText("PDF")).toBeInTheDocument();
      expect(within(lista).getByRole("button", { name: "Eliminar foto.png" })).toBeInTheDocument();
      expect(within(lista).queryByRole("button", { name: "Eliminar acta.pdf" })).toBeNull();
      expect(screen.getByText("jpg, png, pdf, docx, xlsx o txt · hasta 4 MB cada uno · 2 de 10")).toBeInTheDocument();
    });

    it("vista ampliada: se abre, Escape la cierra y el foco vuelve", async () => {
      URL.createObjectURL = vi.fn(() => "blob:local");
      URL.revokeObjectURL = vi.fn();
      await abrir("Técnico");
      await screen.findAllByRole("button", { name: "Ver imagen foto.png" });
      const ver = document.querySelector(".adjunto-ver");
      await userEvent.click(ver);
      const visor = screen.getByRole("dialog", { name: "foto.png" });
      expect(within(visor).getByRole("button", { name: "Cerrar vista previa" })).toHaveFocus();
      await waitFor(() => expect(within(visor).getByRole("img", { name: "foto.png" })).toHaveAttribute("src", "blob:local"));
      await userEvent.keyboard("{Escape}");
      expect(screen.queryByRole("dialog")).toBeNull();
      expect(ver).toHaveFocus();
    });

    it("subir: valida el tipo y sube los válidos uno por uno", async () => {
      const { llamadas } = await abrir("Técnico");
      await screen.findByText(/2 de 10/);
      const input = screen.getByTestId("adj-archivos");
      const bueno = new File(["hola"], "nota.txt", { type: "text/plain" });
      const malo = new File(["MZ"], "virus.exe", { type: "application/octet-stream" });
      await userEvent.upload(input, [bueno, malo], { applyAccept: false });
      expect(await screen.findByText("Archivo adjuntado.")).toBeInTheDocument();
      expect(await screen.findByText("«virus.exe»: tipo no permitido. Se aceptan jpg, png, pdf, docx, xlsx o txt.")).toBeInTheDocument();
      const subidas = llamadas.filter((l) => l.url.includes("/adjuntos?nombre="));
      expect(subidas.map((l) => l.url)).toEqual(["/api/tickets/7/adjuntos?nombre=nota.txt"]);
      expect(subidas[0].opciones.body).toBeInstanceOf(File);
      expect(subidas[0].opciones.headers["Content-Type"]).toBe("application/octet-stream");
    });

    it("eliminar pide confirmación", async () => {
      const { llamadas } = await abrir("Administrador");
      await userEvent.click(await screen.findByRole("button", { name: "Eliminar foto.png" }));
      expect(screen.getByRole("alertdialog", { name: "Eliminar adjunto" })).toBeInTheDocument();
      await userEvent.click(within(screen.getByRole("alertdialog")).getByRole("button", { name: "Eliminar" }));
      expect(await screen.findByText("«foto.png» eliminado.")).toBeInTheDocument();
      expect(llamadas.some((l) => l.url === "/api/tickets/7/adjuntos/9" && l.opciones.method === "DELETE")).toBe(true);
    });
  });

  it("historial del ticket", async () => {
    await abrir("Técnico");
    await userEvent.click(screen.getByRole("tab", { name: "Historial" }));
    await userEvent.click(screen.getByRole("button", { name: "Ver historial" }));
    const tabla = await screen.findByRole("table");
    expect(within(tabla).getByText("Asignó el ticket")).toBeInTheDocument();
    expect(within(tabla).getByText("Sin asignar → Tomás Técnico")).toBeInTheDocument();
    expect(localStorage.getItem("detalle_pestana")).toBe("historial");
  });

  it("pestañas: ?pestana=ia abre la de IA y las flechas cambian", async () => {
    const { llamadas } = await abrir("Técnico", {}, "/tickets/7?pestana=ia");
    const ia = screen.getByRole("tab", { name: "Explicación IA" });
    expect(ia).toHaveAttribute("aria-selected", "true");
    await userEvent.click(screen.getByRole("button", { name: "Explicar con IA" }));
    expect(await screen.findByText("Falta tóner.")).toBeInTheDocument();
    expect(screen.getByText("Cartucho vacío")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Volver a explicar" })).toBeVisible();
    expect(llamadas.some((l) => l.url === "/api/tickets/7/explicacion" && l.opciones.method === "POST")).toBe(true);
    ia.focus();
    await userEvent.keyboard("{ArrowRight}");
    expect(screen.getByRole("tab", { name: "Comentarios" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "Comentarios" })).toHaveFocus();
  });

  it("eliminar el ticket vuelve al listado con el aviso", async () => {
    const { llamadas } = await abrir("Administrador");
    await userEvent.click(screen.getByRole("button", { name: "Eliminar" }));
    const dialogo = screen.getByRole("alertdialog", { name: "Eliminar ticket" });
    expect(within(dialogo).getByRole("button", { name: "Cancelar" })).toHaveFocus();
    await userEvent.click(within(dialogo).getByRole("button", { name: "Eliminar" }));
    expect(await screen.findByText("Ticket #7 eliminado correctamente.", {}, { timeout: 3000 })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Tickets" })).toBeInTheDocument();
    expect(llamadas.some((l) => l.url === "/api/tickets/7" && l.opciones.method === "DELETE")).toBe(true);
  });

  it("imprimir abre el diálogo del navegador", async () => {
    const print = vi.fn();
    window.print = print;
    await abrir("Técnico");
    await userEvent.click(screen.getByRole("button", { name: "Imprimir" }));
    expect(print).toHaveBeenCalled();
    document.documentElement.setAttribute("data-tema", "oscuro");
    window.dispatchEvent(new Event("beforeprint"));
    expect(document.documentElement).not.toHaveAttribute("data-tema");
    expect(document.getElementById("impresion-fecha")).toHaveTextContent(/^Impreso el /);
    window.dispatchEvent(new Event("afterprint"));
    expect(document.documentElement).toHaveAttribute("data-tema", "oscuro");
  });
});
