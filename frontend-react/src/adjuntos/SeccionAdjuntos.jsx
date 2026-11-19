/* Adjuntos en el detalle del ticket (port de frontend/js/adjuntos.js).
   Quien ve el ticket los ve y sube; borra quien lo subió o el Administrador
   (puede_eliminar viene del servidor). En Cerrado, solo lectura. Las
   miniaturas y descargas se piden con la sesión y se muestran desde un blob
   local: nunca hay enlaces públicos. */
import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { api } from "../api/cliente.js";
import { useAvisos } from "../avisos/Avisos.jsx";
import { useConfirmar } from "../componentes/Confirmar.jsx";
import {
  ADJ_ACCEPT, ADJ_POR_DEFECTO, ADJ_TIPOS_TEXTO, adjFecha, adjMensaje, adjProblema, adjSubirUno,
  achicarImagen, esTactil, extensionDe, formatoTamano, pedirArchivo,
} from "./adjuntos.js";

/* URL local de cada imagen, pedida una sola vez por adjunto. */
function useImagenes() {
  const cache = useRef(new Map());
  const urls = useRef([]);
  const liberar = useCallback(() => {
    urls.current.forEach((url) => URL.revokeObjectURL(url));
    urls.current = [];
    cache.current = new Map();
  }, []);
  useEffect(() => liberar, [liberar]);
  const urlDe = useCallback((adjunto) => {
    if (!cache.current.has(adjunto.id)) {
      const pedido = pedirArchivo(adjunto).then((blob) => {
        const url = URL.createObjectURL(blob);
        urls.current.push(url);
        return url;
      });
      pedido.catch(() => cache.current.delete(adjunto.id));
      cache.current.set(adjunto.id, pedido);
    }
    return cache.current.get(adjunto.id);
  }, []);
  return { urlDe, liberar };
}

function Miniatura({ adjunto, urlDe }) {
  const [src, setSrc] = useState(null);
  const [fallo, setFallo] = useState(false);
  useEffect(() => {
    let vigente = true;
    urlDe(adjunto).then((url) => { if (vigente) setSrc(url); }).catch(() => { if (vigente) setFallo(true); });
    return () => { vigente = false; };
  }, [adjunto, urlDe]);
  return <img className="adjunto-miniatura" alt="" width={48} height={48} src={src || undefined} hidden={fallo} />;
}

/* Vista ampliada: la imagen sobre un fondo oscuro con el nombre y ✕; se
   cierra con ✕, Escape o tocando afuera, y el foco vuelve a quien la abrió. */
function VistaPrevia({ adjunto, urlDe, volverA, onCerrar }) {
  const cerrarBoton = useRef(null);
  const caja = useRef(null);
  const [estado, setEstado] = useState("cargando");
  const [src, setSrc] = useState(null);

  useEffect(() => {
    let vigente = true;
    urlDe(adjunto).then((url) => { if (vigente) { setSrc(url); setEstado("lista"); } })
      .catch(() => { if (vigente) setEstado("error"); });
    return () => { vigente = false; };
  }, [adjunto, urlDe]);

  useEffect(() => {
    cerrarBoton.current.focus();
    const teclas = (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onCerrar();
      } else if (event.key === "Tab") {
        event.preventDefault();
        cerrarBoton.current.focus();
      }
    };
    document.addEventListener("keydown", teclas, true);
    const destino = volverA;
    return () => {
      document.removeEventListener("keydown", teclas, true);
      if (destino && typeof destino.focus === "function") destino.focus();
    };
  }, [onCerrar, volverA]);

  return createPortal(
    <div className="adj-visor-fondo" id="adj-visor" role="dialog" aria-modal="true" aria-labelledby="adj-visor-titulo"
      onClick={(event) => { if (event.target === event.currentTarget || event.target === caja.current) onCerrar(); }}>
      <div className="adj-visor" ref={caja}>
        <div className="adj-visor-cabecera">
          <p className="adj-visor-titulo" id="adj-visor-titulo">{adjunto.nombre}</p>
          <button type="button" className="adj-visor-cerrar" aria-label="Cerrar vista previa" ref={cerrarBoton} onClick={onCerrar}>✕</button>
        </div>
        {estado !== "lista" && (
          <p className="adj-visor-estado">{estado === "error" ? "No se pudo cargar la imagen." : "Cargando imagen…"}</p>
        )}
        <img className="adj-visor-imagen" alt={adjunto.nombre} src={src || undefined} hidden={estado !== "lista"} />
      </div>
    </div>,
    document.body,
  );
}

