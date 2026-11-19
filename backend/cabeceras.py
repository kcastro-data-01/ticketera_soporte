"""Cabeceras de seguridad de la versión publicada fuera de Vercel (Render).

En Vercel las pone la CDN (``vercel.json`` → ``headers``); en Render no hay
CDN delante de FastAPI, así que las agrega este middleware. Son las mismas
(``test_render.py`` lo compara con ``vercel.json``).
"""

from starlette.middleware.base import BaseHTTPMiddleware

PAGINA_SILENCIOSA = "/msal/silencioso"

CABECERAS = {
    "X-Robots-Tag": "noindex, nofollow",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "same-origin",
    "X-Frame-Options": "DENY",
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains",
    "Content-Security-Policy-Report-Only": (
        "default-src 'self'; script-src 'self' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
        "style-src 'self' https://fonts.googleapis.com; font-src https://fonts.gstatic.com; "
        "img-src 'self' data: blob:; connect-src 'self' https://login.microsoftonline.com; "
        "frame-src 'self' https://login.microsoftonline.com; object-src 'none'; base-uri 'none'; "
        "form-action 'self'; frame-ancestors 'none'; upgrade-insecure-requests"),
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
    "Cross-Origin-Opener-Policy": "same-origin",
}

# La página que msal abre en un iframe (renovar la sesión sin ventana).
CABECERAS_SILENCIOSA = {
    "X-Robots-Tag": "noindex, nofollow",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "same-origin",
    "X-Frame-Options": "SAMEORIGIN",
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains",
    "Content-Security-Policy": "default-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'self'",
    "Cross-Origin-Opener-Policy": "same-origin",
}


def cabeceras_para(ruta: str) -> dict[str, str]:
    return CABECERAS_SILENCIOSA if ruta == PAGINA_SILENCIOSA else CABECERAS


class CabecerasSeguridad(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        for nombre, valor in cabeceras_para(request.url.path).items():
            response.headers.setdefault(nombre, valor)
        return response
