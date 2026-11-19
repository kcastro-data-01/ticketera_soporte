/* Inicio de sesión (port de frontend/js/login.js): Microsoft con MSAL
   (flujo de código con PKCE) y, solo con LOGIN_LOCAL, correo y contraseña. */
import { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { PublicClientApplication } from "@azure/msal-browser";
import "../css/login.css";
import imagenLogin from "../images/login-sistema-tickets.jpg";
import logo from "../images/logo-circular.jpg";
import { useSesion } from "../contexto/SesionContext.jsx";
import { useClaseBody, useTitulo } from "../componentes/claseBody.js";
import { IconoMicrosoft, IconoOjo } from "../componentes/iconos.jsx";
import {
  SESION_ACTIVIDAD_KEY, SESION_CIERRE_KEY, SESION_INICIO_KEY, VOLVER_KEY,
  destinoSeguro, guardarAlmacen, leerAlmacen,
} from "../sesion/almacen.js";
import { conBase } from "../rutas.js";

const API_BASE = "/api/auth";
/* Solo lo necesario para iniciar sesión (User.Read ya tiene consentimiento). */
export const SCOPES = ["openid", "profile", "email", "User.Read"];
/* Página vacía a la que vuelve el iframe oculto de ssoSilent: la misma que
   usa la ticketera actual (ya registrada en Entra, con sus cabeceras). */
export const RUTA_SILENCIOSA = "/msal/silencioso";

const MENSAJES_CIERRE = {
  inactividad: "Su sesión se cerró por inactividad.",
  maxima: "Su sesión llegó al máximo de horas permitido. Inicie sesión nuevamente.",
  vencida: "Su sesión venció. Inicie sesión nuevamente.",
};

function inicioDelToken(token) {
  try {
    const base = token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
    const datos = JSON.parse(atob(base + "=".repeat((4 - (base.length % 4)) % 4)));
    return Number.isFinite(datos.ini) ? datos.ini : null;
  } catch {
    return null;
  }
}

export default function Login() {
  useClaseBody("pagina-login");
  useTitulo("Iniciar sesión");
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const { iniciar } = useSesion();
  const [mensaje, setMensaje] = useState(null); /* { tipo: "error" | "exito", texto } */
  const [loginLocal, setLoginLocal] = useState(false);
  const [msDeshabilitado, setMsDeshabilitado] = useState(false);
  const [cargandoMs, setCargandoMs] = useState(false);
  const [cargandoClave, setCargandoClave] = useState(false);
  const [email, setEmail] = useState("");
  const [clave, setClave] = useState("");
  const [verClave, setVerClave] = useState(false);
  const msal = useRef(null);
  const iniciado = useRef(false);

  const error = (texto) => setMensaje({ tipo: "error", texto });
  const exito = (texto) => setMensaje({ tipo: "exito", texto });

  /* Solo una ruta propia; al ir a Microsoft y volver se pierde ?volver=. */
  const destino = () => {
    let volver = params.get("volver") || "";
    if (!volver) {
      try {
        volver = sessionStorage.getItem(VOLVER_KEY) || "";
      } catch {
        volver = "";
      }
    }
    return destinoSeguro(volver);
  };

  const entrarConToken = async (accessToken, respaldo, { silencioso = false } = {}) => {
    const me = await fetch(`${API_BASE}/me`, { headers: { Authorization: `Bearer ${accessToken}` } });
    const pagina = destino();
    try {
      sessionStorage.removeItem(VOLVER_KEY);
    } catch {
      /* Nada guardado. */
    }
    const user = me.ok ? await me.json() : respaldo;
    iniciar(accessToken, user);
    const inicio = inicioDelToken(accessToken);
    if (inicio !== null) guardarAlmacen(SESION_INICIO_KEY, inicio * 1000);
    guardarAlmacen(SESION_ACTIVIDAD_KEY, Date.now());
    if (silencioso) {
      navigate(pagina, { replace: true });
      return;
    }
    exito("Inicio de sesión correcto. Redirigiendo…");
    setTimeout(() => navigate(pagina, { replace: true }), 800);
  };

  /* El id_token de Microsoft va al backend, que lo valida y entrega la sesión. */
  const entrarConMicrosoft = async (idToken, { inicio = null, silencioso = false } = {}) => {
    const cuerpo = { id_token: idToken };
    if (inicio !== null) cuerpo.inicio = inicio;
    const resp = await fetch(`${API_BASE}/microsoft`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(cuerpo),
    });
    if (silencioso && !resp.ok && resp.status !== 403) return false;
    if (resp.status === 403) {
      error("Su cuenta está desactivada. Comuníquese con el administrador.");
      return false;
    }
    if (resp.status === 401) {
      error("No se pudo validar su cuenta. Use la cuenta de Microsoft de la empresa.");
      return false;
    }
    if (!resp.ok) {
      error(`Error del servidor (${resp.status}). Inténtelo de nuevo.`);
      return false;
    }
    const data = await resp.json();
    await entrarConToken(data.access_token, {}, { silencioso });
    return true;
  };

  /* Si la sesión venció (no se cerró a mano, por inactividad ni por el
     máximo de horas) y la cuenta de Microsoft sigue conectada, se vuelve a
     entrar sin pedir nada: primero la caché de MSAL y luego ssoSilent. */
  const entrarEnSilencio = async (config) => {
    if (leerAlmacen(SESION_CIERRE_KEY) !== "vencida") return false;
    const inicioMs = Number(leerAlmacen(SESION_INICIO_KEY)) || 0;
    const maximoMs = (Number(config.sesion_maxima_horas) || 10) * 3600 * 1000;
    if (!inicioMs || Date.now() - inicioMs >= maximoMs) {
      guardarAlmacen(SESION_CIERRE_KEY, "maxima");
      return false;
    }
    exito("Reconectando con su cuenta de Microsoft…");
    const inicio = Math.floor(inicioMs / 1000);
    const app = msal.current;
    const cuentas = app.getAllAccounts ? app.getAllAccounts() : [];
    const pedido = { scopes: SCOPES, redirectUri: `${window.location.origin}${RUTA_SILENCIOSA}` };
    const intentos = [];
    if (cuentas.length) {
      intentos.push(() => app.acquireTokenSilent({ ...pedido, account: cuentas[0], forceRefresh: true }));
    }
    intentos.push(() => app.ssoSilent(cuentas.length ? { ...pedido, loginHint: cuentas[0].username } : pedido));
    for (const intento of intentos) {
      try {
        const resultado = await intento();
        if (resultado && resultado.idToken
            && await entrarConMicrosoft(resultado.idToken, { inicio, silencioso: true })) {
          return true;
        }
      } catch {
        /* Siguiente intento o el botón de siempre. */
      }
    }
    setMensaje(null);
    return false;
  };

  const mostrarMotivo = () => {
    const texto = MENSAJES_CIERRE[leerAlmacen(SESION_CIERRE_KEY)];
    if (texto) setMensaje((actual) => (actual && actual.tipo === "error" ? actual : { tipo: "exito", texto }));
  };

  const iniciarMicrosoft = async (config) => {
    if (!config.tenant || !config.client_id) {
      setMsDeshabilitado(true);
      error("El inicio de sesión con Microsoft no está disponible en este momento.");
      return;
    }
    msal.current = await PublicClientApplication.createPublicClientApplication({
      auth: {
        clientId: config.client_id,
        authority: `https://login.microsoftonline.com/${config.tenant}`,
        redirectUri: `${window.location.origin}${conBase("/login")}`,
      },
      /* En localStorage: la cuenta se recuerda en todas las pestañas. */
      cache: { cacheLocation: "localStorage" },
    });
    const respuesta = await msal.current.handleRedirectPromise();
    if (respuesta && respuesta.idToken) {
      setCargandoMs(true);
      try {
        await entrarConMicrosoft(respuesta.idToken);
      } finally {
        setCargandoMs(false);
      }
      return;
    }
    setCargandoMs(true);
    let entro = false;
    try {
      entro = await entrarEnSilencio(config);
    } finally {
      if (!entro) setCargandoMs(false);
    }
    if (!entro) mostrarMotivo();
  };

  useEffect(() => {
    if (iniciado.current) return;
    iniciado.current = true;
    (async () => {
      try {
        const resp = await fetch(`${API_BASE}/config`);
        const config = resp.ok ? await resp.json() : {};
        if (config.login_local) setLoginLocal(true);
        await iniciarMicrosoft(config);
      } catch {
        error("No se pudo iniciar sesión con Microsoft. Inténtelo de nuevo.");
      }
    })();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const conMicrosoft = async () => {
    setMensaje(null);
    if (!msal.current) return;
    try {
      guardarAlmacen(SESION_CIERRE_KEY, null);
      try {
        sessionStorage.setItem(VOLVER_KEY, destino());
      } catch {
        /* Se vuelve al listado. */
      }
      await msal.current.loginRedirect({ scopes: SCOPES, prompt: "select_account" });
    } catch {
      error("No se pudo abrir el inicio de sesión de Microsoft.");
    }
  };

  const conClave = async (event) => {
    event.preventDefault();
    setMensaje(null);
    const correo = email.trim();
    if (!correo || !clave) {
      error("Ingrese su correo y su contraseña.");
      return;
    }
    setCargandoClave(true);
    try {
      const resp = await fetch(`${API_BASE}/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: correo, password: clave }),
      });
      if (resp.status === 401) return error("Credenciales inválidas. Verifique su correo y contraseña.");
      if (resp.status === 403) return error("Su cuenta está desactivada. Comuníquese con el administrador.");
      if (!resp.ok) return error(`Error del servidor (${resp.status}). Inténtelo de nuevo.`);
      const data = await resp.json();
      await entrarConToken(data.access_token, { email: correo });
    } catch {
      error("No se pudo conectar con el servidor. Verifique su conexión.");
    } finally {
      setCargandoClave(false);
    }
    return undefined;
  };

  const etiquetaOjo = verClave ? "Ocultar contraseña" : "Mostrar contraseña";
  return (
    <div className="auth-container">
      <div className="login-izq">
        <img src={imagenLogin} alt="American Data Networks" className="login-imagen" />
      </div>
      <div className="login-der">
        <div className="login-marca">
          <img src={logo} alt="" />
          <span>
            <span className="login-marca-nombre">American Data Networks</span>
            <span className="login-marca-sub">Sistema de tickets</span>
          </span>
        </div>
        <h2 className="login-titulo">Iniciar sesión</h2>
        <div id="auth-error" className={`auth-error${mensaje && mensaje.tipo === "error" ? " visible" : ""}`} role="alert">
          {mensaje && mensaje.tipo === "error" ? mensaje.texto : ""}
        </div>
        <div id="auth-success" className={`auth-success${mensaje && mensaje.tipo === "exito" ? " visible" : ""}`} role="status">
          {mensaje && mensaje.tipo === "exito" ? mensaje.texto : ""}
        </div>
        <p className="nota-login">Use su cuenta de Microsoft de la empresa.</p>
        <div className="btn-grp">
          <button type="button" id="btn-microsoft" className="btn-primario btn-microsoft"
            disabled={msDeshabilitado || cargandoMs} onClick={conMicrosoft}>
            {cargandoMs ? "Cargando..." : <><IconoMicrosoft />Iniciar sesión con Microsoft</>}
          </button>
        </div>

        {/* Solo para desarrollo (LOGIN_LOCAL=true): correo y contraseña. */}
        <form id="form-login" className={`auth-form${loginLocal ? " activo" : ""}`} onSubmit={conClave}>
          <div className="campo">
            <input type="email" id="login-email" name="email" required autoComplete="email"
              className="form-input" placeholder="nombre@empresa.com" aria-label="Correo"
              value={email} onChange={(e) => setEmail(e.target.value)} />
            <span className="field-icon email-icon" />
          </div>
          <div className="campo">
            <input type={verClave ? "text" : "password"} id="login-password" name="password" required
              autoComplete="current-password" className="form-input" placeholder="••••••••" aria-label="Contraseña"
              value={clave} onChange={(e) => setClave(e.target.value)} />
            <button type="button" className="toggle-password" aria-label={etiquetaOjo}
              aria-pressed={String(verClave)} title={etiquetaOjo} onClick={() => setVerClave((v) => !v)}>
              <IconoOjo />
            </button>
          </div>
          <div className="btn-grp">
            <button type="submit" id="btn-login" className="btn-secundario" disabled={cargandoClave}>
              {cargandoClave ? "Cargando..." : "Entrar con contraseña (desarrollo)"}
            </button>
          </div>
        </form>

        <div className="login-footer" />
      </div>
    </div>
  );
}
