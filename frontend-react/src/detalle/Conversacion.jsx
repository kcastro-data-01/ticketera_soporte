import { useLayoutEffect, useRef } from "react";
import { formatearFechaHora, persona } from "../sesion/permisos.js";
import { armarConversacion, textoSistema } from "./comentarios.js";

/* Comentarios del más antiguo al más reciente: línea azul si es de IT,
   «por correo», seguidos agrupados y el motivo de un cambio de estado como
   aviso del sistema. Todo como texto. */
export default function Conversacion({ comentarios }) {
  const lista = useRef(null);
  useLayoutEffect(() => {
    /* Al abrir el ticket (y al agregar uno) se ve el último. */
    if (lista.current) lista.current.scrollTop = lista.current.scrollHeight || 0;
  }, [comentarios]);
  return (
    <div id="lista-comentarios" className="comentarios" aria-label="Conversación del ticket" tabIndex={0} ref={lista}>
      {armarConversacion(comentarios).map(({ comentario: c, seguido, sistema }, i) => {
        if (sistema) {
          return (
            <p className="comentario-sistema" key={c.id ?? `s${i}`}>
              <span className="comentario-sistema-texto">{textoSistema(c)}</span>
              <span className="comentario-sistema-meta">{`${c.author || "Anónimo"} · ${formatearFechaHora(c.created_at)}`}</span>
            </p>
          );
        }
        const autor = c.author || "Anónimo";
        const p = persona(autor, "comentario-autor");
        return (
          <article key={c.id ?? `c${i}`} className={`comentario ${c.author_es_it ? "de-it" : "de-otro"}${seguido ? " seguido" : ""}`}>
            <div className="comentario-cabecera">
              {seguido
                ? <span className="comentario-autor solo-lector">{autor}</span>
                : <span className={p.className} data-iniciales={p.iniciales}>{p.texto}</span>}
              {!seguido && c.author_es_it && <span className="comentario-it" title="Técnico o Administrador">IT</span>}
              {c.origen === "correo" && <span className="comentario-correo">por correo</span>}
              <span className="comentario-fecha">{formatearFechaHora(c.created_at)}</span>
            </div>
            <p className="comentario-contenido">{c.content}</p>
          </article>
        );
      })}
    </div>
  );
}
