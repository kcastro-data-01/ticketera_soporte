/* Detalle y gestión de un ticket (port de frontend/detalle.html + js/detalle.js):
   datos y ficha, recorrido de estados, edición, asignación, departamento,
   comentarios, adjuntos, historial, explicación con IA, eliminar e imprimir.
   Un ticket Cerrado es de solo lectura para todos. El servidor vuelve a
   validar cada regla. */
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api } from "../api/cliente.js";
import { avisoPendiente, useAvisos } from "../avisos/Avisos.jsx";
import SeccionAdjuntos from "../adjuntos/SeccionAdjuntos.jsx";
import Cabecera, { Migas } from "../componentes/Cabecera.jsx";
import { useConfirmar } from "../componentes/Confirmar.jsx";
import { useTitulo } from "../componentes/claseBody.js";
import { useSesion } from "../contexto/SesionContext.jsx";
import Conversacion from "../detalle/Conversacion.jsx";
import ExplicacionIA from "../detalle/ExplicacionIA.jsx";
import PasosEstado from "../detalle/PasosEstado.jsx";
import { formatValidation, mensajeDeDetalle, validarTexto } from "../detalle/comentarios.js";
import { autorHistorial, describirHistorial } from "../detalle/historial.js";
import {
  ROLES_IT, SIN_AREA, TRANSICIONES, claseBadge, formatearFechaHora, persona, puede as puedeRol,
  puedeCambiarEstado, puedeEditarTicket, ticketCerrado,
} from "../sesion/permisos.js";
import { CATEGORIAS, PRIORIDADES } from "../tickets/filtros.js";

const PESTANA_KEY = "detalle_pestana";
const ALTO_MAXIMO_COMENTARIO = 320;
const ERROR_API = "Error al comunicarse con la API.";

/* «martes 17 de noviembre a las 4:00 p. m.», hora de Costa Rica. */
function fechaCierreAutomatico(valor) {
  const fecha = new Date(valor);
  if (Number.isNaN(fecha.getTime())) return "";
  const dia = new Intl.DateTimeFormat("es-CR", { timeZone: "America/Costa_Rica", weekday: "long", day: "numeric", month: "long" }).format(fecha);
  return `${dia} a las ${formatearFechaHora(fecha, { parte: "hora" })}`;
}

function idValido(raw) {
  const id = Number(raw);
  return /^\d+$/.test(String(raw || "")) && Number.isInteger(id) && id > 0 ? id : null;
}

function Dato({ etiqueta, children }) {
  return <div className="dato"><dt>{etiqueta}</dt>{children}</div>;
}

/* Asignado y Solicitante: círculo de iniciales, nombre y el completo al pasar el mouse. */
function PersonaFicha({ id, nombre }) {
  const p = persona(nombre);
  return <dd id={id} className={p.className || undefined} data-iniciales={p.iniciales} title={nombre && nombre !== "—" ? nombre : ""}>{p.texto}</dd>;
}

function useEstadoTexto() {
  const [estado, setEstado] = useState(null);
  return [estado, (texto, tipo = "") => setEstado(texto ? { texto, tipo } : null)];
}

function Estado({ id, estado }) {
  return (
    <p id={id} className={estado && estado.tipo ? `estado ${estado.tipo}` : "estado"} role="status" aria-live="polite" hidden={!estado}>
      {estado ? estado.texto : ""}
    </p>
  );
}

