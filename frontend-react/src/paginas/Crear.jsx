/* Nuevo ticket (port de frontend/crear.html + js/crear.js): título,
   descripción, departamento, categoría, prioridad y adjuntos. Los adjuntos
   se eligen antes (con tamaño y ✕ para quitar; las fotos se achican al
   elegirlas) y se suben uno por uno recién creado el ticket. Si alguno falla
   el ticket queda creado igual: se dice cuál y por qué, con el enlace al
   detalle para reintentarlo. */
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api/cliente.js";
import { avisoPendiente, useAvisos } from "../avisos/Avisos.jsx";
import { ADJ_ACCEPT, ADJ_POR_DEFECTO, achicarImagen, adjProblema, adjSubirUno, esTactil, formatoTamano } from "../adjuntos/adjuntos.js";
import Cabecera, { Migas } from "../componentes/Cabecera.jsx";
import { useTitulo } from "../componentes/claseBody.js";
import { rutaTicket } from "../rutas.js";
import { CATEGORIAS } from "../tickets/filtros.js";

const MAX_ADJUNTOS = ADJ_POR_DEFECTO.max_archivos;
const OPCIONES_PRIORIDAD = [["Baja", "prioridad-baja"], ["Media", "prioridad-media"], ["Alta", "prioridad-alta"], ["Crítica", "prioridad-critica"]];

export function validarNuevo(payload, hayAreas) {
  if (!payload.title && !payload.description) return "El título y la descripción son obligatorios.";
  if (!payload.title) return "El título es obligatorio.";
  if (!payload.description) return "La descripción es obligatoria.";
  if (hayAreas && !payload.area_id) return "Elija el departamento del ticket.";
  return "";
}

/* 422 de FastAPI legible (o el motivo en texto, como «Elija el departamento»). */
export function formatValidationCrear(detail) {
  if (detail && typeof detail.detail === "string") return detail.detail;
  if (!detail || !Array.isArray(detail.detail)) return "El servidor rechazó los datos enviados. Revise el formulario.";
  const mensajes = detail.detail.map((error) => {
    const campo = Array.isArray(error.loc) ? error.loc.slice(1).join(".") : "";
    return campo ? `${campo}: ${error.msg}` : error.msg;
  });
  return `Revise los datos enviados. ${mensajes.join(" | ")}`;
}

/* El motivo sin repetir el nombre del archivo. */
function motivoSinNombre(nombre, motivo) {
  const limpio = String(motivo || "").replace(`«${nombre}»: `, "").replace(`«${nombre}» `, "");
  return limpio.charAt(0).toUpperCase() + limpio.slice(1);
}

