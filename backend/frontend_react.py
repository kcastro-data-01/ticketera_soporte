"""La app React (``frontend-react/``, compilada en ``frontend-react/dist``).

Mientras dura la migración vive bajo ``/react/``: para cualquier ruta
``/react/*`` que no sea un archivo del build se devuelve ``index.html`` y la
resuelve React Router (fallback de SPA). Los archivos de ``assets/`` llevan
un hash en el nombre: se guardan un año (``immutable``); lo demás
(``index.html``, ``tema.js``) se revalida siempre, como el frontend actual.

En la etapa final la app pasa a la raíz y las direcciones viejas se
redirigen con 301 usando :func:`ruta_nueva` (todavía no se usa).
"""

from pathlib import Path
from urllib.parse import parse_qsl, urlencode

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException

PREFIJO = "/react"
CACHE_ASSETS = "public, max-age=31536000, immutable"


class FrontendReact(StaticFiles):
    """Archivos del build y, si no existe, ``index.html`` (rutas de React).
    Un ``assets/…`` que falta sí responde 404: devolver HTML en lugar de un
    .js solo confundiría al navegador."""

    async def get_response(self, path, scope):
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
    """Monta el build en ``/react`` si existe (antes del frontend actual).
    Devuelve True si lo montó."""
    if not (carpeta / "index.html").is_file():
        return False

    @app.get(PREFIJO, include_in_schema=False)
    def react_sin_barra() -> RedirectResponse:
        return RedirectResponse(f"{PREFIJO}/", status_code=307)

    app.mount(PREFIJO, FrontendReact(directory=str(carpeta), html=True), name="frontend-react")
    return True


# --- Etapa final: direcciones viejas → nuevas (301) ---
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
}


def ruta_nueva(ruta: str, consulta: str = "") -> str | None:
    """``/detalle.html?id=5`` → ``/tickets/5``; ``/index.html?estado=Nuevo`` →
    ``/?estado=Nuevo``; None si no es una dirección vieja. Igual que
    ``rutaNuevaDe`` en ``frontend-react/src/rutas.js``."""
    parametros = parse_qsl(consulta, keep_blank_values=False)
    if ruta == "/detalle.html":
        ticket = dict(parametros).get("id", "")
        return f"/tickets/{ticket}" if ticket.isdigit() else "/"
    nueva = RUTAS_VIEJAS.get(ruta)
    if nueva is None:
        return None
    return f"{nueva}?{urlencode(parametros)}" if parametros else nueva
