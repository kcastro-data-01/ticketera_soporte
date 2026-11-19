/* Historial global (port de frontend/historial.html + js/historial.js),
   solo para quien tiene historial_global: los cambios agrupados por persona.
   A la izquierda las personas (pestañas) con «Todas las personas» arriba y
   «Sistema»; a la derecha período, búsqueda, cajas y los cambios por día (50
   por vez, con «Ver más»). La persona y el período quedan en la dirección. */
import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { api } from "../api/cliente.js";
import Cabecera from "../componentes/Cabecera.jsx";
import { useTitulo } from "../componentes/claseBody.js";
import { destinoTeclado, useOrientacion } from "../componentes/useOrientacion.js";
import {
  CAMBIOS_POR_PAGINA, PERIODOS_HISTORIAL, PERSONA_SISTEMA, PERSONA_TODAS, agruparPorDia, armarHash,
  formatAutor, fraseCambio, leerHash, textoCambios,
} from "../historial/frases.js";
import { formatearFechaHora, inicialesDe, persona as personaClases, tonoAvatar } from "../sesion/permisos.js";
import { rutaTicket } from "../rutas.js";

const ESPERA_BUSQUEDA_MS = 300;
const SIN_CONEXION = "No se pudo conectar con el servidor. Verifique que esté en funcionamiento.";

async function pedirJson(url) {
  let response;
  try {
    response = await api(url);
  } catch {
    throw new Error(SIN_CONEXION);
  }
  if (response.status === 403) throw new Error("Su rol no tiene permiso para ver el historial.");
  const datos = await response.json().catch(() => null);
  if (!response.ok || datos === null) throw new Error(`No se pudo cargar el historial (${response.status}).`);
  return datos;
}

function Avatar({ persona }) {
  if (persona.clave === PERSONA_TODAS) {
    return (
      <span className="hist-avatar hist-avatar-icono" aria-hidden="true">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" /><circle cx="9" cy="7" r="4" /><path d="M22 21v-2a4 4 0 0 0-3-3.9M16 3.1a4 4 0 0 1 0 7.8" /></svg>
      </span>
    );
  }
  if (persona.clave === PERSONA_SISTEMA) {
    return (
      <span className="hist-avatar hist-avatar-icono hist-avatar-sistema" aria-hidden="true">
        <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="4" y="4" width="16" height="16" rx="2" /><path d="M9 9h6v6H9zM9 1v3M15 1v3M9 20v3M15 20v3M20 9h3M20 14h3M1 9h3M1 14h3" /></svg>
      </span>
    );
  }
  return <span className={`hist-avatar tono-avatar-${tonoAvatar(persona.nombre)}`} aria-hidden="true">{inicialesDe(persona.nombre)}</span>;
}

function Caja({ etiqueta, valor, clase }) {
  return (
    <li className={`depto-caja ${clase || ""}`.trim()}>
      <span className="depto-caja-numero">{String(valor)}</span>
      <span className="depto-caja-etiqueta">{etiqueta}</span>
    </li>
  );
}

function Linea({ entry, conAutor }) {
  const autor = personaClases(formatAutor(entry), "hist-autor");
  return (
    <li className={conAutor ? "hist-linea con-autor" : "hist-linea"}>
      <time className="hist-hora" dateTime={entry.created_at ? String(entry.created_at) : undefined}>
        {formatearFechaHora(entry.created_at, { parte: "hora" })}
      </time>
      {conAutor && <span className={autor.className} data-iniciales={autor.iniciales}>{autor.texto}</span>}
      <span className="hist-ticket">
        <Link className="enlace-tabla" to={rutaTicket(entry.ticket_id)}>{`#${entry.ticket_id}`}</Link>
        {entry.ticket_title && <span className="hist-ticket-titulo" title={entry.ticket_title}>{entry.ticket_title}</span>}
      </span>
      <span className="hist-frase">{fraseCambio(entry)}</span>
    </li>
  );
}

