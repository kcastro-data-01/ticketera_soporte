/* Usuarios (port de frontend/usuarios.html + js/usuarios.js), solo
   Administrador: listado con los desactivados, agregar, editar (rol y
   departamento), desactivar y reactivar. La contraseña solo con
   LOGIN_LOCAL=true. Una sola ventana <dialog> para agregar y editar. */
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { api } from "../api/cliente.js";
import { useAvisos } from "../avisos/Avisos.jsx";
import Cabecera from "../componentes/Cabecera.jsx";
import { useConfirmar } from "../componentes/Confirmar.jsx";
import { useTitulo } from "../componentes/claseBody.js";
import { useSesion } from "../contexto/SesionContext.jsx";
import { persona } from "../sesion/permisos.js";
import {
  ROLES_IT_USUARIOS, areaElegida, campoDelError, claseRol, mensajeDeError, textoAreaUsuario, validarPassword, validarUsuario,
} from "../usuarios/reglas.js";

const SIN_CONEXION = "No se pudo conectar con el servidor. Verifique que esté en funcionamiento.";
const VACIO = { id: "", nombre: "", email: "", rol: "Técnico", area: "", password: "" };

/* Un campo con su error debajo (aria-invalid y foco si corresponde). */
function Campo({ etiqueta, id, error, children, className = "campo", hidden }) {
  return (
    <label className={className} hidden={hidden}>
      <span>{etiqueta}</span>
      {children}
      {id && <small id={`error-${id}`} className="error-campo" role="alert" hidden={!error}>{error || ""}</small>}
    </label>
  );
}

function Formulario({ tipo, visible, datos, setDatos, errores, areas, loginLocal, ocupado, onEnviar, onCancelar, refs }) {
  const editar = tipo === "editar";
  const p = editar ? "editar-" : "";
  const cambiar = (campo) => (e) => setDatos({ ...datos, [campo]: e.target.value });
  const esIT = ROLES_IT_USUARIOS.includes(datos.rol);
  const roles = editar ? ["Administrador", "Técnico", "Solicitante"] : ["Técnico", "Administrador", "Solicitante"];
  return (
    <form id={editar ? "form-editar-usuario" : "form-usuario"} className="formulario-usuario" noValidate onSubmit={onEnviar} hidden={!visible}>
      {editar && <input type="hidden" id="editar-id" name="id" value={datos.id} />}
      <div className="campos-dos">
        <Campo etiqueta="Nombre *" id={`${p}nombre`} error={errores.nombre}>
          <input type="text" id={`${p}nombre`} name="nombre" required maxLength={120} placeholder="Nombre y apellido"
            aria-describedby={`error-${p}nombre`} aria-invalid={errores.nombre ? "true" : undefined} ref={refs.nombre}
            value={datos.nombre} onChange={cambiar("nombre")} />
        </Campo>
        <Campo etiqueta="Correo electrónico *" id={`${p}email`} error={errores.email}>
          <input type="email" id={`${p}email`} name="email" required maxLength={255} placeholder="nombre@data.cr"
            aria-describedby={`error-${p}email`} aria-invalid={errores.email ? "true" : undefined} ref={refs.email}
            value={datos.email} onChange={cambiar("email")} />
        </Campo>
        <Campo etiqueta="Rol *" id={`${p}rol`} error={errores.rol}>
          <select id={`${p}rol`} name="rol" aria-describedby={`error-${p}rol`} aria-invalid={errores.rol ? "true" : undefined}
            ref={refs.rol} value={datos.rol} onChange={cambiar("rol")}>
            {roles.map((r) => <option key={r} value={r}>{r}</option>)}
          </select>
        </Campo>
        <Campo etiqueta="Departamento" className="campo campo-area" hidden={!esIT}>
          <select id={`${p}area`} name="area" disabled={!esIT} value={datos.area} onChange={cambiar("area")}>
            <option value="">Sin departamento</option>
            {areas.map((a) => <option key={a.id} value={String(a.id)}>{a.name}</option>)}
          </select>
        </Campo>
        <Campo etiqueta={editar ? "Nueva contraseña" : "Contraseña *"} id={`${p}password`} error={errores.password}
          className="campo solo-login-local" hidden={!loginLocal}>
          <input type="password" id={`${p}password`} name="password" minLength={6} maxLength={72} autoComplete="new-password"
            placeholder={editar ? "Vacía: no cambia" : "Entre 6 y 72 caracteres"} aria-describedby={`error-${p}password`}
            aria-invalid={errores.password ? "true" : undefined} ref={refs.password}
            value={datos.password} onChange={cambiar("password")} />
        </Campo>
      </div>
      <div className="acciones ventana-acciones">
        <button type="button" id={editar ? "cancelar-edicion" : "cancelar-usuario"} className="secundario" onClick={onCancelar}>Cancelar</button>
        <button type="submit" id={editar ? "guardar-edicion" : "crear"} disabled={ocupado}>{editar ? "Guardar cambios" : "Agregar usuario"}</button>
      </div>
    </form>
  );
}

