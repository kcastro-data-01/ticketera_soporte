import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { conSesion, renderApp, respuesta, simularFetch } from "../pruebas/ayudas.jsx";
import { destinoDeEnlace, textoParaCopiar } from "./formato.jsx";
import { recortarConversacion } from "./Asistente.jsx";

/* Respuesta NDJSON por partes, como la del servidor. */
function flujo(eventos) {
  const codificar = new TextEncoder();
  const cuerpo = new ReadableStream({
    start(control) {
      eventos.forEach((e) => control.enqueue(codificar.encode(`${JSON.stringify(e)}\n`)));
      control.close();
    },
  });
  return new Response(cuerpo, { status: 200, headers: { "Content-Type": "application/x-ndjson" } });
}

function servidor(eventos = [{ t: "Hay **2** tickets: " }, { t: "#5 y [la explicación](detalle.html?id=7&pestana=ia)." }, { fin: true, fuente: "sistema" }]) {
  return simularFetch([
    [(u, o) => u === "/api/asistente/stream" && o.method === "POST", () => (Array.isArray(eventos) ? flujo(eventos) : eventos)],
    [(u) => /^\/api\/tickets\/\d+$/.test(u), () => respuesta({ id: 7, title: "VPN", description: "x", category: "Red", priority: "Alta", state: "Nuevo", created_by_id: 3, created_at: "2026-11-10T15:00:00Z", updated_at: "2026-11-10T15:00:00Z" })],
    [(u) => /\/adjuntos$/.test(u), () => respuesta({ adjuntos: [], puede_subir: true, cerrado: false, max_archivos: 10, max_bytes: 4194304 })],
    ["/api/tickets/summary", respuesta({ mios_abiertos: 0 })],
    ["/api/", respuesta([])],
  ]);
}

const abrirChat = async () => {
  await userEvent.click(await screen.findByRole("button", { name: "Abrir asistente virtual" }));
  return screen.getByRole("region", { name: "Asistente virtual" });
};

