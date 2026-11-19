"""El frontend: la app React compilada (``frontend-react/dist``), en la raíz.

- Un archivo del build se sirve tal cual; los de ``assets/`` llevan un hash
  en el nombre y se guardan un año (``immutable``); lo demás (``index.html``,
  ``tema.js``…) se revalida siempre (``no-cache``).
- Cualquier otra ruta devuelve ``index.html`` y la resuelve React Router
  (fallback de SPA), salvo ``/api/*`` y ``/health``: ahí una ruta que no
  existe sigue siendo 404 y no una página.
- ``/msal/silencioso`` es la página vacía a la que vuelve el iframe de MSAL
  (con sus cabeceras de iframe, ver ``cabeceras.py``).
- Las direcciones viejas redirigen con 301 (:func:`ruta_nueva`):
  ``detalle.html?id=N`` → ``/tickets/N``, ``index.html`` → ``/``,
  ``/react/…`` → ``/…``, ``/msal/silencioso.html`` → ``/msal/silencioso``.
  Se conserva la consulta; el ``#fragmento`` no llega al servidor y el
  navegador lo vuelve a poner en la dirección nueva.
"""

from pathlib import Path
from urllib.parse import parse_qsl, urlencode

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException

CACHE_ASSETS = "public, max-age=31536000, immutable"
PAGINA_SILENCIOSA = "/msal/silencioso"
ARCHIVO_SILENCIOSA = "msal/silencioso.html"
FUERA_DE_LA_APP = ("api/", "api", "health", "docs", "redoc", "openapi.json")

# Dirección vieja → nueva (la de React).
RUTAS_VIEJAS = {
    "/index.html": "/",
    "/login.html": "/login",
    "/crear.html": "/crear",
    "/metricas.html": "/metricas",
    "/departamentos.html": "/departamentos",
    "/historial.html": "/historial",
    "/usuarios.html": "/usuarios",
    "/cuenta.html": "/cuenta",
    "/ayuda.html": "/ayuda",
    "/sin-permiso.html": "/sin-permiso",
    "/404.html": "/",
    "/msal/silencioso.html": PAGINA_SILENCIOSA,
}


def ruta_nueva(ruta: str, consulta: str = "") -> str | None:
    """``/detalle.html?id=5`` → ``/tickets/5``; ``/index.html?estado=Nuevo`` →
    ``/?estado=Nuevo``; ``/react/tickets/5`` → ``/tickets/5``; None si no es
    una dirección vieja. La consulta se conserva (en el detalle, sin el id)."""
    parametros = parse_qsl(consulta, keep_blank_values=True)
    if ruta == "/detalle.html":
        ticket = dict(parametros).get("id", "")
        resto = [(k, v) for k, v in parametros if k != "id"]
        nueva = f"/tickets/{ticket}" if ticket.isdigit() and int(ticket) > 0 else "/"
    elif ruta == "/react" or ruta.startswith("/react/"):
        nueva = "/" + ruta[len("/react/"):] if ruta.startswith("/react/") else "/"
        resto = parametros
    elif ruta in RUTAS_VIEJAS:
        nueva = RUTAS_VIEJAS[ruta]
        resto = parametros
    else:
        return None
    return f"{nueva}?{urlencode(resto)}" if resto else nueva


def _redirigir(request: Request) -> RedirectResponse:
    destino = ruta_nueva(request.url.path, request.url.query) or "/"
    return RedirectResponse(destino, status_code=301)


def registrar_redirecciones(app: FastAPI) -> None:
    """Las 301 de las direcciones viejas (también sin el build)."""
    metodos = ["GET", "HEAD"]
    for ruta in [*RUTAS_VIEJAS, "/detalle.html", "/react", "/react/{resto:path}"]:
        app.add_api_route(ruta, _redirigir, methods=metodos, include_in_schema=False)


class FrontendReact(StaticFiles):
    """Archivos del build y, si no existe, ``index.html`` (rutas de React)."""

    async def get_response(self, path, scope):
        # Primero el método, como StaticFiles: un POST a una ruta de la API
        # que solo acepta GET sigue siendo 405 (y no 404).
        if scope["method"] not in ("GET", "HEAD"):
            raise HTTPException(status_code=405)
        if path == "." or path == "":
            path = "index.html"
        if path.startswith(FUERA_DE_LA_APP):
            raise HTTPException(status_code=404)
        try:
            response = await super().get_response(path, scope)
        except HTTPException as error:
            if error.status_code != 404:
                raise
            response = None
        if response is None or response.status_code == 404:
            if path.startswith("assets/"):
                raise HTTPException(status_code=404)
            response = await super().get_response("index.html", scope)
        if path.startswith("assets/") and response.status_code in (200, 304):
            response.headers["Cache-Control"] = CACHE_ASSETS
        else:
            response.headers.setdefault("Cache-Control", "no-cache")
        return response


def montar_react(app: FastAPI, carpeta: Path) -> bool:
    """Las redirecciones y, si el build existe, la página silenciosa y la
    app en ``/`` (va al final: las rutas de la API tienen prioridad).
    Devuelve True si montó la app."""
    registrar_redirecciones(app)
    if not (carpeta / "index.html").is_file():
        return False

    silenciosa = carpeta / ARCHIVO_SILENCIOSA

    @app.api_route(PAGINA_SILENCIOSA, methods=["GET", "HEAD"], include_in_schema=False)
    def pagina_silenciosa() -> FileResponse:
        return FileResponse(silenciosa, media_type="text/html; charset=utf-8", headers={"Cache-Control": "no-cache"})

    app.mount("/", FrontendReact(directory=str(carpeta), html=True), name="frontend")
    return True
