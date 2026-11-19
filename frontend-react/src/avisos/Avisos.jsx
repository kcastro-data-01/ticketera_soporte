/* Avisos flotantes (port de frontend/js/avisos.js): el resultado de una
   acción. Una sola función para toda la app:

     const { avisar } = useAvisos();
     avisar("Comentario agregado correctamente.");          // éxito
     avisar("No se pudo guardar el comentario.", "error");  // error

   Mismas clases y reglas: arriba a la derecha debajo de la .cabecera, éxito
   verde que se va a los 4 s (pausa con mouse o foco encima), error rojo que
   queda hasta cerrarlo, ✕ o Escape, máximo 4, el mismo aviso seguido no se
   repite, aria-live y role="alert" en los errores. avisoPendiente() deja un
   aviso para la pantalla siguiente (la misma clave que la app actual). */
import { createContext, useCallback, useContext, useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useLocation } from "react-router-dom";

const AVISO_EXITO_MS = 4000;
const AVISO_SALIDA_MS = 200;
const AVISOS_MAXIMO = 4;
const AVISOS_MARGEN_PX = 12;
export const AVISO_PENDIENTE_KEY = "aviso_pendiente";

const AvisosContext = createContext({ avisar: () => {} });

export function avisoPendiente(texto, tipo = "exito") {
  try {
    sessionStorage.setItem(AVISO_PENDIENTE_KEY, JSON.stringify({ texto, tipo }));
  } catch {
    /* Sin sessionStorage el aviso no se muestra. */
  }
}

function leerPendiente() {
  try {
    const guardado = JSON.parse(sessionStorage.getItem(AVISO_PENDIENTE_KEY) || "null");
    sessionStorage.removeItem(AVISO_PENDIENTE_KEY);
    return guardado && guardado.texto ? guardado : null;
  } catch {
    return null;
  }
}

function Aviso({ aviso, onCerrar }) {
  const temporizador = useRef(null);
  const programar = useCallback(() => {
    clearTimeout(temporizador.current);
    temporizador.current = setTimeout(() => onCerrar(aviso.id), AVISO_EXITO_MS);
  }, [aviso.id, onCerrar]);

  useEffect(() => {
    if (aviso.tipo === "exito" && !aviso.cerrando) programar();
    return () => clearTimeout(temporizador.current);
  }, [aviso.tipo, aviso.cerrando, programar]);

  const pausar = () => clearTimeout(temporizador.current);
  const seguir = () => { if (aviso.tipo === "exito" && !aviso.cerrando) programar(); };
  return (
    <div className={`aviso ${aviso.tipo}${aviso.cerrando ? " saliendo" : ""}`}
      role={aviso.tipo === "error" ? "alert" : undefined}
      onMouseEnter={pausar} onMouseLeave={seguir} onFocus={pausar} onBlur={seguir}
      onKeyDown={(evento) => {
        if (evento.key === "Escape") {
          evento.preventDefault();
          evento.stopPropagation();
          onCerrar(aviso.id);
        }
      }}>
      <p className="aviso-texto">{aviso.texto}</p>
      <button type="button" className="aviso-cerrar" aria-label="Cerrar aviso" onClick={() => onCerrar(aviso.id)}>✕</button>
    </div>
  );
}

/* La zona, justo debajo de la barra del título (variable CSS con CSSOM: la
   CSP no permite estilos en línea en el HTML). Con una ventana modal
   abierta (<dialog>) va adentro de ella, para que se vea y se pueda cerrar;
   al cerrarla vuelve al <body>. */
function Zona({ avisos, onCerrar }) {
  const zona = useRef(null);
  const [modal, setModal] = useState(null);
  useLayoutEffect(() => {
    const abierto = document.querySelector("dialog[open]");
    if (abierto !== modal) setModal(abierto);
  }, [avisos]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!modal) return undefined;
    const alCerrar = () => setModal(null);
    modal.addEventListener("close", alCerrar);
    return () => modal.removeEventListener("close", alCerrar);
  }, [modal]);
  useLayoutEffect(() => {
    if (!zona.current) return;
    const cabecera = modal ? null : document.querySelector(".cabecera");
    const borde = cabecera ? Math.max(cabecera.getBoundingClientRect().bottom, 0) : 0;
    zona.current.style.setProperty("--avisos-arriba", `${Math.round(borde + AVISOS_MARGEN_PX)}px`);
  });
  return createPortal(
    <div id="avisos" className="avisos" aria-live="polite" aria-label="Avisos" ref={zona}>
      {avisos.map((aviso) => <Aviso key={aviso.id} aviso={aviso} onCerrar={onCerrar} />)}
    </div>,
    modal || document.body,
  );
}

let siguienteId = 1;

export function AvisosProvider({ children }) {
  const [avisos, setAvisosEstado] = useState([]);
  const actuales = useRef([]);
  /* La lista vive en una ref que se actualiza en el acto (varios avisos
     seguidos en la misma tanda ven a los anteriores) y se copia al estado. */
  const setAvisos = useCallback((cambio) => {
    actuales.current = typeof cambio === "function" ? cambio(actuales.current) : cambio;
    setAvisosEstado(actuales.current);
  }, []);

  const cerrar = useCallback((id) => {
    setAvisos((lista) => lista.map((a) => (a.id === id ? { ...a, cerrando: true } : a)));
    setTimeout(() => setAvisos((lista) => lista.filter((a) => a.id !== id)), AVISO_SALIDA_MS);
  }, [setAvisos]);

  const avisar = useCallback((texto, tipo = "exito") => {
    if (!texto) return;
    const clase = tipo === "error" ? "error" : "exito";
    const nuevo = { id: siguienteId++, texto: String(texto), tipo: clase, cerrando: false };
    /* El mismo aviso dos veces seguidas se renueva; más de 4, se va el más viejo. */
    const lista = actuales.current;
    const repetidos = lista.filter((a) => a.texto === nuevo.texto && a.tipo === clase && !a.cerrando);
    const visibles = lista.filter((a) => !a.cerrando && !repetidos.includes(a));
    const sobran = visibles.slice(0, Math.max(0, visibles.length - AVISOS_MAXIMO + 1));
    setAvisos((previa) => [...previa, nuevo]);
    [...repetidos, ...sobran].forEach((a) => cerrar(a.id));
  }, [cerrar, setAvisos]);

  return (
    <AvisosContext.Provider value={{ avisar }}>
      {children}
      <Zona avisos={avisos} onCerrar={cerrar} />
      <AvisoPendiente avisar={avisar} />
    </AvisosContext.Provider>
  );
}

/* Al llegar a cada pantalla, el aviso que dejó la anterior (también desde
   la app actual). */
function AvisoPendiente({ avisar }) {
  const { pathname } = useLocation();
  useEffect(() => {
    const pendiente = leerPendiente();
    if (pendiente) avisar(pendiente.texto, pendiente.tipo);
  }, [pathname, avisar]);
  return null;
}

export const useAvisos = () => useContext(AvisosContext);
