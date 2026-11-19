/* Métricas (port de frontend/metricas.html + js/metricas.js), solo
   Administrador: informe con Resumen (contra el período anterior),
   Situación de hoy, Distribución, Por día y Por técnico. Cada gráfico tiene
   su tabla en «Ver datos»; si los gráficos no se pueden dibujar, las tablas
   quedan abiertas. «Imprimir» imprime solo el informe, en grises. */
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api/cliente.js";
import Cabecera from "../componentes/Cabecera.jsx";
import { useTitulo } from "../componentes/claseBody.js";
import { SIN_AREA } from "../sesion/permisos.js";
import {
  diaCorto, fechaLarga, filasCategoria, filasHoy, filasResumen, filasTecnicos, rangoAnterior, rangoPorDefecto,
  textoAlcance, urlMetricas,
} from "../metricas/calculos.js";
import { COLORES_IMPRESION, barras, coloresDelTema } from "../metricas/graficos.js";

function Tabla({ id, encabezados, filas, textos = [0] }) {
  return (
    <table id={id} className="tabla-informe">
      <thead>
        <tr>{encabezados.map((e, i) => <th key={e} scope="col" className={textos.includes(i) ? undefined : "num"}>{e}</th>)}</tr>
      </thead>
      <tbody>
        {filas.map(({ celdas, total = false, vacia = false }, n) => (
          <tr key={n} className={total ? "fila-total" : undefined}>
            {vacia
              ? <td className="celda-vacia" colSpan={encabezados.length}>{celdas[0]}</td>
              : celdas.map((valor, i) => (i === 0
                ? <th key={i} scope="row">{String(valor)}</th>
                : <td key={i} className={textos.includes(i) ? undefined : "num"}>{String(valor)}</td>))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function TablaDatos({ encabezados, filas }) {
  return (
    <table className="tabla-informe">
      <thead><tr>{encabezados.map((e, i) => <th key={e} className={i ? "num" : undefined}>{e}</th>)}</tr></thead>
      <tbody>{filas.map((valores, n) => <tr key={n}>{valores.map((v, i) => <td key={i} className={i ? "num" : undefined}>{String(v)}</td>)}</tr>)}</tbody>
    </table>
  );
}

function Grafico({ id, ancho = false, titulo, sub, etiqueta, children, refLienzo, disponible }) {
  return (
    <figure className={`informe-grafico${ancho ? " ancho" : ""}`} id={id}>
      <figcaption>{titulo}{sub && <> <span>{sub}</span></>}</figcaption>
      <div className="grafico-lienzo" hidden={!disponible}><canvas aria-label={etiqueta} role="img" ref={refLienzo} /></div>
      <details className="grafico-datos" open={!disponible}><summary>Ver datos</summary><div>{children}</div></details>
    </figure>
  );
}

const ENC_RESUMEN = ["Indicador", "Este período", "Período anterior", "Variación"];

export default function Metricas() {
  useTitulo("Métricas");
  const rango = useRef(rangoPorDefecto()).current;
  const [desde, setDesde] = useState(rango.desde);
  const [hasta, setHasta] = useState(rango.hasta);
  const [area, setArea] = useState("");
  const [areas, setAreas] = useState(null);
  const [datos, setDatos] = useState(null);
  const [anteriores, setAnteriores] = useState(null);
  const [alcance, setAlcance] = useState(textoAlcance(null, null, "Todos"));
  const [estado, setEstado] = useState(null);
  const [cargando, setCargando] = useState(false);
  const [graficosOk, setGraficosOk] = useState(true);
  const lienzoEstado = useRef(null);
  const lienzoDia = useRef(null);
  const graficos = useRef([]);
  const filtros = useRef({ desde, hasta, area });
  filtros.current = { desde, hasta, area };

  const nombreArea = (valor, lista = areas || []) => {
    if (!valor) return "Todos";
    if (valor === "sin") return SIN_AREA;
    const a = lista.find((x) => String(x.id) === valor);
    return a ? a.name : "Todos";
  };

  const dibujar = useCallback((d, colores = coloresDelTema()) => {
    graficos.current.forEach((g) => g.destroy());
    graficos.current = [];
    if (!d || !lienzoEstado.current || !lienzoDia.current) return false;
    try {
      graficos.current = [
        barras(lienzoEstado.current, d.por_estado.map((e) => e.nombre), d.por_estado.map((e) => e.total), colores),
        barras(lienzoDia.current, d.por_dia.map((x) => diaCorto(x.fecha)), d.por_dia.map((x) => x.total), colores, { muchas: d.por_dia.length > 31 }),
      ];
      return true;
    } catch {
      graficos.current = [];
      return false;
    }
  }, []);

  const cargar = useCallback(async (f = filtros.current, lista) => {
    if (!f.desde || !f.hasta) {
      setEstado({ texto: "Seleccione las dos fechas.", tipo: "error" });
      return;
    }
    setCargando(true);
    setEstado(null);
    const previo = rangoAnterior(f.desde, f.hasta);
    const pedirAnteriores = async () => {
      try {
        const r = await api(urlMetricas(previo.desde, previo.hasta, f.area));
        if (!r.ok) return null;
        const x = await r.json();
        return x && x.tarjetas ? x.tarjetas : null;
      } catch {
        return null;
      }
    };
    try {
      const [response, previos] = await Promise.all([api(urlMetricas(f.desde, f.hasta, f.area)), pedirAnteriores()]);
      const cuerpo = await response.json().catch(() => null);
      if (response.ok && cuerpo) {
        setDatos(cuerpo);
        setAnteriores(previos);
        setAlcance(textoAlcance(cuerpo.desde, cuerpo.hasta, nombreArea(f.area, lista)));
      } else if (response.status === 403) {
        setEstado({ texto: "Su rol no tiene permiso para ver las métricas.", tipo: "error" });
      } else {
        const detalle = cuerpo && typeof cuerpo.detail === "string" ? cuerpo.detail : "";
        setEstado({ texto: detalle || `No se pudieron cargar las métricas (${response.status}).`, tipo: "error" });
      }
    } catch {
      setEstado({ texto: "Error al comunicarse con la API.", tipo: "error" });
    } finally {
      setCargando(false);
    }
  }, [areas]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    let vigente = true;
    (async () => {
      let lista = [];
      try {
        const r = await api("/api/areas");
        lista = r.ok ? await r.json() : [];
      } catch {
        lista = [];
      }
      if (!vigente) return;
      lista = Array.isArray(lista) ? lista : [];
      setAreas(lista);
      cargar(filtros.current, lista);
    })();
    return () => { vigente = false; };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  /* Con datos nuevos se dibujan; con el tema o al imprimir, se redibujan. */
  useEffect(() => {
    if (!datos) return undefined;
    const ok = dibujar(datos);
    setGraficosOk(ok);
    setEstado(ok ? null : { texto: "No se pudieron cargar los gráficos. Los datos se muestran en tablas.", tipo: "vacio" });
    const tema = () => dibujar(datos);
    const antes = () => dibujar(datos, COLORES_IMPRESION);
    const despues = () => dibujar(datos);
    document.addEventListener("tema-cambiado", tema);
    window.addEventListener("beforeprint", antes);
    window.addEventListener("afterprint", despues);
    return () => {
      document.removeEventListener("tema-cambiado", tema);
      window.removeEventListener("beforeprint", antes);
      window.removeEventListener("afterprint", despues);
    };
  }, [datos, dibujar]);
  useEffect(() => () => graficos.current.forEach((g) => g.destroy()), []);

  const t = datos ? datos.tarjetas : null;
  return (
    <>
      <Cabecera claseTitulo="" titulo="Métricas" subtitulo="Indicadores de la mesa de soporte: situación actual y resultados del período" />
      <main className="contenido metricas">
        <form id="form-rango" className="filtros metricas-rango" onSubmit={(e) => { e.preventDefault(); cargar(); }}>
          <label className="campo">
            <span>Desde</span>
            <input type="date" id="desde" name="desde" required max={rango.hasta} value={desde} onChange={(e) => setDesde(e.target.value)} />
          </label>
          <label className="campo">
            <span>Hasta</span>
            <input type="date" id="hasta" name="hasta" required max={rango.hasta} value={hasta} onChange={(e) => setHasta(e.target.value)} />
          </label>
          <label className="campo">
            <span>Departamento</span>
            <select id="m-area" name="area" value={area}
              onChange={(e) => { setArea(e.target.value); cargar({ ...filtros.current, area: e.target.value }); }}>
              <option value="">Todos</option>
              <option value="sin">{SIN_AREA}</option>
              {(areas || []).map((a) => <option key={a.id} value={String(a.id)}>{a.name}</option>)}
            </select>
          </label>
          <div className="acciones">
            <button type="submit" id="aplicar" disabled={cargando}>Aplicar</button>
            <button type="button" id="imprimir-informe" className="secundario" onClick={() => window.print()}>Imprimir</button>
          </div>
        </form>

        <p id="estado-carga" className={estado && estado.tipo ? `estado ${estado.tipo}` : "estado"} role="status" aria-live="polite" hidden={!estado}>
          {estado ? estado.texto : ""}
        </p>

        <article id="informe" className={`informe${cargando ? " esqueleto-activo" : ""}`} aria-labelledby="informe-titulo" aria-busy={cargando ? "true" : "false"}>
          <header className="informe-encabezado">
            <h2 id="informe-titulo">Indicadores de la mesa de soporte</h2>
            <p id="informe-alcance" className="informe-alcance">{alcance}</p>
          </header>

          <section className="informe-seccion" aria-labelledby="s-resumen">
            <h3 id="s-resumen" className="informe-seccion-titulo">Resumen</h3>
            <div className="informe-tabla">
              <Tabla id="tabla-resumen" encabezados={ENC_RESUMEN} filas={t ? filasResumen(t, anteriores) : []} />
            </div>
          </section>

          <section className="informe-seccion" aria-labelledby="s-hoy">
            <h3 id="s-hoy" className="informe-seccion-titulo">Situación de hoy</h3>
            <div className="informe-tabla">
              <Tabla id="tabla-hoy" encabezados={["Estado", "Tickets", "% del total abierto"]} filas={t ? filasHoy(t) : []} />
            </div>
            <p className="informe-nota">Abiertos = Nuevo + En proceso, al momento de consultar.</p>
          </section>

          <section className="informe-seccion" aria-labelledby="s-distribucion">
            <h3 id="s-distribucion" className="informe-seccion-titulo">Distribución</h3>
            <div className="informe-columnas">
              <Grafico id="g-estado" titulo="Tickets por estado" sub="creados en el período, según su estado actual" etiqueta="Tickets por estado"
                refLienzo={lienzoEstado} disponible={graficosOk}>
                {datos && <TablaDatos encabezados={["Estado", "Tickets"]} filas={datos.por_estado.map((e) => [e.nombre, e.total])} />}
              </Grafico>
              <div className="informe-bloque">
                <h4 className="informe-bloque-titulo">Tickets por categoría <span>creados en el período</span></h4>
                <div className="informe-tabla">
                  <Tabla id="tabla-categoria" encabezados={["Categoría", "Tickets", "%"]} filas={datos ? filasCategoria(datos.por_categoria) : []} />
                </div>
              </div>
            </div>
          </section>

          <section className="informe-seccion" aria-labelledby="s-dia">
            <h3 id="s-dia" className="informe-seccion-titulo">Por día</h3>
            <Grafico id="g-dia" ancho titulo="Tickets creados por día" etiqueta="Tickets creados por día" refLienzo={lienzoDia} disponible={graficosOk}>
              {datos && <TablaDatos encabezados={["Día", "Tickets creados"]} filas={datos.por_dia.map((d) => [fechaLarga(d.fecha), d.total])} />}
            </Grafico>
          </section>

          <section className="informe-seccion" aria-labelledby="s-tecnico">
            <h3 id="s-tecnico" className="informe-seccion-titulo">Por técnico</h3>
            <div className="informe-tabla">
              <Tabla id="tabla-tecnicos" encabezados={["Técnico", "Departamento", "Abiertos hoy", "Resueltos en el período"]}
                filas={datos ? filasTecnicos(datos) : []} textos={[0, 1]} />
            </div>
          </section>
        </article>
      </main>
    </>
  );
}
