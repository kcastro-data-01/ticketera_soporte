/* Inicio de sesión (login.html): Microsoft con MSAL.js y, solo con
   LOGIN_LOCAL, correo y contraseña. Va en un archivo aparte porque la CSP no
   permite scripts inline; se carga después de MSAL, al final del <body>. */
(function () {
  const API_BASE = "/api/auth";
  // Solo lo que hace falta para iniciar sesión; User.Read ya tiene
  // consentimiento de administrador.
  const SCOPES = ["openid", "profile", "email", "User.Read"];

  const errorDiv = document.getElementById("auth-error");
  const successDiv = document.getElementById("auth-success");
  const btnMicrosoft = document.getElementById("btn-microsoft");
  const formLogin = document.getElementById("form-login");
  const btnLogin = document.getElementById("btn-login");

  let msalApp = null;

  // --- Sesión (ver sesion.js y auth.js) ---

  const CIERRE_KEY = "sesion_cierre";
  const INICIO_KEY = "sesion_inicio";
  const ACTIVIDAD_KEY = "sesion_actividad";
  const MENSAJES_CIERRE = {
    inactividad: "Su sesión se cerró por inactividad.",
    maxima: "Su sesión llegó al máximo de horas permitido. Inicie sesión nuevamente.",
    vencida: "Su sesión venció. Inicie sesión nuevamente.",
  };

  function leer(clave) {
    try {
      return localStorage.getItem(clave);
    } catch (e) {
      return null;
    }
  }

  function guardar(clave, valor) {
    try {
      if (valor === null) localStorage.removeItem(clave);
      else localStorage.setItem(clave, String(valor));
    } catch (e) {
      /* Sin almacenamiento. */
    }
  }

  const VOLVER_KEY = "login_volver";

  // Solo una página propia («detalle.html?id=5»): nunca otro sitio. Al ir a
  // Microsoft y volver se pierde el ?volver=: queda en sessionStorage.
  function destino() {
    let volver = "";
    try {
      volver = new URLSearchParams(window.location.search || "").get("volver") || "";
      if (!volver) volver = sessionStorage.getItem(VOLVER_KEY) || "";
    } catch (e) {
      volver = "";
    }
    return /^[a-z][a-z0-9-]*\.html(\?[A-Za-z0-9_=&%.-]*)?$/.test(volver) && !/^login\.html/.test(volver)
      ? volver : "index.html";
  }

  // Segundos Unix del claim ini del token de la app (o null).
  function inicioDelToken(token) {
    try {
      const base = token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
      const datos = JSON.parse(atob(base + "=".repeat((4 - (base.length % 4)) % 4)));
      return Number.isFinite(datos.ini) ? datos.ini : null;
    } catch (e) {
      return null;
    }
  }

  // --- Utilidades ---

  function showError(msg) {
    errorDiv.textContent = msg;
    errorDiv.classList.add("visible");
    successDiv.classList.remove("visible");
  }

  function showSuccess(msg) {
    successDiv.textContent = msg;
    successDiv.classList.add("visible");
    errorDiv.classList.remove("visible");
  }

  function clearMessages() {
    errorDiv.classList.remove("visible");
    successDiv.classList.remove("visible");
  }

  function setLoading(button, loading) {
    if (loading) {
      button.disabled = true;
      button.dataset.originalText = button.innerHTML;
      button.textContent = "Cargando...";
    } else {
      button.disabled = false;
      button.innerHTML = button.dataset.originalText;
    }
  }

  function saveSession(token, user) {
    try {
      sessionStorage.removeItem(VOLVER_KEY);
    } catch (e) {
      /* Nada guardado. */
    }
    localStorage.setItem("access_token", token);
    localStorage.setItem("user", JSON.stringify(user));
    const inicio = inicioDelToken(token);
    if (inicio !== null) guardar(INICIO_KEY, inicio * 1000);
    guardar(ACTIVIDAD_KEY, Date.now());
    guardar(CIERRE_KEY, null);
  }

  // Con el token de la app: datos del usuario, sesión guardada y a la página
  // de antes (o al listado).
  async function entrarConToken(accessToken, respaldo, { silencioso = false } = {}) {
    const meResp = await fetch(`${API_BASE}/me`, {
      headers: { Authorization: `Bearer ${accessToken}` },
    });
    const pagina = destino();
    saveSession(accessToken, meResp.ok ? await meResp.json() : respaldo);
    if (silencioso) {
      window.location.href = pagina;
      return;
    }
    showSuccess("Inicio de sesión correcto. Redirigiendo…");
    setTimeout(() => { window.location.href = pagina; }, 800);
  }

  // --- Microsoft ---

  // El id_token de Microsoft va al backend, que lo valida (firma,
  // audiencia, emisor y tenant) y entrega la sesión de la app.
  async function entrarConMicrosoft(idToken, { inicio = null, silencioso = false } = {}) {
    const cuerpo = { id_token: idToken };
    if (inicio !== null) cuerpo.inicio = inicio;
    const resp = await fetch(`${API_BASE}/microsoft`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(cuerpo),
    });
    if (silencioso && !resp.ok && resp.status !== 403) return false;
    if (resp.status === 403) {
      showError("Su cuenta está desactivada. Comuníquese con el administrador.");
      return;
    }
    if (resp.status === 401) {
      showError("No se pudo validar su cuenta. Use la cuenta de Microsoft de la empresa.");
      return;
    }
    if (!resp.ok) {
      showError(`Error del servidor (${resp.status}). Inténtelo de nuevo.`);
      return;
    }
    const data = await resp.json();
    await entrarConToken(data.access_token, {}, { silencioso });
    return true;
  }

  // La sesión venció (no se cerró a mano, por inactividad ni por el máximo
  // de horas): si la cuenta de Microsoft sigue conectada, se vuelve a entrar
  // sin pedir nada. Primero con la caché de MSAL (refresh token, sin
  // iframe); si no, ssoSilent con un iframe oculto que vuelve a
  // msal/silencioso.html. Devuelve true si entró.
  async function entrarEnSilencio(config) {
    if (leer(CIERRE_KEY) !== "vencida") return false;
    const inicioMs = Number(leer(INICIO_KEY)) || 0;
    const maximoMs = (Number(config.sesion_maxima_horas) || 10) * 3600 * 1000;
    if (!inicioMs || Date.now() - inicioMs >= maximoMs) {
      guardar(CIERRE_KEY, "maxima");
      return false;
    }
    showSuccess("Reconectando con su cuenta de Microsoft…");
    const inicio = Math.floor(inicioMs / 1000);
    const cuentas = msalApp.getAllAccounts ? msalApp.getAllAccounts() : [];
    const pedido = {
      scopes: SCOPES,
      redirectUri: `${window.location.origin}/msal/silencioso.html`,
    };
    const intentos = [];
    if (cuentas.length) {
      intentos.push(() => msalApp.acquireTokenSilent({ ...pedido, account: cuentas[0], forceRefresh: true }));
    }
    intentos.push(() => msalApp.ssoSilent(cuentas.length ? { ...pedido, loginHint: cuentas[0].username } : pedido));
    for (const intento of intentos) {
      try {
        const resultado = await intento();
        if (resultado && resultado.idToken
            && await entrarConMicrosoft(resultado.idToken, { inicio, silencioso: true })) {
          return true;
        }
      } catch (e) {
        /* Siguiente intento o el botón de siempre. */
      }
    }
    clearMessages();
    return false;
  }

  async function iniciarMicrosoft(config) {
    if (!window.msal || !config.tenant || !config.client_id) {
      btnMicrosoft.disabled = true;
      showError("El inicio de sesión con Microsoft no está disponible en este momento.");
      return;
    }
    msalApp = await msal.PublicClientApplication.createPublicClientApplication({
      auth: {
        clientId: config.client_id,
        authority: `https://login.microsoftonline.com/${config.tenant}`,
        redirectUri: `${window.location.origin}/login.html`,
      },
      // En localStorage (MSAL la cifra): la cuenta se recuerda en todas las
      // pestañas y al volver de otra página, para entrar en silencio.
      cache: { cacheLocation: "localStorage" },
    });
    // Al volver de Microsoft (redirect) llega la respuesta con el id_token.
    const respuesta = await msalApp.handleRedirectPromise();
    if (respuesta && respuesta.idToken) {
      setLoading(btnMicrosoft, true);
      try {
        await entrarConMicrosoft(respuesta.idToken);
      } finally {
        setLoading(btnMicrosoft, false);
      }
      return;
    }
    setLoading(btnMicrosoft, true);
    let entro = false;
    try {
      entro = await entrarEnSilencio(config);
    } finally {
      if (!entro) setLoading(btnMicrosoft, false);
    }
    if (!entro) mostrarMotivo();
  }

  // Por qué se está en el login (sesión cerrada por inactividad, etc.).
  function mostrarMotivo() {
    const mensaje = MENSAJES_CIERRE[leer(CIERRE_KEY)];
    if (mensaje && !errorDiv.classList.contains("visible")) showSuccess(mensaje);
  }

  btnMicrosoft.addEventListener("click", async () => {
    clearMessages();
    if (!msalApp) return;
    try {
      // Flujo de código con PKCE (MSAL lo hace solo).
      guardar(CIERRE_KEY, null);
      try {
        sessionStorage.setItem(VOLVER_KEY, destino());
      } catch (e) {
        /* Sin sessionStorage se vuelve al listado. */
      }
      await msalApp.loginRedirect({ scopes: SCOPES, prompt: "select_account" });
    } catch (err) {
      showError("No se pudo abrir el inicio de sesión de Microsoft.");
    }
  });

  // --- Contraseña (solo LOGIN_LOCAL, desarrollo) ---

  async function handleLogin(event) {
    event.preventDefault();
    clearMessages();

    const email = document.getElementById("login-email").value.trim();
    const password = document.getElementById("login-password").value;
    if (!email || !password) {
      showError("Ingrese su correo y su contraseña.");
      return;
    }

    setLoading(btnLogin, true);
    try {
      const resp = await fetch(`${API_BASE}/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      if (resp.status === 401) {
        showError("Credenciales inválidas. Verifique su correo y contraseña.");
        return;
      }
      if (resp.status === 403) {
        showError("Su cuenta está desactivada. Comuníquese con el administrador.");
        return;
      }
      if (!resp.ok) {
        showError(`Error del servidor (${resp.status}). Inténtelo de nuevo.`);
        return;
      }
      const data = await resp.json();
      await entrarConToken(data.access_token, { email });
    } catch (err) {
      showError("No se pudo conectar con el servidor. Verifique su conexión.");
    } finally {
      setLoading(btnLogin, false);
    }
  }

  formLogin.addEventListener("submit", handleLogin);
  // Botón con aria-label y aria-pressed: también se usa con el teclado.
  document.querySelectorAll(".toggle-password").forEach(el => el.addEventListener("click", () => {
    const i = el.parentElement.querySelector("input");
    const mostrar = i.type === "password";
    i.type = mostrar ? "text" : "password";
    const etiqueta = mostrar ? "Ocultar contraseña" : "Mostrar contraseña";
    el.setAttribute("aria-label", etiqueta);
    el.setAttribute("aria-pressed", String(mostrar));
    el.title = etiqueta;
  }));

  // --- Inicialización ---

  async function init() {
    try {
      const resp = await fetch(`${API_BASE}/config`);
      const config = resp.ok ? await resp.json() : {};
      if (config.login_local) formLogin.classList.add("activo");
      await iniciarMicrosoft(config);
    } catch (err) {
      showError("No se pudo iniciar sesión con Microsoft. Inténtelo de nuevo.");
    }
  }

  init();
})();
