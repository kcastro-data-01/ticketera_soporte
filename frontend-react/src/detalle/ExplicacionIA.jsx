/* «Explicar con IA» (port de frontend/js/explicacion.js), Técnico y
   Administrador. Al abrir muestra la explicación guardada (GET, sin llamar a
   la IA); «Explicar con IA» la pide (POST) y «Volver a explicar» fuerza una
   nueva. Con la IA apagada (ia_disponible: false) no hay botones. Todo como texto. */
import { useEffect, useRef, useState } from "react";
import { api } from "../api/cliente.js";
import { useAvisos } from "../avisos/Avisos.jsx";
import { formatearFechaHora } from "../sesion/permisos.js";

const IA_LIMITE_MS = 200000;
const IA_NOTA = "Contenido generado automáticamente. Revíselo antes de utilizarlo.";
const IA_NO_DISPONIBLE_TXT = "La IA no está disponible en este momento";
const IA_TARDO_TXT = "La IA no está disponible en este momento. Tardó demasiado en responder; inténtelo de nuevo.";
const IA_APAGADA_TXT = "La explicación con IA no está disponible en esta versión.";

function Panel({ datos }) {
  const e = datos.explicacion;
  const sugerencias = [
    ["Categoría sugerida", e.categoria_sugerida],
    ["Prioridad sugerida", e.prioridad_sugerida],
  ].filter(([, s]) => s && s.valor);
  const fecha = datos.generada_en ? formatearFechaHora(datos.generada_en) : "";
  const pie = [datos.modelo && `Modelo: ${datos.modelo}`, datos.generada_en && `generado el ${fecha === "—" ? "" : fecha}`]
    .filter(Boolean).join(" · ");
  const causas = e.posibles_causas || [];
  const revisar = e.que_revisar_primero || [];
  return (
    <>
      <p className="ia-aviso">{IA_NOTA}</p>
      {!datos.vigente && (
        <p className="ia-desactualizada">
          El ticket cambió desde la última explicación. Seleccione «Volver a explicar» para actualizarla.
        </p>
      )}
      <p className="ia-explicacion">{e.explicacion}</p>
      <p><strong>Certeza: </strong><span className={`ia-certeza ${e.certeza}`}>{e.certeza}</span></p>
      <p>
        <strong>Claridad: </strong>
        <span className={`ia-claridad ${String(datos.claridad || "").replace(" ", "-")}`}>{datos.claridad}</span>
        {` ${datos.motivo_claridad}`}
      </p>
      {causas.length > 0 && (<><h3>Posibles causas</h3><ul>{causas.map((c, i) => <li key={i}>{c}</li>)}</ul></>)}
      {revisar.length > 0 && (<><h3>Qué revisar primero</h3><ol>{revisar.map((c, i) => <li key={i}>{c}</li>)}</ol></>)}
      {sugerencias.length > 0 && (
        <>
          <h3>Sugerencias (no se aplican solas)</h3>
          <ul>{sugerencias.map(([t, s]) => <li key={t}>{`${t}: ${s.valor}${s.razon ? ` — ${s.razon}` : ""}`}</li>)}</ul>
        </>
      )}
      {pie && <p className="ia-pie">{pie}</p>}
    </>
  );
}

/* ``permitida`` false (Solicitante): la sección queda en la página, oculta y
   sin pedir nada, como en la pantalla actual. */
export default function ExplicacionIA({ ticketId, oculta, permitida = true }) {
  const { avisar } = useAvisos();
  const [datos, setDatos] = useState(null);
  const [disponible, setDisponible] = useState(true);
  const [estado, setEstado] = useState(null);
  const [ocupada, setOcupada] = useState(false);
  const ocupadaRef = useRef(false);

  useEffect(() => {
    if (!permitida) return undefined;
    let vigente = true;
    (async () => {
      try {
        const response = await api(`/api/tickets/${ticketId}/explicacion`);
        if (!response.ok || !vigente) return;
        const guardada = await response.json();
        if (!vigente || !guardada) return;
        if (guardada.ia_disponible === false) {
          setDisponible(false);
          setDatos(guardada);
          setEstado({ texto: IA_APAGADA_TXT, tipo: "" });
          return;
        }
        if (guardada.explicacion) setDatos(guardada);
      } catch {
        /* Sin explicación guardada. */
      }
    })();
    return () => { vigente = false; };
  }, [ticketId, permitida]);

  const explicar = async (regenerar = false) => {
    if (ocupadaRef.current) return;
    ocupadaRef.current = true;
    setOcupada(true);
    setEstado({ texto: "Analizando el ticket… puede tardar hasta un minuto.", tipo: "ia-cargando" });
    const control = new AbortController();
    const limite = setTimeout(() => control.abort(), IA_LIMITE_MS);
    try {
      const response = await api(`/api/tickets/${ticketId}/explicacion${regenerar ? "?regenerar=true" : ""}`, {
        method: "POST", signal: control.signal,
      });
      const cuerpo = await response.json().catch(() => null);
      setEstado(null);
      if (response.ok && cuerpo) {
        setDatos(cuerpo);
        avisar(regenerar ? "Explicación regenerada correctamente." : "Explicación generada correctamente.");
      } else if (response.status === 403) {
        avisar("Su rol no tiene permiso para usar «Explicar con IA».", "error");
      } else if (response.status === 404) {
        avisar("El ticket ya no existe.", "error");
      } else {
        avisar(cuerpo && typeof cuerpo.detail === "string" ? cuerpo.detail : IA_NO_DISPONIBLE_TXT, "error");
      }
    } catch (error) {
      setEstado(null);
      avisar(error && error.name === "AbortError" ? IA_TARDO_TXT : "Error al comunicarse con la API.", "error");
    } finally {
      clearTimeout(limite);
      ocupadaRef.current = false;
      setOcupada(false);
    }
  };

  const hay = Boolean(datos && datos.explicacion);
  return (
    <section id="seccion-ia" className="seccion pestana-panel" role="tabpanel" aria-labelledby="pestana-ia" hidden={oculta || !permitida}>
      <h2>Explicación con IA</h2>
      <p className="nota-chica">Interpreta el ticket, propone causas probables y qué revisar primero.</p>
      <div className="acciones">
        <button type="button" id="ia-explicar" hidden={hay || !disponible} disabled={ocupada} onClick={() => explicar(false)}>Explicar con IA</button>
        <button type="button" id="ia-regenerar" className="secundario" hidden={!hay || !disponible} disabled={ocupada}
          onClick={() => explicar(true)}>Volver a explicar</button>
      </div>
      <p id="ia-estado" className={`estado ${estado ? estado.tipo : ""}`.trim()} role="status" aria-live="polite" hidden={!estado}>
        {estado ? estado.texto : ""}
      </p>
      <div id="ia-panel" className="ia-panel" hidden={!hay}>{hay && <Panel datos={datos} />}</div>
    </section>
  );
}
