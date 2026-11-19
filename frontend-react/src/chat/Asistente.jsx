/* Asistente virtual (port de frontend/js/asistente.js): botón flotante y
   ventana de chat en todas las pantallas con sesión. Envía la conversación
   a POST /api/asistente/stream; el servidor decide qué datos usar según el
   rol y responde por partes (NDJSON). La conversación vive en sessionStorage
   (la misma clave que la app actual). En el detalle de un ticket se manda su
   número para preguntar por «este ticket». */
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { matchPath, useLocation } from "react-router-dom";
import { api } from "../api/cliente.js";
import { useSesion } from "../contexto/SesionContext.jsx";
import { formatearFechaHora } from "../sesion/permisos.js";
import { RUTAS } from "../rutas.js";
import { Texto, textoParaCopiar } from "./formato.jsx";

const CHAT_KEY = "asistente_chat";
const CHAT_GRANDE_KEY = "asistente_grande";
const CHAT_MAX_MENSAJES = 20;
export const IA_NO_DISPONIBLE = "La IA no está disponible en este momento";
const CHAT_LIMITE_MS = 200000;
const AVISO_LENTO_MS = 8000;
const SALUDO = "Buen día. ¿En qué le puedo ayudar? Puede consultar, por ejemplo:";
const SUGERENCIAS_EQUIPO = ["¿Cuántos tickets pendientes hay?", "¿Qué tickets tengo asignados?", "Explique el ticket #1"];
const SUGERENCIAS_POR_ROL = {
  Administrador: SUGERENCIAS_EQUIPO,
  Técnico: SUGERENCIAS_EQUIPO,
  Solicitante: ["¿Cómo va mi solicitud?", "¿Cómo creo un ticket?", "¿Cuántos tickets tengo abiertos?"],
};

export function leerChat() {
  try {
    const guardado = JSON.parse(sessionStorage.getItem(CHAT_KEY) || "[]");
    return Array.isArray(guardado) ? guardado : [];
  } catch {
    return [];
  }
}

function guardarChat(mensajes) {
  try {
    sessionStorage.setItem(CHAT_KEY, JSON.stringify(mensajes));
  } catch {
    /* Solo vive en esta pantalla. */
  }
}

/* Como mucho 20 mensajes que empiezan por user; solo role y content. */
export function recortarConversacion(mensajes) {
  let recorte = mensajes.slice(-CHAT_MAX_MENSAJES);
  while (recorte.length && recorte[0].role !== "user") recorte = recorte.slice(1);
  return recorte.map((m) => ({ role: m.role, content: m.content }));
}

/* Íconos de trazo (los mismos SVG). */
const TRAZOS = {
  cerrar: <path d="M6 6l12 12M18 6L6 18" />,
  nueva: <><path d="M3 12a9 9 0 1 0 3-6.7L3 8" /><path d="M3 3v5h5" /></>,
  enviar: <><path d="M5 12h14" /><path d="M13 6l6 6-6 6" /></>,
  expandir: <><path d="M14 4h6v6" /><path d="M20 4l-7 7" /><path d="M10 20H4v-6" /><path d="M4 20l7-7" /></>,
  contraer: <><path d="M20 4l-6 6" /><path d="M14 4v6h6" /><path d="M4 20l6-6" /><path d="M10 20v-6H4" /></>,
  copiar: <><rect x="9" y="9" width="11" height="11" rx="2" /><path d="M5 15V6a2 2 0 0 1 2-2h9" /></>,
  abajo: <><path d="M12 5v14" /><path d="M6 13l6 6 6-6" /></>,
};
const Icono = ({ nombre, clase = "chat-svg" }) => <svg className={clase} viewBox="0 0 24 24" aria-hidden="true">{TRAZOS[nombre]}</svg>;
const Conversacion = ({ clase }) => (
  <svg className={`${clase} icono-conversacion`} viewBox="0 0 24 24" aria-hidden="true">
    <path className="conv-fondo" d="M10 8h10a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2h-1v3l-4-3h-5a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2z" />
    <path className="conv-frente" d="M3 2h11a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2H8l-4 3v-3H3a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2z" />
    <path className="conv-lineas" d="M5 6h7M5 9h4" />
  </svg>
);

function horaDe(mensaje) {
  const hora = mensaje.hora ? formatearFechaHora(mensaje.hora, { parte: "hora" }) : "—";
  return hora === "—" ? null : hora;
}

