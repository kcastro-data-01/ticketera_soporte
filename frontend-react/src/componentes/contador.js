import { api } from "../api/cliente.js";

/* Contador junto a «Tickets» (port de contarParaMenu): Administrador, los
   Nuevos sin asignar; Técnico, los suyos sin resolver; Solicitante, nada. */
export async function contarParaMenu(user) {
  if (!user) return null;
  if (user.role === "Técnico") {
    const response = await api("/api/tickets/summary");
    if (!response.ok) return null;
    const resumen = await response.json();
    return { cantidad: Number(resumen.mios_abiertos), texto: "asignados a usted sin resolver" };
  }
  if (user.role === "Administrador") {
    const response = await api("/api/tickets?state=Nuevo");
    if (!response.ok) return null;
    const tickets = await response.json();
    if (!Array.isArray(tickets)) return null;
    const sinAsignar = tickets.filter((t) => t.assigned_to_id === null || t.assigned_to_id === undefined);
    return { cantidad: sinAsignar.length, texto: "nuevos sin asignar" };
  }
  return null;
}
