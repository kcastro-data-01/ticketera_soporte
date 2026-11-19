/* Pantalla de Tickets (port de frontend/index.html + js/app.js): filtros,
   «Todos / Mis tickets», Tabla o Tablero, densidad y orden por columnas.
   Todo el texto de los tickets se muestra como texto. */
import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { api, leerDetalle } from "../api/cliente.js";
import Cabecera from "../componentes/Cabecera.jsx";
import { useTitulo } from "../componentes/claseBody.js";
import { useSesion } from "../contexto/SesionContext.jsx";
import { claseBadge, formatearFechaHora, persona, puedeEditarTicket, SIN_AREA } from "../sesion/permisos.js";
import { rutaTicket } from "../rutas.js";
import {
  CATEGORIAS, ESTADOS, ESTADOS_TABLERO, FILAS_DESTACADAS, FILTROS_VACIOS, ORDEN_KEY, PRIORIDADES,
  buildTicketsUrl, claseCategoria, estadoFiltro, filtrosDeUrl, guardarPreferencia, hayFiltros,
  leerOrden, leerPreferencia, ordenarTickets, siguienteOrden, textoAntiguedad, textoTotal,
} from "../tickets/filtros.js";

const VISTA_KEY = "vista_listado";
const DENSIDAD_KEY = "densidad_listado";
const FILAS_ESQUELETO = 6;

const sinAsignar = (t) => t.assigned_to_id === null || t.assigned_to_id === undefined;

function Persona({ as: Etiqueta = "td", nombre, clase }) {
  const p = persona(nombre, clase);
  return <Etiqueta className={p.className} data-iniciales={p.iniciales}>{p.texto}</Etiqueta>;
}

function Badge({ valor }) {
  return <span className={claseBadge(valor)}>{valor}</span>;
}

function Opciones({ valores }) {
  return valores.map((v) => <option key={v} value={v}>{v}</option>);
}

/* Dos opciones como en la barra del listado (clase «activa» y aria-pressed). */
function Pestanas({ etiqueta, opciones, valor, onCambio, id, hidden }) {
  return (
    <div className="vista-tabs" role="group" aria-label={etiqueta} id={id} hidden={hidden}>
      {opciones.map(([clave, texto, idBoton]) => (
        <button key={clave} type="button" id={idBoton} className={`vista-tab${valor === clave ? " activa" : ""}`}
          aria-pressed={String(valor === clave)} onClick={() => onCambio(clave)}>{texto}</button>
      ))}
    </div>
  );
}

function FilasEsqueleto({ solicitante }) {
  const columnas = solicitante ? [0, 1, 4, 5, 6, 7] : [0, 1, 2, 3, 4, 5, 6, 7];
  return Array.from({ length: FILAS_ESQUELETO }, (_, i) => (
    <tr className="fila-esqueleto" key={`e${i}`}>
      {columnas.map((c) => <td key={c}><span className={`esqueleto-barra col-${c}`} /></td>)}
    </tr>
  ));
}

function EncabezadoOrden({ campo, texto, orden, onOrden, vistaEquipo }) {
  const activo = orden && orden.campo === campo;
  const sort = activo ? (orden.dir === "asc" ? "ascending" : "descending") : "none";
  return (
    <th aria-sort={sort} data-vista={vistaEquipo ? "equipo" : undefined}>
      <button type="button" className="orden-columna" data-orden={campo} onClick={() => onOrden(campo)}>{texto}</button>
    </th>
  );
}

function Tablero({ tickets, nombreAsignado }) {
  return (
    <div id="tablero" className="tablero" aria-label="Tickets por estado">
      {ESTADOS_TABLERO.map((estado) => {
        const propios = tickets.filter((t) => t.state === estado);
        return (
          <section className="tablero-columna" key={estado}>
            <h2 className="tablero-titulo">
              <span className={claseBadge(estado)}>{estado}</span>
              <span className="tablero-cuenta" aria-label={`${propios.length} tickets`}>{String(propios.length)}</span>
            </h2>
            <div className="tablero-lista">
              {propios.length === 0 && <p className="tablero-vacio">Sin tickets</p>}
              {propios.map((t) => {
                const nombre = nombreAsignado(t);
                return (
                  <Link key={t.id} to={rutaTicket(t.id)}
                    className={`tablero-tarjeta ${FILAS_DESTACADAS[t.priority] || ""}`.trim()}>
                    <span className="tablero-tarjeta-cabeza">
                      <span className="tablero-tarjeta-id">{`#${t.id}`}</span>
                      <Badge valor={t.priority} />
                    </span>
                    <span className="tablero-tarjeta-titulo">{t.title}</span>
                    {nombre === "—"
                      ? <span className="tablero-tarjeta-asignado sin-asignar">Sin asignar</span>
                      : <Persona as="span" nombre={nombre} clase="tablero-tarjeta-asignado" />}
                  </Link>
                );
              })}
            </div>
          </section>
        );
      })}
    </div>
  );
}

