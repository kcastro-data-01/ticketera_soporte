"""Inicia sesión en Microsoft 365 para que la ticketera lea el buzón.

Uso (una vez, y de nuevo si la sesión vence):

    python -m backend.correo_login
    docker compose exec ticketera python -m backend.correo_login   # con Docker

Muestra un código para escribir en https://microsoft.com/devicelogin; hay que
entrar con la cuenta del buzón (``CORREO_USUARIO``). Lee ``CORREO_M365_TENANT``,
``CORREO_M365_CLIENT_ID`` y ``CORREO_M365_CACHE`` del entorno.
"""

from __future__ import annotations

import os
import sys

from backend.services.correo_auth import SinSesionError, iniciar_sesion, ruta_cache


def main(env=None, imprimir=print, iniciar=iniciar_sesion) -> int:
    env = os.environ if env is None else env
    tenant = (env.get("CORREO_M365_TENANT") or "").strip()
    client_id = (env.get("CORREO_M365_CLIENT_ID") or "").strip()
    usuario = (env.get("CORREO_USUARIO") or "").strip().lower()
    if not tenant or not client_id:
        imprimir("Faltan CORREO_M365_TENANT y/o CORREO_M365_CLIENT_ID en el archivo .env.")
        return 1

    cache = ruta_cache(env.get("CORREO_M365_CACHE"))
    try:
        resultado = iniciar(tenant, client_id, cache, imprimir=imprimir)
    except SinSesionError as error:
        imprimir(f"No se pudo iniciar sesión: {error}")
        return 1

    claims = resultado.get("id_token_claims") or {}
    cuenta = (claims.get("preferred_username") or claims.get("email") or "").lower()
    imprimir(f"Sesión iniciada como {cuenta or '(cuenta desconocida)'}. Tokens guardados en {cache}.")
    if usuario and cuenta and cuenta != usuario:
        imprimir(f"ATENCIÓN: CORREO_USUARIO es {usuario}, pero iniciaste sesión con {cuenta}. "
                 "La ticketera leerá el buzón de la cuenta con la que iniciaste sesión.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