export default function SeccionAdjuntos({ ticketId, estadoTicket }) {
  const { avisar } = useAvisos();
  const confirmar = useConfirmar();
  const [datos, setDatos] = useState(ADJ_POR_DEFECTO);
  const [oculta, setOculta] = useState(false);
  const [estado, setEstado] = useState(null); /* { texto, tipo } */
  const [ocupado, setOcupado] = useState(false);
  const [visor, setVisor] = useState(null); /* { adjunto, volverA } */
  const archivos = useRef(null);
  const camara = useRef(null);
  const { urlDe, liberar } = useImagenes();
  const cerrarVisor = useCallback(() => setVisor(null), []);

  const cargar = useCallback(async () => {
    try {
      const response = await api(`/api/tickets/${ticketId}/adjuntos`);
      if (response.status === 404) {
        setOculta(true);
        return;
      }
      if (!response.ok) {
        setEstado({ texto: `No se pudieron cargar los adjuntos (HTTP ${response.status}).`, tipo: "error" });
        return;
      }
      const nuevos = await response.json();
      liberar();
      setOculta(false);
      setEstado(null);
      setDatos({ ...ADJ_POR_DEFECTO, ...nuevos });
    } catch {
      setEstado({ texto: "No se pudieron cargar los adjuntos.", tipo: "error" });
    }
  }, [ticketId, liberar]);

  /* Al abrir y cada vez que cambia el estado del ticket (p. ej. a Cerrado). */
  useEffect(() => {
    if (estadoTicket) cargar();
  }, [cargar, estadoTicket]);

  const subir = async (lista, input) => {
    const elegidos = Array.from(lista || []);
    if (elegidos.length === 0 || ocupado) return;
    const libres = datos.max_archivos - (datos.adjuntos || []).length;
    const errores = [];
    if (elegidos.length > libres) {
      errores.push(`Solo se pueden agregar ${Math.max(libres, 0)} archivo(s) más (máximo ${datos.max_archivos} por ticket).`);
      elegidos.splice(Math.max(libres, 0));
    }
    setOcupado(true);
    let subidos = 0;
    try {
      for (const [i, original] of elegidos.entries()) {
        setEstado({ texto: `Subiendo ${i + 1} de ${elegidos.length}: ${original.name}…`, tipo: "cargando" });
        const archivo = await achicarImagen(original, datos.max_bytes);
        const problema = adjProblema(archivo, datos.max_bytes);
        if (problema) {
          errores.push(problema);
          continue;
        }
        const error = await adjSubirUno(ticketId, archivo);
        if (error) errores.push(error);
        else subidos += 1;
      }
    } finally {
      setOcupado(false);
      if (input) input.value = "";
    }
    if (subidos) avisar(subidos === 1 ? "Archivo adjuntado." : `${subidos} archivos adjuntados.`, "exito");
    await cargar();
    errores.forEach((error) => avisar(error, "error"));
  };

  const descargar = async (adjunto) => {
    try {
      const url = URL.createObjectURL(await pedirArchivo(adjunto));
      const enlace = document.createElement("a");
      enlace.href = url;
      enlace.download = adjunto.nombre;
      document.body.appendChild(enlace);
      enlace.click();
      enlace.remove();
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch {
      avisar(`No se pudo descargar «${adjunto.nombre}».`, "error");
    }
  };

  const eliminar = async (adjunto) => {
    if (ocupado) return;
    const ok = await confirmar({
      titulo: "Eliminar adjunto",
      mensaje: `¿Desea eliminar «${adjunto.nombre}» del ticket? Esta acción no se puede deshacer.`,
      aceptar: "Eliminar",
      peligro: true,
    });
    if (!ok) return;
    setOcupado(true);
    try {
      const response = await api(`/api/tickets/${adjunto.ticket_id}/adjuntos/${adjunto.id}`, { method: "DELETE" });
      if (response.status === 204) avisar(`«${adjunto.nombre}» eliminado.`, "exito");
      else avisar(await adjMensaje(response, "No se pudo eliminar el adjunto."), "error");
    } catch {
      avisar("Error al comunicarse con la API.", "error");
    } finally {
      setOcupado(false);
    }
    await cargar();
  };

  const adjuntos = Array.isArray(datos.adjuntos) ? datos.adjuntos : [];
  const nota = datos.puede_subir
    ? `${ADJ_TIPOS_TEXTO} · hasta 4 MB cada uno · ${adjuntos.length} de ${datos.max_archivos}`
    : (datos.cerrado
      ? "El ticket está Cerrado: no se agregan ni se eliminan adjuntos."
      : `El ticket ya tiene ${datos.max_archivos} adjuntos, el máximo permitido.`);
  const abrir = (adjunto) => (event) => {
    const fila = event.currentTarget.closest("li");
    setVisor({ adjunto, volverA: fila ? fila.querySelector(".adjunto-ver") : event.currentTarget });
  };

  return (
    <section id="seccion-adjuntos" className="seccion adjuntos" aria-labelledby="adjuntos-titulo" hidden={oculta}>
      <h2 id="adjuntos-titulo">Adjuntos</h2>
      <div className="adj-barra">
        <div id="adj-acciones" className="acciones" hidden={!datos.puede_subir}>
          <button type="button" id="adj-subir" disabled={ocupado} onClick={() => archivos.current.click()}>Adjuntar archivos</button>
          <button type="button" id="adj-foto" className="secundario" hidden={!esTactil()} disabled={ocupado}
            onClick={() => camara.current.click()}>Sacar foto</button>
          <input type="file" id="adj-archivos" multiple hidden accept={ADJ_ACCEPT} ref={archivos}
            data-testid="adj-archivos" onChange={(e) => subir(e.target.files, e.target)} />
          <input type="file" id="adj-camara" accept="image/*" capture="environment" hidden ref={camara}
            onChange={(e) => subir(e.target.files, e.target)} />
        </div>
        <span id="adj-vacio" className="linea-vacia" hidden={adjuntos.length > 0}>Sin adjuntos</span>
      </div>
      <p id="adj-nota" className="nota-chica">{nota}</p>
      <p id="adj-estado" className={`estado ${estado ? estado.tipo : ""}`.trim()} role="status" aria-live="polite" hidden={!estado}>
        {estado ? estado.texto : ""}
      </p>
      <ul id="adj-lista" className="adjuntos-lista" hidden={adjuntos.length === 0}>
        {adjuntos.map((adjunto) => (
          <li className="adjunto" key={adjunto.id}>
            {adjunto.es_imagen ? (
              <button type="button" className="adjunto-ver" aria-label={`Ver imagen ${adjunto.nombre}`} onClick={abrir(adjunto)}>
                <Miniatura adjunto={adjunto} urlDe={urlDe} />
              </button>
            ) : (
              <span className="adjunto-icono">{extensionDe(adjunto.nombre).slice(1).toUpperCase()}</span>
            )}
            <div className="adjunto-datos">
              {adjunto.es_imagen ? (
                <button type="button" className="adjunto-nombre adjunto-nombre-boton" aria-label={`Ver imagen ${adjunto.nombre}`}
                  onClick={abrir(adjunto)}>{adjunto.nombre}</button>
              ) : (
                <span className="adjunto-nombre">{adjunto.nombre}</span>
              )}
              <span className="adjunto-meta">
                {`${formatoTamano(adjunto.tamano)} · ${adjunto.subido_por || "Sistema"} · ${adjFecha(adjunto.creado)}`
                  + (adjunto.por_correo ? " · por correo" : "")}
              </span>
            </div>
            <div className="adjunto-acciones">
              <button type="button" className="adjunto-accion" aria-label={`Descargar ${adjunto.nombre}`}
                onClick={() => descargar(adjunto)}>Descargar</button>
              {adjunto.puede_eliminar && (
                <>
                  <span className="adjunto-separador" aria-hidden="true">·</span>
                  <button type="button" className="adjunto-accion adjunto-accion-peligro" aria-label={`Eliminar ${adjunto.nombre}`}
                    onClick={() => eliminar(adjunto)}>Eliminar</button>
                </>
              )}
            </div>
          </li>
        ))}
      </ul>
      {visor && <VistaPrevia adjunto={visor.adjunto} urlDe={urlDe} volverA={visor.volverA} onCerrar={cerrarVisor} />}
    </section>
  );
}