export default function Usuarios() {
  useTitulo("Usuarios");
  const { user: sesion } = useSesion();
  const { avisar } = useAvisos();
  const confirmar = useConfirmar();
  const [usuarios, setUsuarios] = useState([]);
  const [estado, setEstado] = useState({ texto: "Cargando usuarios...", tipo: "cargando" });
  const [areas, setAreas] = useState([]);
  const [loginLocal, setLoginLocal] = useState(false);
  const [modo, setModo] = useState(null); /* null | "agregar" | "editar" */
  const [agregar, setAgregar] = useState(VACIO);
  const [editar, setEditar] = useState(VACIO);
  const [errores, setErrores] = useState({});
  const [ocupado, setOcupado] = useState(false);
  const ocupadoRef = useRef(false);
  const dialogo = useRef(null);
  const refsAgregar = { nombre: useRef(null), email: useRef(null), rol: useRef(null), password: useRef(null) };
  const refsEditar = { nombre: useRef(null), email: useRef(null), rol: useRef(null), password: useRef(null) };
  const enfocarCampo = useRef(null);

  const cargar = useCallback(async () => {
    setEstado({ texto: "Cargando usuarios...", tipo: "cargando" });
    try {
      const response = await api("/api/users?todos=true");
      const payload = await response.json().catch(() => null);
      if (!response.ok) return setEstado({ texto: mensajeDeError(response, payload), tipo: "error" });
      if (!Array.isArray(payload)) return setEstado({ texto: "Respuesta inválida del servidor.", tipo: "error" });
      setUsuarios(payload);
      setEstado(payload.length ? null : { texto: "No hay usuarios registrados.", tipo: "vacio" });
    } catch {
      setEstado({ texto: SIN_CONEXION, tipo: "error" });
    }
    return undefined;
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const r = await fetch("/api/auth/config");
        setLoginLocal(r.ok && Boolean((await r.json()).login_local));
      } catch {
        setLoginLocal(false);
      }
      try {
        const r = await api("/api/areas");
        const lista = r.ok ? await r.json() : [];
        setAreas(Array.isArray(lista) ? lista : []);
      } catch {
        setAreas([]);
      }
      await cargar();
    })();
  }, [cargar]);

  /* La ventana: showModal() deja el foco adentro y Escape la cierra. */
  useLayoutEffect(() => {
    const d = dialogo.current;
    if (!d) return;
    if (modo && !d.open) {
      if (typeof d.showModal === "function") d.showModal();
      else d.setAttribute("open", "");
    }
    if (!modo && d.open) {
      if (typeof d.close === "function") d.close();
      else d.removeAttribute("open");
    }
    if (modo) {
      const refs = modo === "editar" ? refsEditar : refsAgregar;
      if (refs.nombre.current) refs.nombre.current.focus();
    }
  }, [modo]); // eslint-disable-line react-hooks/exhaustive-deps

  useLayoutEffect(() => {
    if (!enfocarCampo.current) return;
    const refs = modo === "editar" ? refsEditar : refsAgregar;
    const ref = refs[enfocarCampo.current];
    if (ref && ref.current) ref.current.focus();
    enfocarCampo.current = null;
  }, [errores]); // eslint-disable-line react-hooks/exhaustive-deps

  /* Error al agregar o editar: debajo del campo si corresponde; si no, aviso rojo. */
  const mostrarError = (mensaje) => {
    const campo = campoDelError(mensaje);
    if (campo) {
      enfocarCampo.current = campo;
      setErrores({ [campo]: mensaje });
    } else {
      avisar(mensaje, "error");
    }
  };

  const abrirAgregar = () => {
    setAgregar(VACIO);
    setErrores({});
    setModo("agregar");
  };

  const abrirEditar = (u) => {
    setEditar({ id: String(u.id), nombre: u.name, email: u.email, rol: u.role, area: u.area_id ? String(u.area_id) : "", password: "" });
    setErrores({});
    setModo("editar");
  };

  const cerrar = () => setModo(null);

  const crear = async (event) => {
    event.preventDefault();
    if (ocupadoRef.current) return;
    setErrores({});
    const error = validarUsuario(agregar, loginLocal);
    if (error) return mostrarError(error);
    const payload = { name: agregar.nombre.trim(), email: agregar.email.trim(), role: agregar.rol };
    if (loginLocal) payload.password = agregar.password;
    const area = areaElegida(agregar.rol, agregar.area);
    if (area) payload.area_id = area;
    ocupadoRef.current = true;
    setOcupado(true);
    try {
      const response = await api("/api/users", { method: "POST", body: payload });
      const body = response.ok ? null : await response.json().catch(() => null);
      if (!response.ok) return mostrarError(mensajeDeError(response, body));
      setAgregar(VACIO);
      cerrar();
      avisar("Usuario agregado correctamente.", "exito");
      await cargar();
    } catch {
      avisar(SIN_CONEXION, "error");
    } finally {
      ocupadoRef.current = false;
      setOcupado(false);
    }
    return undefined;
  };

  const guardar = async (event) => {
    event.preventDefault();
    if (ocupadoRef.current) return;
    const payload = {};
    const nombre = editar.nombre.trim();
    const email = editar.email.trim();
    if (nombre) payload.name = nombre;
    if (email) payload.email = email;
    if (editar.rol) payload.role = editar.rol;
    const area = areaElegida(editar.rol, editar.area);
    if (area !== undefined) payload.area_id = area;
    setErrores({});
    const nueva = loginLocal ? editar.password : "";
    if (nueva) {
      const error = validarPassword(nueva);
      if (error) return mostrarError(error);
      payload.password = nueva;
    }
    if (Object.keys(payload).length === 0) {
      avisar("No hay cambios para guardar.", "error");
      return undefined;
    }
    ocupadoRef.current = true;
    setOcupado(true);
    try {
      const response = await api(`/api/users/${parseInt(editar.id, 10)}`, { method: "PATCH", body: payload });
      const body = response.ok ? null : await response.json().catch(() => null);
      if (!response.ok) return mostrarError(mensajeDeError(response, body));
      cerrar();
      avisar("Usuario actualizado correctamente.", "exito");
      await cargar();
    } catch {
      avisar(SIN_CONEXION, "error");
    } finally {
      ocupadoRef.current = false;
      setOcupado(false);
    }
    return undefined;
  };

  /* Desactivado no inicia sesión ni recibe tickets, pero conserva su historial. */
  const cambiarActivo = async (u, activar) => {
    if (ocupadoRef.current) return;
    if (!activar && !(await confirmar({
      titulo: "Desactivar usuario",
      mensaje: `¿Desactivar a ${u.name}? No podrá iniciar sesión ni recibir tickets.`,
      aceptar: "Desactivar",
      peligro: true,
    }))) return;
    ocupadoRef.current = true;
    try {
      const response = await api(`/api/users/${u.id}`, { method: "PATCH", body: { is_active: activar } });
      const body = response.ok ? null : await response.json().catch(() => null);
      if (!response.ok) {
        avisar(mensajeDeError(response, body), "error");
        return;
      }
      avisar(activar ? `${u.name} fue reactivado.` : `${u.name} fue desactivado.`, "exito");
      ocupadoRef.current = false;
      await cargar();
    } catch {
      avisar(SIN_CONEXION, "error");
    } finally {
      ocupadoRef.current = false;
    }
  };

  return (
    <>
      <Cabecera claseTitulo="" titulo="Usuarios" subtitulo="Administración de los usuarios del sistema"
        acciones={<button type="button" id="abrir-agregar-usuario" aria-haspopup="dialog" onClick={abrirAgregar}>Agregar usuario</button>} />
      <main className="contenido">
        <section className="seccion" aria-labelledby="titulo-usuarios">
          <h2 id="titulo-usuarios">Usuarios registrados</h2>
          <p id="usuarios-estado" className={estado && estado.tipo ? `estado ${estado.tipo}` : "estado"} role="status" aria-live="polite" hidden={!estado}>
            {estado ? estado.texto : ""}
          </p>
          <div className="tabla-scroll">
            <table id="tabla-usuarios" className="listado tabla-usuarios" hidden={Boolean(estado)}>
              <thead>
                <tr><th>Nombre</th><th>Correo</th><th>Rol</th><th>Departamento</th><th>Estado</th><th>Acciones</th></tr>
              </thead>
              <tbody id="cuerpo-usuarios">
                {usuarios.map((u) => {
                  const activo = u.is_active !== false;
                  const p = persona(u.name, "celda-nombre");
                  return (
                    <tr key={u.id}>
                      <td className={p.className} data-iniciales={p.iniciales}>{p.texto}</td>
                      <td data-label="Correo">{u.email}</td>
                      <td data-label="Rol"><span className={`badge ${claseRol(u.role)}`}>{u.role}</span></td>
                      <td data-label="Departamento">{textoAreaUsuario(u)}</td>
                      <td data-label="Estado"><span className={activo ? "badge badge-activo" : "badge badge-inactivo"}>{activo ? "Activo" : "Inactivo"}</span></td>
                      <td className="celda-acciones">
                        <button type="button" className="btn-accion" onClick={() => abrirEditar(u)}>Editar</button>
                        {(!sesion || sesion.id !== u.id) && (
                          <button type="button" className={activo ? "btn-accion secundario" : "btn-accion"}
                            onClick={() => cambiarActivo(u, !activo)}>{activo ? "Desactivar" : "Reactivar"}</button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>
      </main>

      <dialog id="dialogo-usuario" className="ventana-usuario" aria-labelledby="dialogo-usuario-titulo" ref={dialogo}
        onClose={() => setModo(null)}>
        <div className="ventana-cabecera">
          <h2 id="dialogo-usuario-titulo">{modo === "editar" ? "Editar usuario" : "Agregar usuario"}</h2>
          <button type="button" id="cerrar-dialogo-usuario" className="ventana-cerrar" aria-label="Cerrar" onClick={cerrar}>
            <svg className="icono" viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg>
          </button>
        </div>
        <Formulario tipo="agregar" visible={modo !== "editar"} datos={agregar} setDatos={setAgregar}
          errores={modo === "agregar" ? errores : {}} areas={areas} loginLocal={loginLocal} ocupado={ocupado}
          onEnviar={crear} onCancelar={cerrar} refs={refsAgregar} />
        <Formulario tipo="editar" visible={modo === "editar"} datos={editar} setDatos={setEditar}
          errores={modo === "editar" ? errores : {}} areas={areas} loginLocal={loginLocal} ocupado={ocupado}
          onEnviar={guardar} onCancelar={cerrar} refs={refsEditar} />
      </dialog>
    </>
  );
}
