/* Departamentos (port de frontend/departamentos.html + js/departamentos.js),
   solo Administrador: GET /api/departamentos/resumen. A la izquierda un botón
   por departamento (pestañas) con «Requieren atención» y la leyenda debajo; a
   la derecha el detalle del elegido. El elegido queda en la dirección
   (#programacion). Los enlaces llevan a la lista de React filtrada. */
import { useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { api } from "../api/cliente.js";
import Cabecera from "../componentes/Cabecera.jsx";
import ConEstilo from "../componentes/ConEstilo.jsx";
import { useTitulo } from "../componentes/claseBody.js";
import { destinoTeclado, useOrientacion } from "../componentes/useOrientacion.js";
import { claseBadge, persona } from "../sesion/permisos.js";
import { rutaTicket } from "../rutas.js";

const ESTADOS_DEPARTAMENTO = ["Nuevo", "En proceso", "Resuelto", "Cerrado"];
export const COLORES_ESTADO = { Nuevo: "#1d4ed8", "En proceso": "#7c9fe8", Resuelto: "#0e8a7d", Cerrado: "#a3abbb" };
const MAX_ABIERTOS_DETALLE = 10;

/* Enlace a la lista: ``area`` id o «sin»; ``estado`` uno, «abiertos» o vacío. */
export function urlListaDepartamento(areaId, estado = "") {
  const params = new URLSearchParams();
  params.set("area", areaId === null || areaId === undefined ? "sin" : String(areaId));
  if (estado) params.set("estado", estado);
  return `/?${params.toString()}`;
}

const textoTickets = (n) => (n === 1 ? "1 ticket" : `${n} tickets`);
const textoAbiertos = (n) => (n === 1 ? "1 abierto" : `${n} abiertos`);

export function slugDepartamento(nombre) {
  return String(nombre || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase()
    .replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
}

const visiblesDe = (departamentos) => departamentos.filter((d) => (d.area_id !== null && d.area_id !== undefined) || d.total > 0);

export function filasAtencion(atencion) {
  const dias = atencion.dias_nuevo || 2;
  return [
    ["Críticos abiertos", atencion.criticos, "/?prioridad=Cr%C3%ADtica&estado=abiertos"],
    ["Altos abiertos", atencion.altos, "/?prioridad=Alta&estado=abiertos"],
    ["Sin asignar", atencion.sin_asignar, "/?asignado=sin&estado=abiertos"],
    [`Más de ${dias} días en Nuevo`, atencion.nuevos_viejos, `/?estado=Nuevo&antiguedad=${dias}`],
  ];
}

function Barra({ fila }) {
  const total = fila.total || 0;
  return (
    <span className="depto-barra" aria-hidden="true">
      {ESTADOS_DEPARTAMENTO.map((estado) => {
        const n = (fila.por_estado || {})[estado] || 0;
        if (!total || !n) return null;
        return <ConEstilo key={estado} className="depto-barra-parte" estilos={{ width: `${(n * 100) / total}%`, backgroundColor: COLORES_ESTADO[estado] }} />;
      })}
    </span>
  );
}

function CeldaPersona({ nombre, clase }) {
  const p = persona(nombre, clase);
  return <td className={p.className} data-iniciales={p.iniciales}>{p.texto}</td>;
}

function Detalle({ fila }) {
  const tecnicos = fila.tecnicos || [];
  const tickets = (fila.tickets_abiertos || []).slice(0, MAX_ABIERTOS_DETALLE);
  const resto = (fila.abiertos || 0) - tickets.length;
  const sinDepto = fila.area_id === null || fila.area_id === undefined;
  return (
    <>
      <header className="depto-cabecera">
        <div className="depto-titulos">
          <h2 id="depto-nombre">{fila.nombre}</h2>
          <p className="depto-atiende" id="depto-atiende" hidden={!fila.atiende}>{fila.atiende ? `Atiende ${fila.atiende}` : ""}</p>
          <p className="depto-total" id="depto-total">{`${textoTickets(fila.total)} en total`}</p>
        </div>
        <Link className="enlace-boton secundario" id="depto-ver-todos" aria-label={`Ver todos los tickets de ${fila.nombre}`}
          to={urlListaDepartamento(fila.area_id, (fila.abiertos || 0) > MAX_ABIERTOS_DETALLE ? "abiertos" : "")}>Ver todos sus tickets</Link>
      </header>

      <ul className="depto-cajas" id="depto-cajas" aria-label="Tickets por estado">
        <li className="depto-caja depto-caja-abiertos">
          <span className="depto-caja-numero">{String(fila.abiertos)}</span>
          <span className="depto-caja-etiqueta">Abiertos</span>
        </li>
        {ESTADOS_DEPARTAMENTO.map((estado) => (
          <ConEstilo as="li" key={estado} className="depto-caja " estilos={{ borderTopColor: COLORES_ESTADO[estado] }}>
            <span className="depto-caja-numero">{String((fila.por_estado || {})[estado] || 0)}</span>
            <span className="depto-caja-etiqueta">{estado}</span>
          </ConEstilo>
        ))}
      </ul>

      <h3 className="depto-subtitulo" id="depto-tecnicos-titulo">Técnicos</h3>
      <div className="tabla-scroll">
        <table className="depto-tabla" aria-labelledby="depto-tecnicos-titulo" hidden={!tecnicos.length}>
          <thead>
            <tr>
              <th scope="col">Técnico</th>
              <th scope="col" className="celda-num">Abiertos</th>
              <th scope="col" className="celda-num">Resueltos este mes</th>
            </tr>
          </thead>
          <tbody id="depto-tecnicos">
            {tecnicos.map((t, i) => (
              <tr key={t.id ?? i}>
                <CeldaPersona nombre={t.name} clase="celda-persona" />
                <td className="celda-num" data-label="Abiertos">{String(t.abiertos || 0)}</td>
                <td className="celda-num" data-label="Resueltos este mes">{String(t.resueltos_mes || 0)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="depto-vacio" id="depto-tecnicos-vacio" hidden={tecnicos.length > 0}>
        {sinDepto ? "Los tickets sin departamento no tienen técnicos propios." : "Este departamento no tiene técnicos activos."}
      </p>

      <h3 className="depto-subtitulo" id="depto-abiertos-titulo">Tickets abiertos</h3>
      <div className="tabla-scroll">
        <table className="depto-tabla" aria-labelledby="depto-abiertos-titulo" hidden={!tickets.length}>
          <thead>
            <tr><th scope="col">Ticket</th><th scope="col">Estado</th><th scope="col">Prioridad</th><th scope="col">Asignado</th></tr>
          </thead>
          <tbody id="depto-abiertos">
            {tickets.map((t) => (
              <tr key={t.id}>
                <td className="celda-ticket">
                  <Link className="enlace-tabla" to={rutaTicket(t.id)}>{`#${t.id}`}</Link>
                  <span className="celda-ticket-titulo">{t.title}</span>
                </td>
                <td><span className={claseBadge(t.state)}>{t.state}</span></td>
                <td><span className={claseBadge(t.priority)}>{t.priority}</span></td>
                <CeldaPersona nombre={t.assigned_to_name || "—"} clase={t.assigned_to_name ? "celda-persona" : "celda-persona sin-asignar"} />
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="depto-vacio" id="depto-abiertos-vacio" hidden={tickets.length > 0}>No tiene tickets abiertos.</p>
      <p className="depto-nota" id="depto-abiertos-nota" hidden={resto <= 0}>
        {resto > 0 ? `Se muestran ${tickets.length} de ${fila.abiertos} abiertos. «Ver todos sus tickets» muestra el resto.` : ""}
      </p>
    </>
  );
}

export default function Departamentos() {
  useTitulo("Departamentos");
  const location = useLocation();
  const navigate = useNavigate();
  const orientacion = useOrientacion();
  const [datos, setDatos] = useState(null);
  const [estado, setEstado] = useState({ texto: "Cargando…", tipo: "cargando" });
  const [elegido, setElegido] = useState(0);
  const botones = useRef([]);

  const departamentos = datos ? visiblesDe(datos.departamentos) : [];
  const indiceDe = (hash) => {
    const slug = String(hash || "").replace(/^#/, "");
    const i = departamentos.findIndex((d) => slugDepartamento(d.nombre) === slug);
    return i >= 0 ? i : 0;
  };

  useEffect(() => {
    let vigente = true;
    (async () => {
      try {
        const response = await api("/api/departamentos/resumen");
        if (!vigente) return;
        if (response.status === 403) {
          setEstado({ texto: "Su rol no tiene permiso para ver los departamentos.", tipo: "error" });
          return;
        }
        const cuerpo = await response.json().catch(() => null);
        if (!vigente) return;
        if (!response.ok || !cuerpo || !Array.isArray(cuerpo.departamentos)) {
          setEstado({ texto: `No se pudieron cargar los departamentos (${response.status}).`, tipo: "error" });
          return;
        }
        setDatos(cuerpo);
        setEstado(null);
      } catch {
        if (vigente) setEstado({ texto: "Error al comunicarse con el servidor.", tipo: "error" });
      }
    })();
    return () => { vigente = false; };
  }, []);

  /* El de la dirección (o el primero); atrás/adelante lo cambia. */
  useEffect(() => {
    if (datos) setElegido(indiceDe(location.hash));
  }, [datos, location.hash]); // eslint-disable-line react-hooks/exhaustive-deps

  const elegir = (indice, { foco = false } = {}) => {
    const fila = departamentos[indice];
    if (!fila) return;
    setElegido(indice);
    navigate({ hash: `#${slugDepartamento(fila.nombre)}` }, { replace: true });
    if (foco && botones.current[indice]) {
      botones.current[indice].focus();
      if (typeof botones.current[indice].scrollIntoView === "function") botones.current[indice].scrollIntoView({ block: "nearest", inline: "nearest" });
    }
  };

  const fila = departamentos[elegido];
  return (
    <>
      <Cabecera claseTitulo="" titulo="Departamentos" subtitulo="Tickets de cada departamento de IT, sus técnicos y lo que tienen abierto" />
      <main className="contenido departamentos">
        <p id="estado-carga" className={estado && estado.tipo ? `estado ${estado.tipo}` : "estado"} role="status" aria-live="polite" hidden={!estado}>
          {estado ? estado.texto : ""}
        </p>
        <p className="deptos-ayuda" id="deptos-ayuda">Toque un departamento para ver su detalle</p>
        <div className="deptos-layout" id="deptos-layout" hidden={!datos}>
          <div className="deptos-columna">
            <div className="deptos-lista" id="deptos-lista" role="tablist" aria-orientation={orientacion} aria-label="Departamentos" aria-describedby="deptos-ayuda">
              {departamentos.map((d, indice) => {
                const slug = slugDepartamento(d.nombre);
                const sel = indice === elegido;
                const clases = ["depto-boton", (d.area_id === null || d.area_id === undefined) && "sin-departamento", sel && "elegido"].filter(Boolean).join(" ");
                return (
                  <button key={slug} type="button" className={clases} id={`tab-${slug}`} role="tab" aria-controls="deptos-detalle"
                    aria-selected={sel ? "true" : "false"} tabIndex={sel ? 0 : -1} data-slug={slug}
                    ref={(el) => { botones.current[indice] = el; }}
                    onClick={() => elegir(indice)}
                    onKeyDown={(evento) => {
                      const destino = destinoTeclado(evento.key, indice, departamentos.length);
                      if (destino === null) return;
                      evento.preventDefault();
                      elegir(destino, { foco: true });
                    }}>
                    <span className="depto-boton-nombre" title={d.nombre}>{d.nombre}</span>
                    <span className="depto-boton-abiertos">{textoAbiertos(d.abiertos)}</span>
                    <span className="depto-pastilla" aria-label={`${textoTickets(d.total)} en total`}>{String(d.total)}</span>
                    <Barra fila={d} />
                  </button>
                );
              })}
            </div>

            <div className="deptos-extras" id="deptos-extras">
              <section className="deptos-bloque" aria-labelledby="atencion-titulo">
                <h2 className="deptos-bloque-titulo" id="atencion-titulo">Requieren atención</h2>
                <ul className="deptos-atencion" id="deptos-atencion">
                  {datos && filasAtencion(datos.atencion || {}).map(([etiqueta, valor, href]) => {
                    const n = Number(valor) || 0;
                    return (
                      <li key={etiqueta}>
                        <Link className={`deptos-atencion-fila ${n > 0 ? "con-valor" : "en-cero"}`} to={href}
                          aria-label={`${etiqueta}: ${n}. Abrir la lista de tickets`}>
                          <span className="deptos-atencion-etiqueta">{etiqueta}</span>
                          <span className="deptos-atencion-numero">{String(n)}</span>
                        </Link>
                      </li>
                    );
                  })}
                </ul>
              </section>
              <section className="deptos-bloque" aria-labelledby="leyenda-titulo">
                <h2 className="deptos-bloque-titulo" id="leyenda-titulo">Leyenda</h2>
                <ul className="deptos-leyenda" id="deptos-leyenda">
                  {datos && ESTADOS_DEPARTAMENTO.map((e) => (
                    <li className="deptos-leyenda-item" key={e}>
                      <ConEstilo className="deptos-leyenda-color" aria-hidden="true" estilos={{ backgroundColor: COLORES_ESTADO[e] }} />
                      <span>{e}</span>
                    </li>
                  ))}
                </ul>
              </section>
            </div>
          </div>

          <section className="deptos-detalle" id="deptos-detalle" role="tabpanel" tabIndex={0}
            aria-labelledby={fila ? `tab-${slugDepartamento(fila.nombre)}` : undefined}>
            {fila && <Detalle fila={fila} />}
          </section>
        </div>
      </main>
    </>
  );
}