function Copiar({ contenido }) {
  const [copiado, setCopiado] = useState(false);
  const reloj = useRef(null);
  useEffect(() => () => clearTimeout(reloj.current), []);
  return (
    <button type="button" className={`chat-copiar${copiado ? " copiado" : ""}`} title="Copiar" aria-label="Copiar respuesta"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(textoParaCopiar(contenido));
        } catch {
          return;
        }
        setCopiado(true);
        clearTimeout(reloj.current);
        reloj.current = setTimeout(() => setCopiado(false), 1000);
      }}>
      <Icono nombre="copiar" />
      <span className="chat-copiado" hidden={!copiado}>Copiado</span>
    </button>
  );
}

function Pie({ mensaje, copiable }) {
  const hora = horaDe(mensaje);
  if (!hora && !copiable) return null;
  return (
    <div className="chat-pie">
      {hora && <time className="chat-hora" dateTime={mensaje.hora}>{hora}</time>}
      {copiable && <Copiar contenido={mensaje.content} />}
    </div>
  );
}

function Burbuja({ mensaje }) {
  if (mensaje.role === "user") {
    return (
      <div className="chat-fila usuario">
        <div className="chat-contenido">
          <div className="chat-mensaje usuario">{mensaje.content}</div>
          <Pie mensaje={mensaje} />
        </div>
      </div>
    );
  }
  return (
    <div className="chat-fila asistente">
      <div className="chat-contenido">
        <div className={`chat-mensaje asistente${mensaje.error ? " error" : " chat-formato"}`}>
          {mensaje.error ? mensaje.content : <Texto texto={mensaje.content} />}
        </div>
        <Pie mensaje={mensaje} copiable={!mensaje.error && !mensaje.saludo} />
      </div>
    </div>
  );
}

function Separador({ mensajes }) {
  const primera = mensajes.find((m) => m.hora);
  const fecha = primera ? new Date(primera.hora) : new Date();
  const dia = (d) => formatearFechaHora(d, { parte: "fecha" });
  const ahora = new Date();
  let texto = dia(fecha);
  if (texto === "—" || texto === dia(ahora)) texto = "Hoy";
  else if (texto === dia(new Date(ahora.getTime() - 86400000))) texto = "Ayer";
  return <div className="chat-separador" role="separator" aria-label={texto}><span>{texto}</span></div>;
}