export default function Detalle() {
  const { id: crudo } = useParams();
  const ticketId = idValido(crudo);
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const { user } = useSesion();
  const puede = (permiso) => puedeRol(user, permiso);
  const { avisar } = useAvisos();
  const confirmar = useConfirmar();
  useTitulo("Detalle del ticket");

  const [ticket, setTicket] = useState(null);
  const [cargando, setCargando] = useState(true);
  const [noEncontrado, setNoEncontrado] = useState(ticketId === null
    ? "El identificador del ticket no es válido. Regrese al listado y abra un ticket." : "");
  const [estadoCarga, setEstadoCarga] = useEstadoTexto();
  const [usuarios, setUsuarios] = useState(null); /* null: no se pudieron cargar */
  const [areas, setAreas] = useState([]);
  const [ocupado, setOcupadoEstado] = useState(ticketId === null);
  const ocupadoRef = useRef(ticketId === null);
  const setOcupado = (valor) => { ocupadoRef.current = valor; setOcupadoEstado(valor); };

  const [editando, setEditando] = useState(false);
  const [form, setForm] = useState({ title: "", description: "", category: "Hardware", priority: "Baja" });
  const [asignadoSel, setAsignadoSel] = useState("");
  const [areaSel, setAreaSel] = useState("");
  const [reasignar, setReasignar] = useState(true);
  const [comentarios, setComentarios] = useState([]);
  const [comentariosEstado, setComentariosEstado] = useEstadoTexto();
  const [contenido, setContenido] = useState("");
  const [historial, setHistorial] = useState(null);
  const [historialEstado, setHistorialEstado] = useEstadoTexto();

  const pasos = useRef(null);
  const botonEditar = useRef(null);
  const campoTitulo = useRef(null);
  const campoComentario = useRef(null);
  const fechaImpresion = useRef(null);

  const nombres = new Map((usuarios || []).map((u) => [u.id, u.name]));
  const nombreAsignado = (t) => (t.assigned_to_id === null || t.assigned_to_id === undefined
    ? "—" : nombres.get(t.assigned_to_id) || `Usuario #${t.assigned_to_id}`);
  const nombreSolicitante = (t) => {
    const id = t.created_by_id;
    if (id === null || id === undefined) return "—";
    if (nombres.has(id)) return nombres.get(id);
    if (user && user.id === id && user.name) return user.name;
    return `Usuario #${id}`;
  };

  const cargarTicket = useCallback(async ({ silencioso = false } = {}) => {
    if (!silencioso) setCargando(true);
    try {
      const response = await api(`/api/tickets/${ticketId}`);
      if (response.status === 404) {
        setEstadoCarga("");
        setNoEncontrado(`No existe el ticket #${ticketId} o no tiene acceso a él.`);
        return false;
      }
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const datos = await response.json();
      if (!silencioso) setEstadoCarga("");
      setTicket(datos);
      return true;
    } catch {
      setEstadoCarga(ERROR_API, "error");
      return false;
    } finally {
      setCargando(false);
    }
  }, [ticketId]); // eslint-disable-line react-hooks/exhaustive-deps

  const cargarComentarios = useCallback(async () => {
    setComentariosEstado("Cargando comentarios...", "cargando");
    try {
      const response = await api(`/api/tickets/${ticketId}/comments`);
      if (response.status === 404) {
        setComentariosEstado(await mensajeDeDetalle(response, `No se encontró el ticket #${ticketId}.`), "error");
        return;
      }
      if (!response.ok) {
        setComentariosEstado(`No se pudieron cargar los comentarios (HTTP ${response.status}).`, "error");
        return;
      }
      const lista = await response.json().catch(() => null);
      if (!Array.isArray(lista)) {
        setComentariosEstado("Respuesta inválida del servidor.", "error");
        return;
      }
      setComentarios(lista);
      if (lista.length === 0) setComentariosEstado("Todavía no hay comentarios.", "vacio");
      else setComentariosEstado("");
    } catch {
      setComentariosEstado("No se pudo conectar con el servidor. Verifique que esté en funcionamiento.", "error");
    }
  }, [ticketId]); // eslint-disable-line react-hooks/exhaustive-deps

  const pedirHistorial = async () => {
    setHistorial(null);
    setHistorialEstado("Cargando...", "cargando");
    try {
      const response = await api(`/api/tickets/${ticketId}/history`);
      if (response.status === 404) {
        setHistorialEstado(await mensajeDeDetalle(response, `No se encontró el ticket #${ticketId}.`), "error");
        return;
      }
      if (!response.ok) {
        setHistorialEstado(`No se pudo cargar el historial (HTTP ${response.status}).`, "error");
        return;
      }
      const lista = await response.json();
      if (!Array.isArray(lista) || lista.length === 0) {
        setHistorialEstado("No hay cambios registrados para este ticket.", "vacio");
        return;
      }
      setHistorialEstado("");
      setHistorial(lista);
    } catch {
      setHistorialEstado(ERROR_API, "error");
    }
  };

  /* Usuarios → ticket → departamentos → comentarios, como la pantalla actual. */
  useEffect(() => {
    if (ticketId === null) return undefined;
    let vigente = true;
    (async () => {
      try {
        const response = await api("/api/users");
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const lista = await response.json();
        if (!Array.isArray(lista)) throw new Error("respuesta inválida");
        if (vigente) setUsuarios(lista);
      } catch {
        if (vigente) setUsuarios(null);
      }
      const ok = await cargarTicket();
      if (!vigente || !ok) return;
      if (puedeRol(user, "cambiar_area")) {
        try {
          const response = await api("/api/areas");
          const lista = response.ok ? await response.json() : [];
          if (vigente) setAreas(Array.isArray(lista) ? lista : []);
        } catch {
          if (vigente) setAreas([]);
        }
      }
      if (vigente) await cargarComentarios();
    })();
    return () => { vigente = false; };
  }, [ticketId]); // eslint-disable-line react-hooks/exhaustive-deps

  /* Al cargar (o recargar) el ticket: formulario, asignado y departamento. */
  useEffect(() => {
    if (!ticket) return;
    if (!editando) setForm({ title: ticket.title, description: ticket.description, category: ticket.category, priority: ticket.priority });
    setAsignadoSel(ticket.assigned_to_id === null || ticket.assigned_to_id === undefined ? "" : String(ticket.assigned_to_id));
    if (ticket.area_id) setAreaSel(String(ticket.area_id));
    if (!puedeEditarTicket(user, ticket)) setEditando(false);
  }, [ticket]); // eslint-disable-line react-hooks/exhaustive-deps

  /* Imprimir: fecha en el encabezado y modo claro mientras dura. */
  useEffect(() => {
    let temaAntes = null;
    const antes = () => {
      if (fechaImpresion.current) fechaImpresion.current.textContent = `Impreso el ${formatearFechaHora(new Date().toISOString())}`;
      temaAntes = document.documentElement.getAttribute("data-tema");
      if (temaAntes) document.documentElement.removeAttribute("data-tema");
    };
    const despues = () => {
      if (temaAntes) document.documentElement.setAttribute("data-tema", temaAntes);
      temaAntes = null;
    };
    window.addEventListener("beforeprint", antes);
    window.addEventListener("afterprint", despues);
    return () => {
      window.removeEventListener("beforeprint", antes);
      window.removeEventListener("afterprint", despues);
    };
  }, []);

  /* 403 (sin permiso) o 409 (Cerrado): el motivo y se recarga el ticket. */
  const rechazoDeReglas = async (response, porDefecto) => {
    if (response.status !== 403 && response.status !== 409) return false;
    avisar(await mensajeDeDetalle(response, porDefecto), "error");
    await cargarTicket({ silencioso: true });
    return true;
  };

  /* Ejecuta una acción con los botones bloqueados (una a la vez). */
  const conBloqueo = async (accion) => {
    if (ocupadoRef.current || ticketId === null) return;
    setOcupado(true);
    try {
      await accion();
    } catch {
      avisar(ERROR_API, "error");
    } finally {
      setOcupado(false);
    }
  };

  const activarEdicion = () => {
    if (ocupadoRef.current || !ticket || !puedeEditarTicket(user, ticket)) return;
    setForm({ title: ticket.title, description: ticket.description, category: ticket.category, priority: ticket.priority });
    setEditando(true);
  };
  useLayoutEffect(() => {
    if (editando && campoTitulo.current) campoTitulo.current.focus();
  }, [editando]);

  const salirEdicion = () => {
    setEditando(false);
    setTimeout(() => botonEditar.current && botonEditar.current.focus(), 0);
  };

  const cancelarEdicion = () => {
    if (ocupadoRef.current) return;
    setForm({ title: ticket.title, description: ticket.description, category: ticket.category, priority: ticket.priority });
    salirEdicion();
    avisar("Edición cancelada. Los datos del ticket no se modificaron.");
  };

  const guardarEdicion = (event) => {
    event.preventDefault();
    const payload = { title: form.title.trim(), description: form.description.trim(), category: form.category, priority: form.priority };
    const error = validarTexto(payload);
    if (error) {
      avisar(error, "error");
      return;
    }
    conBloqueo(async () => {
      const response = await api(`/api/tickets/${ticketId}`, { method: "PATCH", body: payload });
      if (response.status === 404) return avisar(`No se encontró el ticket #${ticketId}.`, "error");
      if (await rechazoDeReglas(response, "No tiene permiso para editar este ticket.")) return undefined;
      if (response.status === 422) return avisar(formatValidation(await response.json().catch(() => null)), "error");
      if (!response.ok) return avisar(`No se pudieron guardar los cambios (HTTP ${response.status}).`, "error");
      avisar("Cambios guardados correctamente.", "exito");
      await cargarTicket({ silencioso: true });
      salirEdicion();
      return undefined;
    });
  };

  const eliminar = async () => {
    if (ocupadoRef.current) return;
    const ok = await confirmar({
      titulo: "Eliminar ticket",
      mensaje: `¿Está seguro de que desea eliminar el ticket #${ticketId}? Esta acción no se puede deshacer.`,
      aceptar: "Eliminar",
      peligro: true,
    });
    if (!ok) return;
    let eliminado = false;
    await conBloqueo(async () => {
      setEstadoCarga("Eliminando el ticket...", "cargando");
      let response;
      try {
        response = await api(`/api/tickets/${ticketId}`, { method: "DELETE" });
      } catch (error) {
        setEstadoCarga("");
        throw error;
      }
      if (response.status === 204) {
        eliminado = true;
        return;
      }
      setEstadoCarga("");
      if (response.status === 403) avisar("Solo un Administrador puede eliminar tickets.", "error");
      else if (response.status === 409) await rechazoDeReglas(response, "Un ticket Cerrado no se elimina.");
      else if (response.status === 404) avisar("El ticket ya no existe. Regrese al listado.", "error");
      else avisar(await mensajeDeDetalle(response, "No se pudo eliminar el ticket."), "error");
    });
    if (eliminado) {
      avisoPendiente(`Ticket #${ticketId} eliminado correctamente.`);
      navigate("/");
    }
  };

  const guardarAsignacion = () => {
    if (usuarios === null) {
      avisar("No se pudo cargar la lista de usuarios: recarga la página para intentarlo de nuevo.", "error");
      return;
    }
    if (usuarios.length === 0) {
      avisar("No hay usuarios disponibles. Puede crear uno desde la página de Usuarios.", "error");
      return;
    }
    const assignedToId = asignadoSel === "" ? null : Number(asignadoSel);
    conBloqueo(async () => {
      const response = await api(`/api/tickets/${ticketId}/assign`, { method: "PATCH", body: { assigned_to_id: assignedToId } });
      if (await rechazoDeReglas(response, "No tiene permiso para asignar este ticket.")) return;
      if (response.status === 404) return void avisar(await mensajeDeDetalle(response, `No se encontró el ticket #${ticketId}.`), "error");
      if (response.status === 422) return void avisar(formatValidation(await response.json().catch(() => null)), "error");
      if (!response.ok) return void avisar(`No se pudo guardar la asignación (HTTP ${response.status}).`, "error");
      avisar(assignedToId === null ? "El ticket quedó sin asignar." : "Asignación guardada correctamente.", "exito");
      await cargarTicket({ silencioso: true });
    });
  };

  const cambiarArea = () => {
    if (ticket && ticket.state !== "Nuevo") {
      avisar("El departamento solo se puede cambiar mientras el ticket está en Nuevo.", "error");
      return;
    }
    if (!/^\d+$/.test(areaSel)) {
      avisar("Elija el departamento al que pasa el ticket.", "error");
      return;
    }
    conBloqueo(async () => {
      const response = await api(`/api/tickets/${ticketId}/area`, { method: "PATCH", body: { area_id: Number(areaSel), reasignar } });
      if (await rechazoDeReglas(response, "No tiene permiso para cambiar el departamento de este ticket.")) return;
      if (!response.ok) {
        avisar(await mensajeDeDetalle(response, `No se pudo cambiar el departamento (HTTP ${response.status}).`), "error");
        return;
      }
      const nuevo = await response.json();
      const quien = nuevo.assigned_to_id ? nombres.get(nuevo.assigned_to_id) : null;
      avisar(reasignar && quien
        ? `El ticket pasó al departamento «${nuevo.area_name}» y quedó asignado a ${quien}.`
        : `El ticket pasó al departamento «${nuevo.area_name}».`, "exito");
      await cargarTicket({ silencioso: true });
    });
  };

  /* Un paso del recorrido: confirmación con motivo opcional (queda como
     comentario) y el cambio de estado. */
  const pedirCambioEstado = async (destino) => {
    if (ocupadoRef.current || !destino) return;
    const respuesta = await confirmar({
      titulo: "Cambiar estado",
      mensaje: destino === "Cerrado"
        ? `¿Pasar el ticket #${ticketId} a «Cerrado»? Un ticket Cerrado ya no se puede reabrir.`
        : `¿Pasar el ticket #${ticketId} a «${destino}»?`,
      aceptar: "Confirmar",
      cancelar: "Cancelar",
      campo: { etiqueta: "Motivo (opcional)" },
    });
    if (!respuesta) return;
    const motivo = (respuesta.valor || "").trim();
    let recargarHistorial = false;
    await conBloqueo(async () => {
      const response = await api(`/api/tickets/${ticketId}/state`, { method: "PATCH", body: motivo ? { state: destino, motivo } : { state: destino } });
      if (response.status === 404) return void avisar(await mensajeDeDetalle(response, `No se encontró el ticket #${ticketId}.`), "error");
      if (response.status === 409) {
        avisar(await mensajeDeDetalle(response, "La transición de estado no está permitida."), "error");
        await cargarTicket({ silencioso: true });
        return undefined;
      }
      if (response.status === 422) return void avisar(formatValidation(await response.json().catch(() => null)), "error");
      if (!response.ok) return void avisar(`No se pudo cambiar el estado (HTTP ${response.status}).`, "error");
      avisar(`Estado actualizado a «${destino}».`, "exito");
      await cargarTicket({ silencioso: true });
      if (motivo) await cargarComentarios();
      recargarHistorial = historial !== null;
      return undefined;
    });
    if (recargarHistorial) await conBloqueo(pedirHistorial);
    if (pasos.current) pasos.current.focus();
  };

  const ajustarAlto = () => {
    const campo = campoComentario.current;
    if (!campo) return;
    /* CSSOM (no un atributo style): la CSP lo permite. */
    campo.style.height = "";
    if (!campo.value) return;
    campo.style.height = `${Math.min(campo.scrollHeight + 2, ALTO_MAXIMO_COMENTARIO)}px`;
  };
  useLayoutEffect(ajustarAlto, [contenido]);

  const agregarComentario = (event) => {
    event.preventDefault();
    const content = contenido.trim();
    if (!content) {
      avisar("El comentario no puede estar vacío.", "error");
      return;
    }
    conBloqueo(async () => {
      const response = await api(`/api/tickets/${ticketId}/comments`, { method: "POST", body: { content } });
      if (await rechazoDeReglas(response, "No se puede comentar este ticket.")) return;
      if (response.status === 404) return void avisar(await mensajeDeDetalle(response, `No se encontró el ticket #${ticketId}.`), "error");
      if (response.status === 422) return void avisar(formatValidation(await response.json().catch(() => null)), "error");
      if (!response.ok) return void avisar(`No se pudo agregar el comentario (HTTP ${response.status}).`, "error");
      setContenido("");
      avisar("Comentario agregado correctamente.", "exito");
      await cargarComentarios();
    });
  };

  /* Pestañas: solo las del rol; ?pestana=ia (enlace del chat) o la última. */
  const pestanas = [
    ["comentarios", "Comentarios", "seccion-comentarios"],
    ["historial", "Historial", "seccion-historial"],
    ...(puede("explicar_ia") ? [["ia", "Explicación IA", "seccion-ia"]] : []),
  ];
  const [pestana, setPestanaEstado] = useState(() => {
    let elegida = params.get("pestana");
    if (!elegida) {
      try {
        elegida = localStorage.getItem(PESTANA_KEY);
      } catch {
        elegida = null;
      }
    }
    return elegida;
  });
  const activa = (pestanas.find(([clave]) => clave === pestana) || pestanas[0])[0];
  const refsPestanas = useRef({});
  const elegirPestana = (clave, { enfocar = false } = {}) => {
    setPestanaEstado(clave);
    try {
      localStorage.setItem(PESTANA_KEY, clave);
    } catch {
      /* Solo no se recuerda. */
    }
    if (enfocar && refsPestanas.current[clave]) refsPestanas.current[clave].focus();
  };
  useEffect(() => {
    try {
      localStorage.setItem(PESTANA_KEY, activa);
    } catch {
      /* Solo no se recuerda. */
    }
  }, [activa]);

  const cerrado = ticketCerrado(ticket);
  const destinos = ticket && puedeCambiarEstado(user, ticket) ? TRANSICIONES[ticket.state] || [] : [];
  const cierreCuando = ticket && ticket.state === "Resuelto" && ticket.cierre_automatico_en
    ? fechaCierreAutomatico(ticket.cierre_automatico_en) : "";
  const puedeEditar = Boolean(ticket) && puedeEditarTicket(user, ticket);
  const usuariosIT = (usuarios || []).filter((u) => !u.role || ROLES_IT.includes(u.role));
  const asignadoFuera = ticket && usuarios && usuarios.length > 0 && ticket.assigned_to_id !== null && ticket.assigned_to_id !== undefined
    && !usuariosIT.some((u) => u.id === ticket.assigned_to_id) ? ticket.assigned_to_id : null;
  const deshabilitado = ocupado;

  return (
    <>
      <Cabecera claseTitulo="" titulo="Detalle del ticket" subtitulo="Consulta y gestión del ticket"
        migas={<Migas actual={ticketId !== null ? `Ticket #${ticketId}` : "Ticket"} />}
        acciones={<Link to="/" className="enlace-boton secundario">Volver al listado</Link>} />

      <main className="contenido">
        <div className="impresion-cabecera" aria-hidden="true">
          <div>
            <strong>American Data Networks</strong>
            <span>Sistema de tickets · Ficha del ticket</span>
          </div>
          <span id="impresion-fecha" ref={fechaImpresion} />
        </div>
        <Estado id="estado-carga" estado={noEncontrado ? null : estadoCarga} />

        <section id="ticket-no-encontrado" className="pagina-error-tarjeta en-pagina" hidden={!noEncontrado}>
          <span className="pagina-error-icono icono-buscar" aria-hidden="true" />
          <h2>Ticket no encontrado</h2>
          <p className="pagina-error-mensaje" id="ticket-no-encontrado-mensaje">{noEncontrado}</p>
          <div className="acciones">
            <Link to="/" className="enlace-boton">Volver al listado</Link>
          </div>
        </section>

        <div className="detalle-layout" id="detalle-layout" hidden={Boolean(noEncontrado)}>
          <div className="detalle-principal">
            <div className="acciones acciones-principales">
              <button type="button" id="editar" ref={botonEditar} hidden={!puedeEditar || editando} disabled={deshabilitado}
                onClick={activarEdicion}>Editar ticket</button>
              <button type="button" id="imprimir" className="secundario" onClick={() => window.print()}>Imprimir</button>
              <button type="button" id="eliminar" className="peligro accion-aparte" hidden={!puede("eliminar") || !ticket || cerrado}
                disabled={deshabilitado} onClick={eliminar}>Eliminar</button>
            </div>

            <section id="panel-ticket" className={`tarjeta-ticket${cargando ? " esqueleto-activo" : ""}`}
              aria-label="Datos del ticket" aria-busy={cargando ? "true" : "false"}>
              <div className="tarjeta-ticket-cabecera">
                <div className="tarjeta-ticket-titulos">
                  <span className="tarjeta-ticket-id">#<span id="ver-id">{ticket ? ticket.id : "—"}</span></span>
                  <h2 id="ver-title" className="tarjeta-ticket-titulo">{ticket ? ticket.title : "—"}</h2>
                </div>
                <div className="tarjeta-ticket-etiquetas">
                  <span id="ver-state" className={ticket ? claseBadge(ticket.state) : undefined}>{ticket ? ticket.state : "—"}</span>
                  <span id="ver-priority" className={ticket ? claseBadge(ticket.priority) : undefined}>{ticket ? ticket.priority : "—"}</span>
                </div>
              </div>
              <PasosEstado ref={pasos} estado={ticket ? ticket.state : null} destinos={destinos} onElegir={pedirCambioEstado} />
              <p id="pasos-nota" className="pasos-nota" hidden={destinos.length === 0}>Toque un estado para cambiarlo.</p>
              <p id="estado-final" className="pasos-nota" hidden={!cerrado}>
                Este ticket está <b>Cerrado</b> y no admite cambios.
              </p>
              <p id="cierre-automatico" className="pasos-nota cierre-automatico" hidden={!cierreCuando}>
                {cierreCuando ? `Se cerrará automáticamente el ${cierreCuando} si no hay respuesta.` : ""}
              </p>
              <h3 className="tarjeta-ticket-subtitulo">Descripción</h3>
              <p id="ver-description" className="tarjeta-ticket-descripcion">{ticket ? ticket.description : "—"}</p>
            </section>

            {ticketId !== null && <SeccionAdjuntos ticketId={ticketId} estadoTicket={ticket ? ticket.state : null} />}

            <section id="seccion-edicion" className="seccion" aria-label="Edición del ticket" hidden={!editando || !puedeEditar}>
              <h2>Editar ticket</h2>
              <p className="nota" id="modo-edicion">
                <b>Editando ticket.</b> Los cambios solo se aplican al pulsar
                «Guardar cambios»; «Cancelar» descarta lo escrito y vuelve a la
                consulta del ticket.
              </p>
              <form id="form-editar" className="filtros formulario" noValidate onSubmit={guardarEdicion}>
                <label className="campo">
                  <span>Título *</span>
                  <input type="text" id="title" name="title" required maxLength={200} ref={campoTitulo}
                    value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
                </label>
                <label className="campo">
                  <span>Descripción *</span>
                  <textarea id="description" name="description" required
                    value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
                </label>
                <label className="campo">
                  <span>Categoría</span>
                  <select id="category" name="category" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>
                    {CATEGORIAS.map((c) => <option key={c} value={c}>{c}</option>)}
                  </select>
                </label>
                <label className="campo">
                  <span>Prioridad</span>
                  <select id="priority" name="priority" value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value })}>
                    {PRIORIDADES.map((p) => <option key={p} value={p}>{p}</option>)}
                  </select>
                </label>
                <div className="acciones">
                  <button type="submit" id="guardar" disabled={deshabilitado}>Guardar cambios</button>
                  <button type="button" id="cancelar-edicion" className="secundario" disabled={deshabilitado} onClick={cancelarEdicion}>Cancelar</button>
                </div>
              </form>
            </section>

            <div className="pestanas" id="pestanas-detalle">
              <div className="pestanas-lista" role="tablist" aria-label="Secciones del ticket">
                {pestanas.map(([clave, texto, panel], indice) => (
                  <button key={clave} type="button" role="tab" className="pestana" id={`pestana-${clave}`} data-pestana={clave}
                    aria-controls={panel} aria-selected={String(activa === clave)} tabIndex={activa === clave ? 0 : -1}
                    ref={(el) => { refsPestanas.current[clave] = el; }}
                    onClick={() => elegirPestana(clave)}
                    onKeyDown={(event) => {
                      const paso = { ArrowRight: 1, ArrowLeft: -1 }[event.key];
                      if (!paso) return;
                      event.preventDefault();
                      elegirPestana(pestanas[(indice + paso + pestanas.length) % pestanas.length][0], { enfocar: true });
                    }}>{texto}</button>
                ))}
                {!puede("explicar_ia") && (
                  <button type="button" role="tab" className="pestana" id="pestana-ia" data-pestana="ia" aria-controls="seccion-ia"
                    aria-selected="false" tabIndex={-1} hidden>Explicación IA</button>
                )}
              </div>

              <section id="seccion-comentarios" className="seccion pestana-panel" role="tabpanel" aria-labelledby="pestana-comentarios"
                hidden={activa !== "comentarios"}>
                <h2>Comentarios</h2>
                <Estado id="comentarios-estado" estado={comentariosEstado} />
                {!comentariosEstado && comentarios.length > 0 && <Conversacion comentarios={comentarios} />}
                <form id="form-comentario" className="filtros formulario" noValidate hidden={cerrado} onSubmit={agregarComentario}>
                  <label className="campo">
                    <span>Nuevo comentario</span>
                    <textarea id="contenido" name="content" rows={3} maxLength={2000} placeholder="Escriba aquí el comentario"
                      ref={campoComentario} value={contenido} onChange={(e) => setContenido(e.target.value)} />
                  </label>
                  <div className="acciones">
                    <button type="submit" id="comentar" disabled={deshabilitado}>Agregar comentario</button>
                  </div>
                </form>
              </section>

              <section id="seccion-historial" className="seccion pestana-panel" role="tabpanel" aria-labelledby="pestana-historial"
                hidden={activa !== "historial"}>
                <h2>Historial de cambios</h2>
                <div className="acciones">
                  <button type="button" id="historial" disabled={deshabilitado} onClick={() => conBloqueo(pedirHistorial)}>Ver historial</button>
                </div>
                <Estado id="historial-estado" estado={historialEstado} />
                <table className="listado" id="tabla-historial" hidden={!historial}>
                  <thead>
                    <tr><th>Fecha y hora</th><th>Persona</th><th>Acción</th><th>Detalle</th></tr>
                  </thead>
                  <tbody id="historial-cuerpo">
                    {(historial || []).map((entrada, i) => {
                      const { accion, detalle } = describirHistorial(entrada);
                      return (
                        <tr key={entrada.id ?? i}>
                          <td>{formatearFechaHora(entrada.created_at)}</td>
                          <td>{autorHistorial(entrada)}</td>
                          <td>{accion}</td>
                          <td>{detalle}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </section>

              <ExplicacionIA ticketId={ticketId} permitida={puede("explicar_ia") && ticketId !== null} oculta={activa !== "ia"} />
            </div>
          </div>

          <aside className="detalle-lateral" aria-label="Datos y acciones del ticket">
            <section id="panel-datos" className="seccion detalle-datos" aria-label="Detalles del ticket">
              <h2>Detalles</h2>
              <div className="ficha-datos">
                <div className="ficha-grupo" role="group" aria-labelledby="ficha-clasificacion">
                  <h3 id="ficha-clasificacion" className="ficha-titulo">Clasificación</h3>
                  <dl className="detalle-datos-lista">
                    <Dato etiqueta="Categoría"><dd id="ver-category">{ticket ? ticket.category : "—"}</dd></Dato>
                    <Dato etiqueta="Departamento"><dd id="ver-area">{ticket ? ticket.area_name || SIN_AREA : "—"}</dd></Dato>
                  </dl>
                </div>
                <div className="ficha-grupo" role="group" aria-labelledby="ficha-personas">
                  <h3 id="ficha-personas" className="ficha-titulo">Personas</h3>
                  <dl className="detalle-datos-lista">
                    <Dato etiqueta="Asignado a">
                      {ticket ? <PersonaFicha id="ver-assigned" nombre={nombreAsignado(ticket)} /> : <dd id="ver-assigned">—</dd>}
                    </Dato>
                    <Dato etiqueta="Solicitante">
                      {ticket ? <PersonaFicha id="ver-creator" nombre={nombreSolicitante(ticket)} /> : <dd id="ver-creator">—</dd>}
                    </Dato>
                  </dl>
                </div>
                <div className="ficha-grupo" role="group" aria-labelledby="ficha-fechas">
                  <h3 id="ficha-fechas" className="ficha-titulo">Fechas</h3>
                  <dl className="detalle-datos-lista">
                    <Dato etiqueta="Creado"><dd id="ver-created">{ticket ? formatearFechaHora(ticket.created_at) : "—"}</dd></Dato>
                    <Dato etiqueta="Actualizado"><dd id="ver-updated">{ticket ? formatearFechaHora(ticket.updated_at) : "—"}</dd></Dato>
                  </dl>
                </div>
              </div>
            </section>

            {(
              <section id="seccion-asignacion" className="seccion" aria-label="Asignación del ticket" hidden={!puede("asignar") || cerrado}>
                <h2>Asignación</h2>
                <div className="filtros formulario">
                  <label className="campo">
                    <span>Persona asignada</span>
                    <select id="usuario" value={usuarios === null ? "" : asignadoSel} disabled={!usuarios || usuarios.length === 0}
                      onChange={(e) => setAsignadoSel(e.target.value)}>
                      {usuarios === null ? (
                        <option value="">No se pudo cargar la lista de usuarios</option>
                      ) : (
                        <>
                          <option value="">Sin asignar</option>
                          {usuarios.length > 0 && usuariosIT.map((u) => (
                            <option key={u.id} value={String(u.id)}>{u.area_name ? `${u.name} · ${u.area_name}` : u.name}</option>
                          ))}
                          {asignadoFuera !== null && (
                            <option value={String(asignadoFuera)} disabled>
                              {`${nombres.get(asignadoFuera) || `Usuario #${asignadoFuera}`} (Solicitante: reasígnelo)`}
                            </option>
                          )}
                        </>
                      )}
                    </select>
                  </label>
                  <div className="acciones">
                    <button type="button" id="asignar" disabled={deshabilitado} onClick={guardarAsignacion}>Guardar asignación</button>
                  </div>
                </div>
                <p id="usuarios-nota" className="nota" hidden={!(usuarios && usuarios.length === 0)}>
                  No hay usuarios disponibles. Puede crear uno desde <Link to="/usuarios">Usuarios</Link>.
                </p>
              </section>
            )}

            {(
              <section id="seccion-area" className="seccion" aria-label="Departamento del ticket"
                hidden={!puede("cambiar_area") || !ticket || ticket.state !== "Nuevo"}>
                <h2>Cambiar departamento</h2>
                <div className="filtros formulario">
                  <label className="campo">
                    <span>Nuevo departamento</span>
                    <select id="area-destino" value={areaSel} onChange={(e) => setAreaSel(e.target.value)}>
                      <option value="">{areas.length || ticket ? "Elija un departamento" : "Cargando departamentos…"}</option>
                      {areas.map((a) => <option key={a.id} value={String(a.id)}>{a.name}</option>)}
                    </select>
                  </label>
                  <label className="casilla">
                    <input type="checkbox" id="area-reasignar" checked={reasignar} onChange={(e) => setReasignar(e.target.checked)} />
                    <span>Reasignar al técnico del nuevo departamento con menos tickets abiertos</span>
                  </label>
                  <div className="acciones">
                    <button type="button" id="cambiar-area" disabled={deshabilitado} onClick={cambiarArea}>Cambiar departamento</button>
                  </div>
                </div>
              </section>
            )}
          </aside>
        </div>
      </main>
    </>
  );
}