describe("Asistente virtual", () => {
  it("botón flotante en todas las pantallas con sesión; no en el login", async () => {
    servidor();
    renderApp("/login");
    await screen.findByRole("heading", { name: "Iniciar sesión" });
    expect(screen.queryByRole("button", { name: "Abrir asistente virtual" })).toBeNull();
  });

  it("saludo con sugerencias según el rol", async () => {
    conSesion("Solicitante");
    servidor();
    renderApp("/");
    const panel = await abrirChat();
    expect(within(panel).getByText("Buen día. ¿En qué le puedo ayudar? Puede consultar, por ejemplo:")).toBeInTheDocument();
    expect(within(panel).getAllByRole("button", { name: /\?$/ }).map((b) => b.textContent)).toEqual([
      "¿Cómo va mi solicitud?", "¿Cómo creo un ticket?", "¿Cuántos tickets tengo abiertos?",
    ]);
    expect(within(panel).getByText("Hoy")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cerrar asistente virtual" })).toHaveAttribute("aria-expanded", "true");
  });

  it("pregunta y muestra la respuesta exacta por partes, con enlaces a /tickets/N", async () => {
    conSesion("Técnico");
    const { llamadas } = servidor();
    renderApp("/");
    const panel = await abrirChat();
    await userEvent.type(within(panel).getByLabelText("Su consulta"), "¿Cuántos hay?{Enter}");
    await waitFor(() => expect(within(panel).getByText(/Hay/)).toBeInTheDocument());
    const respuestaEl = within(panel).getByText(/Hay/).closest(".chat-mensaje");
    expect(respuestaEl).toHaveTextContent("Hay 2 tickets: #5 y la explicación.");
    expect(within(respuestaEl).getByText("2").tagName).toBe("STRONG");
    expect(within(respuestaEl).getByRole("link", { name: "#5" })).toHaveAttribute("href", "/tickets/5");
    expect(within(respuestaEl).getByRole("link", { name: "la explicación" })).toHaveAttribute("href", "/tickets/7?pestana=ia");
    const pedido = JSON.parse(llamadas.find((l) => l.url === "/api/asistente/stream").opciones.body);
    expect(pedido).toEqual({ messages: [{ role: "user", content: "¿Cuántos hay?" }] });
    const guardado = JSON.parse(sessionStorage.getItem("asistente_chat"));
    expect(guardado.map((m) => m.role)).toEqual(["user", "assistant"]);
    expect(guardado[1].content).toBe("Hay **2** tickets: #5 y [la explicación](detalle.html?id=7&pestana=ia).");
    expect(within(panel).getByRole("button", { name: "Copiar respuesta" })).toBeInTheDocument();
  });

  it("en el detalle de un ticket manda su número", async () => {
    conSesion("Técnico");
    const { llamadas } = servidor();
    renderApp("/tickets/7");
    const panel = await abrirChat();
    await userEvent.type(within(panel).getByLabelText("Su consulta"), "Explique este ticket{Enter}");
    await waitFor(() => expect(llamadas.some((l) => l.url === "/api/asistente/stream")).toBe(true));
    expect(JSON.parse(llamadas.find((l) => l.url === "/api/asistente/stream").opciones.body).ticket_id).toBe(7);
  });

  it("los enlaces viejos guardados en la conversación llevan a React", async () => {
    sessionStorage.setItem("asistente_chat", JSON.stringify([
      { role: "user", content: "hola", hora: new Date().toISOString() },
      { role: "assistant", content: "Vea [el ticket 3](detalle.html?id=3) o [este](/tickets/4).", hora: new Date().toISOString() },
    ]));
    conSesion("Técnico");
    servidor();
    renderApp("/");
    const panel = await abrirChat();
    expect(within(panel).getByRole("link", { name: "el ticket 3" })).toHaveAttribute("href", "/tickets/3");
    expect(within(panel).getByRole("link", { name: "este" })).toHaveAttribute("href", "/tickets/4");
    await userEvent.click(within(panel).getByRole("link", { name: "el ticket 3" }));
    expect(await screen.findByRole("heading", { name: "Detalle del ticket" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Abrir asistente virtual" })).toHaveAttribute("aria-expanded", "false");
  });

  it("error del servidor: aviso que no se guarda y la pregunta se puede reintentar", async () => {
    conSesion("Técnico");
    servidor(respuesta({ detail: "Demasiadas preguntas seguidas." }, { status: 429 }));
    renderApp("/");
    const panel = await abrirChat();
    await userEvent.type(within(panel).getByLabelText("Su consulta"), "hola{Enter}");
    const error = await within(panel).findByText("Demasiadas preguntas seguidas.");
    expect(error).toHaveClass("chat-mensaje", "asistente", "error");
    expect(JSON.parse(sessionStorage.getItem("asistente_chat")).map((m) => m.role)).toEqual(["assistant"]);
  });

  it("IA sin respuesta: «La IA no está disponible en este momento»", async () => {
    conSesion("Técnico");
    servidor([{ error: "" }, { fin: true }]);
    renderApp("/");
    const panel = await abrirChat();
    await userEvent.type(within(panel).getByLabelText("Su consulta"), "hola{Enter}");
    expect(await within(panel).findByText("La IA no está disponible en este momento")).toBeInTheDocument();
  });

  it("«reemplazo» cambia la respuesta de la IA por la del sistema", async () => {
    conSesion("Técnico");
    servidor([{ t: "respuesta mala" }, { reemplazo: "Hay 3 tickets pendientes." }, { fin: true, fuente: "sistema" }]);
    renderApp("/");
    const panel = await abrirChat();
    await userEvent.type(within(panel).getByLabelText("Su consulta"), "hola{Enter}");
    expect(await within(panel).findByText("Hay 3 tickets pendientes.")).toBeInTheDocument();
    expect(within(panel).queryByText("respuesta mala")).toBeNull();
  });

  it("agrandar se recuerda, Nueva conversación borra y Escape cierra", async () => {
    sessionStorage.setItem("asistente_chat", JSON.stringify([{ role: "user", content: "vieja" }]));
    conSesion("Técnico");
    servidor();
    renderApp("/");
    const panel = await abrirChat();
    await userEvent.click(within(panel).getByRole("button", { name: "Agrandar ventana" }));
    expect(document.getElementById("chat-asistente")).toHaveClass("grande");
    expect(localStorage.getItem("asistente_grande")).toBe("1");
    expect(within(panel).getByText("vieja")).toBeInTheDocument();
    await userEvent.click(within(panel).getByRole("button", { name: "Nueva conversación" }));
    expect(within(panel).queryByText("vieja")).toBeNull();
    await userEvent.keyboard("{Escape}");
    expect(screen.getByRole("button", { name: "Abrir asistente virtual" })).toBeInTheDocument();
  });

  it("formato: el texto del servidor nunca se interpreta como HTML", async () => {
    conSesion("Técnico");
    servidor([{ t: "Resumen:\n- uno <img src=x onerror=alert(1)>\n- dos\n\n1. paso" }, { fin: true }]);
    renderApp("/");
    const panel = await abrirChat();
    await userEvent.type(within(panel).getByLabelText("Su consulta"), "x{Enter}");
    await within(panel).findByText("Resumen:");
    expect(within(panel).getByText("Resumen:")).toHaveClass("chat-titulo-respuesta");
    expect(panel.querySelector("ul.chat-lista-respuesta").children).toHaveLength(2);
    expect(panel.querySelector("ol.chat-lista-respuesta")).not.toBeNull();
    expect(within(panel).getByText("uno <img src=x onerror=alert(1)>")).toBeInTheDocument();
    expect(panel.querySelector("img")).toBeNull();
  });

  it("enlaces: solo a tickets; cualquier otro destino queda como texto", () => {
    expect(destinoDeEnlace("[a](detalle.html?id=12)")).toEqual({ texto: "a", a: "/tickets/12" });
    expect(destinoDeEnlace("[a](/tickets/12?pestana=ia)")).toEqual({ texto: "a", a: "/tickets/12?pestana=ia" });
    expect(destinoDeEnlace("[a](https://malo.com)")).toBeNull();
    expect(destinoDeEnlace("[a](javascript:alert(1))")).toBeNull();
    expect(textoParaCopiar("Ver **[el 3](detalle.html?id=3)**")).toBe("Ver el 3");
    expect(recortarConversacion([{ role: "assistant", content: "a" }, { role: "user", content: "b", hora: "x" }])).toEqual([{ role: "user", content: "b" }]);
  });
});