export default function Crear() {
  useTitulo("Nuevo ticket");
  const navigate = useNavigate();
  const { avisar } = useAvisos();
  const [form, setForm] = useState({ title: "", description: "", category: "Hardware", priority: "Media", area: "" });
  const [areas, setAreas] = useState(null); /* null: cargando */
  const [elegidos, setElegidos] = useState([]);
  const [errorAdjuntos, setErrorAdjuntos] = useState("");
  const [preparando, setPreparando] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const [estado, setEstado] = useState(null);
  const [resultado, setResultado] = useState(null); /* { id, fallas, subidos } */
  const archivos = useRef(null);
  const camara = useRef(null);
  const lista = useRef(null);
  const botonAdjuntar = useRef(null);
  const tituloResultado = useRef(null);
  const enviandoRef = useRef(false);

  useEffect(() => {
    let vigente = true;
    api("/api/areas")
      .then((r) => (r.ok ? r.json() : []))
      .then((l) => { if (vigente) setAreas(Array.isArray(l) ? l : []); })
      .catch(() => { if (vigente) setAreas([]); });
    return () => { vigente = false; };
  }, []);

  useEffect(() => {
    if (resultado && tituloResultado.current) tituloResultado.current.focus();
  }, [resultado]);

  const hayAreas = Boolean(areas && areas.length);
  const cambiar = (campo) => (e) => setForm({ ...form, [campo]: e.target.value });

  const agregar = async (listaArchivos, input) => {
    const nuevos = Array.from(listaArchivos || []);
    if (nuevos.length === 0 || enviandoRef.current) return;
    const errores = [];
    const aceptados = [...elegidos];
    setPreparando(true);
    try {
      for (const original of nuevos) {
        if (aceptados.length >= MAX_ADJUNTOS) {
          errores.push(`Se pueden adjuntar hasta ${MAX_ADJUNTOS} archivos por ticket.`);
          break;
        }
        const archivo = await achicarImagen(original);
        const problema = adjProblema(archivo);
        if (problema) errores.push(problema);
        else aceptados.push(archivo);
      }
    } finally {
      setPreparando(false);
      if (input) input.value = "";
    }
    setElegidos(aceptados);
    setErrorAdjuntos(errores.join(" "));
  };

  const quitar = (indice) => {
    if (enviandoRef.current) return;
    const restantes = elegidos.filter((_, i) => i !== indice);
    setElegidos(restantes);
    setErrorAdjuntos("");
    /* El foco pasa al ✕ que quedó en ese lugar (o a «Adjuntar archivos»). */
    setTimeout(() => {
      const botones = lista.current ? lista.current.querySelectorAll(".adjunto-quitar") : [];
      const destino = botones[Math.min(indice, restantes.length - 1)] || botonAdjuntar.current;
      if (destino) destino.focus();
    }, 0);
  };

  const crear = async (event) => {
    event.preventDefault();
    if (enviandoRef.current || preparando) return;
    const payload = { title: form.title.trim(), description: form.description.trim(), category: form.category, priority: form.priority };
    if (/^\d+$/.test(form.area)) payload.area_id = Number(form.area);
    const error = validarNuevo(payload, hayAreas);
    if (error) {
      setEstado(null);
      avisar(error, "error");
      return;
    }
    enviandoRef.current = true;
    setEnviando(true);
    setEstado({ texto: "Guardando...", tipo: "cargando" });
    let listo = false;
    try {
      const response = await api("/api/tickets", { method: "POST", body: payload });
      if (response.status === 422) {
        setEstado(null);
        avisar(formatValidationCrear(await response.json().catch(() => null)), "error");
        return;
      }
      if (!response.ok) {
        setEstado(null);
        avisar(`No se pudo crear el ticket (HTTP ${response.status}). Inténtelo de nuevo.`, "error");
        return;
      }
      const ticket = await response.json();
      /* Desde acá el ticket existe: el formulario no se vuelve a habilitar. */
      listo = true;
      const fallas = [];
      for (const [i, archivo] of elegidos.entries()) {
        setEstado({ texto: `Ticket #${ticket.id} creado. Subiendo adjunto ${i + 1} de ${elegidos.length}: ${archivo.name}…`, tipo: "cargando" });
        const motivo = await adjSubirUno(ticket.id, archivo);
        if (motivo) fallas.push({ nombre: archivo.name, motivo: motivoSinNombre(archivo.name, motivo) });
      }
      if (fallas.length) {
        setEstado(null);
        setResultado({ id: ticket.id, fallas, subidos: elegidos.length - fallas.length });
        const no = fallas.length === 1 ? "No se pudo subir 1 adjunto" : `No se pudieron subir ${fallas.length} adjuntos`;
        avisar(`Ticket #${ticket.id} creado. ${no}.`, "error");
        return;
      }
      const cantidad = elegidos.length;
      const conAdjuntos = cantidad === 1 ? " con 1 adjunto" : cantidad ? ` con ${cantidad} adjuntos` : "";
      avisoPendiente(`Ticket #${ticket.id} guardado correctamente${conAdjuntos}.`);
      setEstado({ texto: "Ticket guardado. Abriendo el listado...", tipo: "cargando" });
      navigate("/");
    } catch {
      setEstado(null);
      avisar("Error al comunicarse con la API.", "error");
    } finally {
      if (!listo) {
        enviandoRef.current = false;
        setEnviando(false);
      }
    }
  };

  const textoResultado = () => {
    if (!resultado) return "";
    const { fallas, subidos } = resultado;
    const no = fallas.length === 1 ? "No se pudo subir 1 adjunto" : `No se pudieron subir ${fallas.length} adjuntos`;
    return subidos
      ? `${no}; ${subidos === 1 ? "el otro quedó guardado" : `los otros ${subidos} quedaron guardados`}. Puede reintentarlos desde el detalle del ticket.`
      : `${no}. Puede reintentarlos desde el detalle del ticket.`;
  };

  const primeraArea = areas === null ? "Cargando departamentos…"
    : hayAreas ? "Elija un departamento" : "No se pudieron cargar: se elige por la categoría";
  const tactil = esTactil();

  return (
    <>
      <Cabecera claseTitulo="" titulo="Nuevo ticket" subtitulo="Registro de una nueva solicitud de soporte"
        migas={<Migas actual="Nuevo ticket" />}
        acciones={<Link to="/" className="enlace-boton secundario">Volver al listado</Link>} />

      <main className="contenido">
        <form id="form-crear" className="filtros formulario formulario-crear formulario-ticket" noValidate onSubmit={crear} hidden={Boolean(resultado)}>
          <div className="crear-columnas">
            <div className="crear-columna crear-principal">
              <label className="campo">
                <span>Título *</span>
                <input type="text" id="title" name="title" required maxLength={200}
                  placeholder="Ej.: La impresora del 2.º piso no imprime" value={form.title} onChange={cambiar("title")} />
              </label>
              <label className="campo campo-descripcion">
                <span>Descripción *</span>
                <textarea id="description" name="description" required
                  placeholder="Qué sucede, desde cuándo, qué mensaje aparece y qué intentó."
                  value={form.description} onChange={cambiar("description")} />
              </label>
            </div>

            <div className="crear-columna crear-lateral">
              <div className="campo">
                <label htmlFor="area"><span>Departamento *</span></label>
                <select id="area" name="area" required={hayAreas} aria-describedby="ayuda-area" value={form.area} onChange={cambiar("area")}>
                  <option value="">{primeraArea}</option>
                  {(areas || []).map((a) => <option key={a.id} value={String(a.id)}>{a.name}</option>)}
                </select>
                <ul id="ayuda-area" className="ayuda-campo ayuda-areas">
                  <li><strong>Soporte IT</strong>: computadoras, impresoras, programas.</li>
                  <li><strong>Redes e Infraestructura</strong>: internet, wifi, servidores, VPN.</li>
                  <li><strong>Ciberseguridad</strong>: accesos, contraseñas, cuentas, incidentes de seguridad.</li>
                  <li><strong>Programación</strong>: sistemas internos, Odoo, desarrollos y reportes.</li>
                </ul>
              </div>

              <label className="campo">
                <span>Categoría</span>
                <select id="category" name="category" value={form.category} onChange={cambiar("category")}>
                  {CATEGORIAS.map((c) => <option key={c} value={c}>{c}</option>)}
                </select>
              </label>

              <fieldset className="campo campo-prioridad" aria-describedby="ayuda-prioridad">
                <legend>Prioridad</legend>
                <div className="opciones-prioridad">
                  {OPCIONES_PRIORIDAD.map(([valor, clase]) => (
                    <label key={valor} className={`opcion-prioridad ${clase}`}>
                      <input type="radio" name="opcion-prioridad" value={valor} checked={form.priority === valor}
                        onChange={() => setForm({ ...form, priority: valor })} />
                      <span>{valor}</span>
                    </label>
                  ))}
                </div>
                <input type="hidden" id="priority" name="priority" value={form.priority} />
                <small id="ayuda-prioridad" className="ayuda-campo">Crítica: nadie puede trabajar o el servicio está caído.</small>
              </fieldset>

              <div className="campo campo-adjuntos" role="group" aria-labelledby="crear-adj-titulo">
                <span id="crear-adj-titulo">Adjuntos (opcional)</span>
                <div className="acciones">
                  <button type="button" id="crear-adj-subir" className="secundario" aria-describedby="ayuda-adjuntos" ref={botonAdjuntar}
                    disabled={enviando || elegidos.length >= MAX_ADJUNTOS} onClick={() => archivos.current.click()}>Adjuntar archivos</button>
                  <button type="button" id="crear-adj-foto" className="secundario" hidden={!tactil} disabled={enviando}
                    onClick={() => camara.current.click()}>Sacar foto</button>
                  <input type="file" id="crear-adj-archivos" multiple hidden accept={ADJ_ACCEPT} ref={archivos}
                    data-testid="crear-adj-archivos" onChange={(e) => agregar(e.target.files, e.target)} />
                  <input type="file" id="crear-adj-camara" accept="image/*" capture="environment" hidden ref={camara}
                    onChange={(e) => agregar(e.target.files, e.target)} />
                </div>
                <small id="ayuda-adjuntos" className="ayuda-campo">Hasta 4 MB cada uno y 10 por ticket.</small>
                <p id="crear-adj-estado" className={errorAdjuntos ? "estado error" : "estado"} role="status" aria-live="polite" hidden={!errorAdjuntos}>
                  {errorAdjuntos}
                </p>
                <ul id="crear-adj-lista" className="adjuntos-lista adjuntos-elegidos" aria-label="Archivos elegidos" hidden={elegidos.length === 0} ref={lista}>
                  {elegidos.map((archivo, indice) => (
                    <li className="adjunto adjunto-elegido" key={`${archivo.name}-${indice}`}>
                      <div className="adjunto-datos">
                        <span className="adjunto-nombre">{archivo.name}</span>
                        <span className="adjunto-meta">{formatoTamano(archivo.size)}</span>
                      </div>
                      <button type="button" className="adjunto-quitar" aria-label={`Quitar ${archivo.name}`} onClick={() => quitar(indice)}>✕</button>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </div>

          <div className="acciones acciones-crear">
            <button type="submit" id="guardar" disabled={enviando || preparando}>Crear ticket</button>
          </div>
        </form>

        <section id="crear-resultado" className="seccion crear-resultado" aria-labelledby="crear-resultado-titulo" hidden={!resultado}>
          <h2 id="crear-resultado-titulo" tabIndex={-1} ref={tituloResultado}>{resultado ? `Ticket #${resultado.id} creado` : ""}</h2>
          <p id="crear-resultado-texto">{textoResultado()}</p>
          <ul id="crear-resultado-fallas" className="crear-resultado-fallas">
            {(resultado ? resultado.fallas : []).map(({ nombre, motivo }, i) => (
              <li key={i}><strong>{nombre}</strong>{`: ${motivo}`}</li>
            ))}
          </ul>
          <div className="acciones">
            <Link id="crear-resultado-detalle" to={resultado ? rutaTicket(resultado.id) : "/"} className="enlace-boton">Ir al ticket y reintentar</Link>
            <Link to="/" className="enlace-boton secundario">Volver al listado</Link>
          </div>
        </section>

        <p id="estado-carga" className={estado ? `estado ${estado.tipo}` : "estado"} role="status" aria-live="polite" hidden={!estado || Boolean(resultado)}>
          {estado ? estado.texto : ""}
        </p>
      </main>
    </>
  );
}