export default function Tickets() {
  const { user } = useSesion();
  const solicitante = Boolean(user && user.role === "Solicitante");
  const equipo = !solicitante;
  const navigate = useNavigate();
  const location = useLocation();
  useTitulo(solicitante ? "Mis solicitudes" : "Tickets");

  const [form, setForm] = useState(FILTROS_VACIOS);
  const formRef = useRef(form);
  formRef.current = form;
  const [soloMios, setSoloMios] = useState(false);
  const [antiguedad, setAntiguedad] = useState(0);
  const [usuarios, setUsuarios] = useState([]);
  const [areas, setAreas] = useState([]);
  const [listo, setListo] = useState(false);
  const [carga, setCarga] = useState({ estado: "cargando", tickets: [], total: 0, mensaje: "", conFiltros: false });
  const [orden, setOrden] = useState(leerOrden);
  const [vista, setVista] = useState(() => leerPreferencia(VISTA_KEY, ["tablero", "tabla"], "tabla"));
  const [densidad, setDensidad] = useState(() => leerPreferencia(DENSIDAD_KEY, ["compacta", "comoda"], "comoda"));
  const pedido = useRef(0);

  const usaTablero = vista === "tablero" && equipo;
  const nombres = new Map(usuarios.map((u) => [u.id, u.name]));
  const nombreAsignado = (t) => (sinAsignar(t) ? "—" : nombres.get(t.assigned_to_id) || `Usuario #${t.assigned_to_id}`);

  /* Una única petición por búsqueda; una respuesta vieja no pisa a la nueva. */
  const cargar = useCallback(async ({ filtros = formRef.current, mios, dias } = {}) => {
    const numero = ++pedido.current;
    const f = {
      ...filtros,
      state: estadoFiltro(filtros.state),
      mios,
      asignado: solicitante ? "" : filtros.asignado,
      area: solicitante ? "" : filtros.area,
      antiguedad: dias,
    };
    const conFiltros = hayFiltros(f);
    setCarga({ estado: "cargando", tickets: [], total: 0, mensaje: "", conFiltros });
    const fin = (datos) => { if (numero === pedido.current) setCarga({ conFiltros, total: 0, tickets: [], mensaje: "", ...datos }); };
    let response;
    try {
      response = await api(buildTicketsUrl(f));
    } catch {
      fin({ estado: "error", mensaje: "No se pudo conectar con el servidor. Verifique que esté en funcionamiento." });
      return;
    }
    if (!response.ok) {
      const detalle = await leerDetalle(response);
      fin({ estado: "error", mensaje: detalle ? `Error de API (${response.status}): ${detalle}` : `Error de API (${response.status}).` });
      return;
    }
    let tickets;
    try {
      tickets = await response.json();
    } catch {
      tickets = null;
    }
    if (!Array.isArray(tickets)) {
      fin({ estado: "error", mensaje: "Respuesta inválida del servidor." });
      return;
    }
    const crudo = response.headers && response.headers.get ? response.headers.get("X-Total-Count") : null;
    const cabecera = crudo === null || crudo === undefined || crudo === "" ? NaN : Number(crudo);
    const total = Number.isFinite(cabecera) ? cabecera : tickets.length;
    if (tickets.length === 0) {
      if (solicitante && !conFiltros) return fin({ estado: "sin-solicitudes", total });
      return fin({
        estado: "vacio", total,
        mensaje: conFiltros ? "No hay tickets que coincidan con los filtros." : "No hay tickets para mostrar.",
      });
    }
    fin({ estado: "listo", tickets, total });
    return undefined;
  }, [solicitante]);

  /* Usuarios (nombres y «Asignado a») y departamentos; después se aplican
     los filtros de la dirección y se pide la lista. */
  useEffect(() => {
    let vigente = true;
    const pedirUsuarios = api("/api/users")
      .then((r) => (r.ok ? r.json() : []))
      .then((lista) => (Array.isArray(lista) ? lista : []))
      .catch(() => []);
    const pedirAreas = equipo
      ? api("/api/areas").then((r) => (r.ok ? r.json() : [])).then((l) => (Array.isArray(l) ? l : [])).catch(() => [])
      : Promise.resolve([]);
    Promise.all([pedirUsuarios, pedirAreas]).then(([lista, listaAreas]) => {
      if (!vigente) return;
      setUsuarios(lista);
      setAreas(listaAreas);
      const { filtros, antiguedad: dias } = filtrosDeUrl(location.search, { solicitante, areas: listaAreas, usuarios: lista });
      const inicial = { ...FILTROS_VACIOS, ...filtros };
      setForm(inicial);
      setAntiguedad(dias);
      setListo(true);
      cargar({ filtros: inicial, mios: false, dias });
    });
    return () => { vigente = false; };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const cambiar = (campo) => (event) => setForm((f) => ({ ...f, [campo]: event.target.value }));
  const buscar = (event) => {
    event.preventDefault();
    cargar({ mios: soloMios, dias: antiguedad });
  };
  const limpiar = () => {
    setForm(FILTROS_VACIOS);
    setAntiguedad(0);
    setSoloMios(false);
    cargar({ filtros: FILTROS_VACIOS, mios: false, dias: 0 });
  };
  const quitarAntiguedad = () => {
    setAntiguedad(0);
    cargar({ mios: soloMios, dias: 0 });
  };
  const cambiarMios = (valor) => {
    const mios = valor === "mios";
    setSoloMios(mios);
    cargar({ mios, dias: antiguedad });
  };
  const cambiarOrden = (campo) => {
    const nuevo = siguienteOrden(orden, campo);
    guardarPreferencia(ORDEN_KEY, nuevo);
    setOrden(nuevo);
  };
  const cambiarVista = (valor) => { guardarPreferencia(VISTA_KEY, valor); setVista(valor); };
  const cambiarDensidad = (valor) => { guardarPreferencia(DENSIDAD_KEY, valor); setDensidad(valor); };

  const activos = usuarios
    .filter((u) => u.is_active !== false)
    .sort((a, b) => String(a.name).localeCompare(String(b.name), "es"));
  const ordenados = ordenarTickets(carga.tickets, orden);
  const sinSolicitudes = carga.estado === "sin-solicitudes";
  const yo = user;

  const celdaAsignado = (t) => {
    if (solicitante && sinAsignar(t)) return <td className="celda-pendiente celda-asignado">Pendiente de asignar</td>;
    if (solicitante && yo && yo.id !== undefined && t.assigned_to_id === yo.id) {
      return <td className="celda-asignado celda-asignado-usted">Asignado a usted</td>;
    }
    const nombre = nombreAsignado(t);
    return <Persona nombre={nombre} clase={nombre === "—" ? "celda-asignado sin-asignar" : "celda-asignado"} />;
  };

  return (
    <>
      <Cabecera className="cabecera-listado" idTitulo="titulo-listado" idSubtitulo="subtitulo-listado"
        titulo={solicitante ? "Mis solicitudes" : "Tickets"}
        subtitulo={solicitante ? "Consulte el estado de sus tickets de soporte" : "Consulta y gestión de los tickets de soporte"}
        centro={(
          <div className="listado-controles">
            {equipo && (
              <Pestanas etiqueta="Qué tickets ver" valor={soloMios ? "mios" : "todos"} onCambio={cambiarMios}
                opciones={[["todos", "Todos", "vista-todos"], ["mios", "Mis tickets", "vista-mios"]]} />
            )}
            {equipo && (
              <Pestanas etiqueta="Cómo ver los tickets" valor={vista} onCambio={cambiarVista}
                opciones={[["tabla", "Tabla", "ver-tabla"], ["tablero", "Tablero", "ver-tablero"]]} />
            )}
            <Pestanas etiqueta="Densidad de la tabla" id="densidad" hidden={usaTablero} valor={densidad} onCambio={cambiarDensidad}
              opciones={[["compacta", "Compacta", "densidad-compacta"], ["comoda", "Cómoda", "densidad-comoda"]]} />
          </div>
        )}
        acciones={solicitante && <Link to="/crear" id="nuevo-ticket-solicitante" className="enlace-boton">Nuevo ticket</Link>}
      />

      <main className="contenido">
        <form id="form-filtros" className="filtros" onSubmit={buscar}>
          <label className="campo campo-busqueda">
            <span>Buscar</span>
            <input type="search" id="search" name="search" placeholder="Título o descripción" autoComplete="off"
              value={form.search} onChange={cambiar("search")} />
          </label>
          {equipo && (
            <label className="campo">
              <span>Categoría</span>
              <select id="category" name="category" value={form.category} onChange={cambiar("category")}>
                <option value="">Todas</option><Opciones valores={CATEGORIAS} />
              </select>
            </label>
          )}
          {equipo && (
            <label className="campo">
              <span>Prioridad</span>
              <select id="priority" name="priority" value={form.priority} onChange={cambiar("priority")}>
                <option value="">Todas</option><Opciones valores={PRIORIDADES} />
              </select>
            </label>
          )}
          <label className="campo">
            <span>Estado</span>
            <select id="state" name="state" value={form.state} onChange={cambiar("state")}>
              <option value="">Todos</option>
              <option value="abiertos" title="Nuevo y En proceso">Abiertos</option>
              <Opciones valores={ESTADOS} />
            </select>
          </label>
          {equipo && (
            <label className="campo">
              <span>Asignado a</span>
              <select id="assigned" name="assigned" value={form.asignado} onChange={cambiar("asignado")}>
                <option value="">Todos</option>
                <option value="sin">Sin asignar</option>
                {activos.map((u) => <option key={u.id} value={String(u.id)}>{u.name}</option>)}
              </select>
            </label>
          )}
          {equipo && (
            <label className="campo">
              <span>Departamento</span>
              <select id="area" name="area" value={form.area} onChange={cambiar("area")}>
                <option value="">Todos</option>
                <option value="sin">{SIN_AREA}</option>
                {areas.map((a) => <option key={a.id} value={String(a.id)}>{a.name}</option>)}
              </select>
            </label>
          )}
          <label className="campo">
            <span>Fecha de creación</span>
            <input type="date" id="fecha" name="fecha" value={form.fecha} onChange={cambiar("fecha")} />
          </label>
          <div className="acciones">
            <button type="submit" id="buscar">Buscar</button>
            <button type="button" id="limpiar" className="secundario" onClick={limpiar}>Limpiar filtros</button>
          </div>
        </form>

        <p id="filtro-antiguedad" className="filtro-extra" hidden={!antiguedad}>
          <span id="filtro-antiguedad-texto">{textoAntiguedad(antiguedad)}</span>
          <button type="button" id="quitar-antiguedad" className="enlace-quitar" onClick={quitarAntiguedad}>Quitar</button>
        </p>

        <p id="estado-carga" className={`estado ${carga.estado}`} role="status" aria-live="polite"
          hidden={!(carga.estado === "error" || carga.estado === "vacio")}>
          {carga.estado === "error" || carga.estado === "vacio" ? carga.mensaje : ""}
        </p>

        <div id="sin-solicitudes" className="estado vacio sin-solicitudes" hidden={!sinSolicitudes}>
          <p>Todavía no ha creado solicitudes.</p>
          <Link to="/crear" className="enlace-boton">Nuevo ticket</Link>
        </div>

        <p id="total-tickets" className="total-listado" aria-live="polite" hidden={carga.total === 0}>
          {carga.total > 0 ? textoTotal(carga.total, carga.tickets.length) : ""}
        </p>

        <div className={`tabla-scroll${densidad === "compacta" ? " densidad-compacta" : ""}`} id="tabla-tickets"
          hidden={usaTablero || sinSolicitudes}>
          <table className="listado">
            <thead>
              <tr>
                <EncabezadoOrden campo="id" texto="ID" orden={orden} onOrden={cambiarOrden} />
                <EncabezadoOrden campo="title" texto="Título" orden={orden} onOrden={cambiarOrden} />
                {equipo && <th>Categoría</th>}
                {equipo && <EncabezadoOrden campo="priority" texto="Prioridad" orden={orden} onOrden={cambiarOrden} />}
                <EncabezadoOrden campo="state" texto="Estado" orden={orden} onOrden={cambiarOrden} />
                <th id="th-asignado">{solicitante ? "Atendido por" : "Asignado a"}</th>
                <EncabezadoOrden campo="created_at" texto="Fecha de creación" orden={orden} onOrden={cambiarOrden} />
                <th>Acción</th>
              </tr>
            </thead>
            <tbody id="lista-tickets">
              {(carga.estado === "cargando" || !listo) && <FilasEsqueleto solicitante={solicitante} />}
              {carga.estado === "listo" && ordenados.map((t) => (
                <tr key={t.id} className={equipo ? FILAS_DESTACADAS[t.priority] || undefined : undefined}>
                  <td className="celda-id"><Link className="enlace-tabla" to={rutaTicket(t.id)}>{t.id}</Link></td>
                  <td className="celda-titulo">{t.title}</td>
                  {equipo && <td className={claseCategoria(t.category)}>{t.category}</td>}
                  {equipo && <td className="celda-prioridad"><Badge valor={t.priority} /></td>}
                  <td className="celda-estado"><Badge valor={t.state} /></td>
                  {celdaAsignado(t)}
                  <td className="celda-fecha">{formatearFechaHora(t.created_at)}</td>
                  <td className="celda-accion">
                    <button type="button" className="btn-accion" onClick={() => navigate(rutaTicket(t.id))}>
                      {puedeEditarTicket(user, t) ? "Editar" : "Ver"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {usaTablero && carga.estado === "listo" && <Tablero tickets={ordenados} nombreAsignado={nombreAsignado} />}
        {usaTablero && carga.estado !== "listo" && <div id="tablero" className="tablero" aria-label="Tickets por estado" />}
      </main>
    </>
  );
}