export default function Asistente() {
  const { token, user } = useSesion();
  const location = useLocation();
  const [abierto, setAbierto] = useState(false);
  const [grande, setGrande] = useState(() => {
    try {
      return localStorage.getItem(CHAT_GRANDE_KEY) === "1";
    } catch {
      return false;
    }
  });
  const [mensajes, setMensajes] = useState(leerChat);
  const [pendiente, setPendiente] = useState(null); /* { texto, lento } mientras responde */
  const [entrada, setEntrada] = useState("");
  const [seguirAbajo, setSeguirAbajo] = useState(true);
  const [irFinal, setIrFinal] = useState(false);
  const abiertoRef = useRef(false);
  abiertoRef.current = abierto;
  const ocupado = useRef(false);
  const lista = useRef(null);
  const campo = useRef(null);
  const coincide = matchPath(RUTAS.ticket, location.pathname);
  const idEnPantalla = coincide && /^\d+$/.test(coincide.params.id) && Number(coincide.params.id) > 0 ? Number(coincide.params.id) : null;

  /* Al ir a otra pantalla se cierra, como al cambiar de página en la app actual. */
  useEffect(() => { setAbierto(false); }, [location.pathname]);

  const alternar = useCallback((mostrar) => {
    if (mostrar === abiertoRef.current) return;
    if (mostrar) {
      setSeguirAbajo(true);
      setIrFinal(false);
      setMensajes(leerChat());
    }
    setAbierto(mostrar);
  }, []);

  useEffect(() => {
    if (!abierto) return undefined;
    if (campo.current) campo.current.focus();
    const tecla = (event) => { if (event.key === "Escape") alternar(false); };
    document.addEventListener("keydown", tecla);
    return () => document.removeEventListener("keydown", tecla);
  }, [abierto, alternar]);

  /* Lo nuevo baja la conversación; si el usuario subió a leer, no lo mueve y
     aparece «Ir al final». */
  useLayoutEffect(() => {
    if (!abierto || !lista.current) return;
    if (seguirAbajo) {
      lista.current.scrollTop = lista.current.scrollHeight;
      setIrFinal(false);
    } else {
      setIrFinal(true);
    }
  }, [abierto, mensajes, pendiente]); // eslint-disable-line react-hooks/exhaustive-deps

  /* El campo crece con el texto hasta 120 px (CSSOM, no un atributo style). */
  useLayoutEffect(() => {
    const el = campo.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 120)}px`;
  }, [entrada, abierto]);

  const cambiarGrande = () => {
    setGrande((g) => {
      try {
        localStorage.setItem(CHAT_GRANDE_KEY, g ? "0" : "1");
      } catch {
        /* Solo para esta pantalla. */
      }
      return !g;
    });
  };

  const enviar = async (texto) => {
    const pregunta = String(texto || "").trim();
    if (!pregunta || ocupado.current) return;
    ocupado.current = true;
    setSeguirAbajo(true);
    setIrFinal(false);
    /* Los avisos de error se muestran pero no se envían a la API. */
    const historial = leerChat().filter((m) => !m.error);
    historial.push({ role: "user", content: pregunta, hora: new Date().toISOString() });
    guardarChat(historial);
    setMensajes(historial);
    setEntrada("");
    setPendiente({ texto: "", lento: false });
    const aviso = setTimeout(() => setPendiente((p) => (p && !p.texto ? { ...p, lento: true } : p)), AVISO_LENTO_MS);

    let respuesta;
    let acumulado = "";
    let fuente = "";
    const control = new AbortController();
    const limite = setTimeout(() => control.abort(), CHAT_LIMITE_MS);
    try {
      const cuerpo = { messages: recortarConversacion(historial) };
      if (idEnPantalla !== null) cuerpo.ticket_id = idEnPantalla;
      const response = await api("/api/asistente/stream", { method: "POST", body: cuerpo, signal: control.signal });
      if (!response.ok || !response.body) {
        const body = await response.json().catch(() => null);
        const detalle = body && typeof body.detail === "string" ? body.detail : "";
        respuesta = { role: "assistant", error: true, content: detalle || `El asistente no pudo responder (${response.status}).` };
      } else {
        const lector = response.body.getReader();
        const decodificador = new TextDecoder();
        let resto = "";
        let error = "";
        for (;;) {
          const { value, done } = await lector.read();
          if (done) break;
          resto += decodificador.decode(value, { stream: true });
          const lineas = resto.split("\n");
          resto = lineas.pop();
          for (const l of lineas) {
            if (!l.trim()) continue;
            const evento = JSON.parse(l);
            if (typeof evento.t === "string") {
              acumulado += evento.t;
              clearTimeout(aviso);
              setPendiente({ texto: acumulado, lento: false });
            } else if (typeof evento.reemplazo === "string") {
              /* La respuesta de la IA no servía: se cambia por la del sistema. */
              acumulado = evento.reemplazo;
              setPendiente({ texto: acumulado, lento: false });
            } else if (evento.error) {
              error = evento.error;
            } else if (evento.fin) {
              fuente = evento.fuente || "";
            }
          }
        }
        respuesta = error || !acumulado
          ? { role: "assistant", error: true, content: error || IA_NO_DISPONIBLE }
          : { role: "assistant", content: acumulado, fuente };
      }
    } catch (error) {
      respuesta = {
        role: "assistant",
        error: true,
        content: error && error.name === "AbortError" ? IA_NO_DISPONIBLE : "No se pudo conectar con el servidor. Verifique que esté en funcionamiento.",
      };
    }
    clearTimeout(aviso);
    clearTimeout(limite);
    respuesta.hora = new Date().toISOString();
    /* Si falló, la pregunta se quita del historial para poder reintentarla. */
    const actualizado = respuesta.error ? historial.slice(0, -1) : historial;
    guardarChat([...actualizado, respuesta]);
    setMensajes([...historial, respuesta]);
    setPendiente(null);
    ocupado.current = false;
    if (campo.current) campo.current.focus();
  };

  if (!token) return null;
  const textoGrande = grande ? "Achicar ventana" : "Agrandar ventana";
  const sugerencias = SUGERENCIAS_POR_ROL[user && user.role] || [];

  return createPortal(
    <div className={`chat-asistente${grande ? " grande" : ""}${abierto ? " abierto" : ""}`} id="chat-asistente">
      <section className="chat-panel" id="chat-panel" hidden={!abierto} aria-label="Asistente virtual">
        <header className="chat-cabecera">
          <div className="chat-identidad">
            <span className="chat-cabecera-icono"><Conversacion clase="chat-svg" /></span>
            <div>
              <strong className="chat-titulo">Asistente virtual</strong>
              <span className="chat-subtitulo" title={user && user.role ? `Respuestas según su rol: ${user.role}` : "Respuestas según su rol"}>
                <span className="chat-punto-en-linea" />En línea
              </span>
            </div>
          </div>
          <div className="chat-acciones">
            <button type="button" className="chat-icono chat-agrandar" title={textoGrande} aria-label={textoGrande} aria-pressed={String(grande)}
              onClick={cambiarGrande}><Icono nombre={grande ? "contraer" : "expandir"} /></button>
            <button type="button" className="chat-icono" title="Nueva conversación" aria-label="Nueva conversación"
              onClick={() => { guardarChat([]); setMensajes([]); if (campo.current) campo.current.focus(); }}><Icono nombre="nueva" /></button>
            <button type="button" className="chat-icono" title="Cerrar" aria-label="Cerrar asistente" onClick={() => alternar(false)}>
              <Icono nombre="cerrar" />
            </button>
          </div>
        </header>
        <div className="chat-cuerpo">
          <div className="chat-lista" id="chat-lista" aria-live="polite" ref={lista}
            onScroll={(e) => {
              const el = e.currentTarget;
              const abajo = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
              setSeguirAbajo(abajo);
              if (abajo) setIrFinal(false);
            }}>
            {abierto && (
              <>
                <Separador mensajes={mensajes} />
                {mensajes.length === 0 && (
                  <>
                    <Burbuja mensaje={{ role: "assistant", content: SALUDO, saludo: true }} />
                    <div className="chat-sugerencias">
                      {sugerencias.map((s) => <button key={s} type="button" className="chat-sugerencia" onClick={() => enviar(s)}>{s}</button>)}
                    </div>
                  </>
                )}
                {mensajes.map((m, i) => <Burbuja key={`${m.hora || ""}-${i}`} mensaje={m} />)}
                {pendiente && (
                  <div className="chat-fila asistente">
                    <div className="chat-contenido">
                      {pendiente.texto
                        ? <div className="chat-mensaje asistente chat-formato"><Texto texto={pendiente.texto} /></div>
                        : <div className="chat-mensaje asistente escribiendo">Escribiendo…</div>}
                      {pendiente.lento && !pendiente.texto && (
                        <span className="chat-nota">La primera respuesta puede tardar hasta un minuto. Gracias por su paciencia.</span>
                      )}
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
          <button type="button" className="chat-ir-final" id="chat-ir-final" hidden={!irFinal} title="Ir al final" aria-label="Ir al final"
            onClick={() => {
              setSeguirAbajo(true);
              setIrFinal(false);
              if (lista.current) lista.current.scrollTop = lista.current.scrollHeight;
            }}><Icono nombre="abajo" /></button>
        </div>
        <form className="chat-formulario" onSubmit={(e) => { e.preventDefault(); enviar(entrada); }}>
          <div className="chat-caja">
            <textarea className="chat-entrada" id="chat-entrada" rows={1} maxLength={2000} placeholder="Ingrese su consulta…" aria-label="Su consulta"
              ref={campo} value={entrada} onChange={(e) => setEntrada(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  enviar(entrada);
                }
              }} />
            <button type="submit" className="chat-enviar" id="chat-enviar" disabled={Boolean(pendiente) || !entrada.trim()} aria-label="Enviar">
              <Icono nombre="enviar" />
            </button>
          </div>
        </form>
      </section>
      <button type="button" className="chat-boton" aria-expanded={String(abierto)}
        aria-label={abierto ? "Cerrar asistente virtual" : "Abrir asistente virtual"} data-tooltip={abierto ? "Cerrar" : "Asistente virtual"}
        onClick={() => alternar(!abierto)}>
        <Conversacion clase="chat-boton-icono icono-chat" />
        <Icono nombre="cerrar" clase="chat-boton-icono icono-cerrar" />
      </button>
    </div>,
    document.body,
  );
}