export default function Historial() {
  useTitulo("Historial");
  const location = useLocation();
  const navigate = useNavigate();
  const orientacion = useOrientacion();
  const inicial = leerHash(location.hash);
  const [persona, setPersona] = useState(inicial.persona);
  const [periodo, setPeriodo] = useState(inicial.periodo);
  const [buscar, setBuscar] = useState("");
  const [texto, setTexto] = useState("");
  const [personas, setPersonas] = useState([]);
  const [visibles, setVisibles] = useState([]);
  const [total, setTotal] = useState(0);
  const [cajas, setCajas] = useState(null);
  const [cambios, setCambios] = useState([]);
  const [listo, setListo] = useState(false);
  const [cargando, setCargando] = useState(false);
  const [estado, setEstado] = useState({ texto: "Cargando…", tipo: "cargando" });
  const [verMasOcupado, setVerMasOcupado] = useState(false);
  const pedido = useRef(0);
  const botones = useRef({});
  const enfocar = useRef(null);
  const repintar = useRef(true);
  const espera = useRef(null);

  const todas = (cantidad) => ({ clave: PERSONA_TODAS, nombre: "Todas las personas", rol: null, departamento: null, cambios: cantidad });

  const guardarHash = useCallback((p, per) => {
    const hash = armarHash(p, per);
    if (hash !== location.hash) navigate({ hash }, { replace: true });
  }, [location.hash, navigate]);

  /* Resumen (personas y cajas) y la primera página del filtro actual. */
  const actualizar = useCallback(async (p, per, b, { repintarLista }) => {
    const numero = ++pedido.current;
    setCargando(true);
    const params = new URLSearchParams({ persona: p, periodo: per });
    if (b) params.set("buscar", b);
    const paginada = new URLSearchParams(params);
    paginada.set("limit", String(CAMBIOS_POR_PAGINA));
    paginada.set("offset", "0");
    try {
      const [resumen, lista] = await Promise.all([
        pedirJson(`/api/history/resumen?${params}`),
        pedirJson(`/api/history?${paginada}`),
      ]);
      if (numero !== pedido.current) return;
      if (!resumen || !Array.isArray(resumen.personas) || !Array.isArray(lista)) throw new Error("Respuesta inválida del servidor.");
      /* Una persona que ya no está en el historial vuelve a «Todas». */
      if (p !== PERSONA_TODAS && !resumen.personas.some((x) => x.clave === p)) {
        setPersona(PERSONA_TODAS);
        repintar.current = true;
        return;
      }
      setPersonas(resumen.personas);
      setTotal(resumen.total || 0);
      setCajas(resumen.cajas || null);
      setCambios(lista);
      if (repintarLista) {
        setVisibles([todas(resumen.total || 0), ...resumen.personas.filter((x) => x.cambios > 0 || x.clave === p)]);
      } else {
        setVisibles((actuales) => actuales.map((x) => (x.clave === PERSONA_TODAS ? todas(resumen.total || 0) : x)));
      }
      setListo(true);
      setEstado(null);
    } catch (error) {
      if (numero !== pedido.current) return;
      setEstado({ texto: error && error.message ? error.message : "Error al comunicarse con el servidor.", tipo: "error" });
    } finally {
      if (numero === pedido.current) setCargando(false);
    }
  }, []);

  useEffect(() => {
    const repintarLista = repintar.current;
    repintar.current = false;
    actualizar(persona, periodo, buscar, { repintarLista });
  }, [persona, periodo, buscar, actualizar]);

  /* La dirección refleja persona y período; atrás/adelante o un enlace la cambian. */
  useEffect(() => { guardarHash(persona, periodo); }, [persona, periodo]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    const desde = leerHash(location.hash);
    if (desde.periodo !== periodo) {
      repintar.current = true;
      setPeriodo(desde.periodo);
    }
    if (location.hash && desde.persona !== persona) {
      repintar.current = true;
      setPersona(desde.persona);
    }
  }, [location.hash]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (enfocar.current && botones.current[enfocar.current]) {
      const boton = botones.current[enfocar.current];
      boton.focus();
      if (typeof boton.scrollIntoView === "function") boton.scrollIntoView({ block: "nearest", inline: "nearest" });
    }
    enfocar.current = null;
  }, [persona]);

  const elegir = (clave, { foco = false } = {}) => {
    if (foco) enfocar.current = clave;
    if (clave === persona) {
      if (foco && botones.current[clave]) botones.current[clave].focus();
      return;
    }
    setPersona(clave);
  };

  const cambiarPeriodo = (valor) => {
    if (!PERIODOS_HISTORIAL.includes(valor) || valor === periodo) return;
    repintar.current = true;
    setPeriodo(valor);
  };

  const aplicarBusqueda = (valor, { inmediato = false } = {}) => {
    const limpio = String(valor || "").trim();
    clearTimeout(espera.current);
    const aplicar = () => setBuscar((actual) => (actual === limpio ? actual : limpio));
    if (inmediato) aplicar();
    else espera.current = setTimeout(aplicar, ESPERA_BUSQUEDA_MS);
  };
  useEffect(() => () => clearTimeout(espera.current), []);

  const verMas = async () => {
    const numero = pedido.current;
    setVerMasOcupado(true);
    const params = new URLSearchParams({ persona, periodo });
    if (buscar) params.set("buscar", buscar);
    params.set("limit", String(CAMBIOS_POR_PAGINA));
    params.set("offset", String(cambios.length));
    try {
      const mas = await pedirJson(`/api/history?${params}`);
      if (numero !== pedido.current || !Array.isArray(mas)) return;
      setCambios((actuales) => [...actuales, ...mas]);
    } catch (error) {
      setEstado({ texto: error && error.message ? error.message : "Error al comunicarse con el servidor.", tipo: "error" });
    } finally {
      setVerMasOcupado(false);
    }
  };

  const elegida = persona === PERSONA_TODAS ? todas(total)
    : visibles.find((p) => p.clave === persona) || personas.find((p) => p.clave === persona) || todas(total);
  const partes = elegida.clave === PERSONA_TODAS
    ? ["Técnicos, administradores, solicitantes y Sistema"]
    : [elegida.rol, elegida.departamento].filter(Boolean);
  const c = cajas || {};
  const totalCambios = cajas ? cajas.cambios : cambios.length;
  const resto = totalCambios - cambios.length;
  const conAutor = persona === PERSONA_TODAS;

  return (
    <>
      <Cabecera claseTitulo="" titulo="Historial" subtitulo="Los cambios hechos en los tickets, por persona" />
      <main className="contenido historial-personas">
        <p id="estado-carga" className={estado && estado.tipo ? `estado ${estado.tipo}` : "estado"} role="status" aria-live="polite" hidden={!estado}>
          {estado ? estado.texto : ""}
        </p>
        <p className="deptos-ayuda" id="hist-ayuda">Toque una persona para ver sus cambios</p>
        <div className="deptos-layout" id="hist-layout" hidden={!listo}>
          <div className="deptos-columna">
            <div className="deptos-lista" id="hist-lista" role="tablist" aria-orientation={orientacion} aria-label="Personas" aria-describedby="hist-ayuda">
              {visibles.map((p, indice) => {
                const sel = p.clave === persona;
                const clases = ["depto-boton hist-persona", p.clave === PERSONA_TODAS && "hist-todas",
                  p.clave === PERSONA_SISTEMA && "hist-sistema", sel && "elegido"].filter(Boolean).join(" ");
                return (
                  <button key={p.clave} type="button" className={clases} id={`tab-persona-${p.clave}`} role="tab"
                    aria-controls="hist-detalle" aria-selected={sel ? "true" : "false"} tabIndex={sel ? 0 : -1} data-persona={p.clave}
                    ref={(el) => { botones.current[p.clave] = el; }}
                    onClick={() => elegir(p.clave)}
                    onKeyDown={(evento) => {
                      const destino = destinoTeclado(evento.key, indice, visibles.length);
                      if (destino === null) return;
                      evento.preventDefault();
                      elegir(visibles[destino].clave, { foco: true });
                    }}>
                    <Avatar persona={p} />
                    <span className="depto-boton-nombre" title={p.nombre}>{p.nombre}</span>
                    <span className="depto-boton-abiertos">{textoCambios(p.cambios)}</span>
                    <span className="depto-pastilla" aria-hidden="true">{String(p.cambios)}</span>
                  </button>
                );
              })}
            </div>
          </div>

          <section className="deptos-detalle" id="hist-detalle" role="tabpanel" tabIndex={0}
            aria-labelledby={listo ? `tab-persona-${persona}` : undefined} aria-busy={cargando ? "true" : undefined}>
            <header className="depto-cabecera">
              <div className="depto-titulos">
                <h2 id="hist-nombre">{listo ? elegida.nombre : ""}</h2>
                <p className="depto-atiende" id="hist-rol" hidden={!partes.length}>{partes.join(" · ")}</p>
                <p className="depto-total" id="hist-total">{listo ? `${textoCambios(elegida.cambios || 0)} en el período` : ""}</p>
              </div>
              <div className="hist-controles">
                <label className="campo hist-campo-periodo">
                  <span>Período</span>
                  <select id="hist-periodo" value={periodo} onChange={(e) => cambiarPeriodo(e.target.value)}>
                    <option value="hoy">Hoy</option>
                    <option value="7">Últimos 7 días</option>
                    <option value="30">Últimos 30 días</option>
                  </select>
                </label>
                <label className="campo hist-campo-buscar">
                  <span>Buscar ticket</span>
                  <input type="search" id="hist-buscar" placeholder="Número o título" autoComplete="off" maxLength={200}
                    value={texto}
                    onChange={(e) => { setTexto(e.target.value); aplicarBusqueda(e.target.value); }}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        e.preventDefault();
                        aplicarBusqueda(texto, { inmediato: true });
                      }
                    }} />
                </label>
              </div>
            </header>

            <ul className="depto-cajas hist-cajas" id="hist-cajas" aria-label="Resumen del período">
              {listo && (
                <>
                  <Caja etiqueta="Cambios" valor={c.cambios || 0} clase="depto-caja-abiertos" />
                  <Caja etiqueta="Tickets tocados" valor={c.tickets || 0} />
                  <Caja etiqueta="Comentarios" valor={c.comentarios || 0} />
                  <Caja etiqueta="Cambios de estado" valor={c.cambios_estado || 0} />
                </>
              )}
            </ul>

            <div className="hist-cambios" id="hist-cambios">
              {agruparPorDia(cambios).map((grupo) => {
                const id = `hist-dia-${grupo.clave || "sin-fecha"}`;
                return (
                  <section className="hist-dia" aria-labelledby={id} key={id}>
                    <h3 className="depto-subtitulo hist-dia-titulo" id={id}>{grupo.texto}</h3>
                    <ul className="hist-lineas">
                      {grupo.cambios.map((entry, i) => <Linea key={entry.id ?? `${id}-${i}`} entry={entry} conAutor={conAutor} />)}
                    </ul>
                  </section>
                );
              })}
            </div>
            <p className="depto-vacio" id="hist-vacio" role="status" hidden={!listo || cambios.length > 0}>
              {buscar ? `Ningún cambio en el período coincide con «${buscar}».` : "No hay cambios en este período."}
            </p>
            <div className="hist-mas">
              <button type="button" id="hist-ver-mas" className="secundario" hidden={!listo || resto <= 0} disabled={verMasOcupado}
                aria-label={`Ver más cambios (faltan ${resto})`} onClick={verMas}>Ver más</button>
            </div>
          </section>
        </div>
      </main>
    </>
  );
}
