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
    localStorage.setItem("access_token", token);
    localStorage.setItem("user", JSON.stringify(user));
  }

  // Con el token de la app: datos del usuario, sesión guardada y al listado.
  async function entrarConToken(accessToken, respaldo) {
    const meResp = await fetch(`${API_BASE}/me`, {
      headers: { Authorization: `Bearer ${accessToken}` },
    });
    saveSession(accessToken, meResp.ok ? await meResp.json() : respaldo);
    showSuccess("Inicio de sesión correcto. Redirigiendo…");
    setTimeout(() => { window.location.href = "index.html"; }, 800);
  }

  // --- Microsoft ---

  // El id_token de Microsoft va al backend, que lo valida (firma,
  // audiencia, emisor y tenant) y entrega la sesión de la app.
  async function entrarConMicrosoft(idToken) {
    const resp = await fetch(`${API_BASE}/microsoft`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id_token: idToken }),
    });
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
    await entrarConToken(data.access_token, {});
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
      cache: { cacheLocation: "sessionStorage" },
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
    }
  }

  btnMicrosoft.addEventListener("click", async () => {
    clearMessages();
    if (!msalApp) return;
    try {
      // Flujo de código con PKCE (MSAL lo hace solo).
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
