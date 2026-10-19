"""Inicio de sesión en Microsoft 365 para leer y enviar el correo con Graph.

Se usa ``msal.PublicClientApplication`` con el flujo *device code*: no hay
secreto de cliente. La primera vez se ejecuta ``python -m backend.correo_login``,
que muestra un código para escribir en https://microsoft.com/devicelogin.
Los tokens quedan en un archivo de caché (``CORREO_M365_CACHE``) y después la
aplicación los renueva sola con ``acquire_token_silent``.
"""

from __future__ import annotations

import os
from pathlib import Path

import msal

from backend.database import PROJECT_ROOT

# Permisos delegados concedidos a la app de Azure.
PERMISOS = ["Mail.ReadWrite", "Mail.Send", "User.Read"]

# Fuera de Docker la caché queda en la raíz del proyecto (en .gitignore);
# en Docker, docker-compose la pone en el volumen /data.
CACHE_POR_DEFECTO = PROJECT_ROOT / ".msal_cache.json"


class SinSesionError(Exception):
    """No hay token válido: hay que ejecutar ``python -m backend.correo_login``."""


def ruta_cache(valor: str | None = None) -> Path:
    if valor is None:
        valor = os.environ.get("CORREO_M365_CACHE")
    return Path(valor) if valor and valor.strip() else CACHE_POR_DEFECTO


def cargar_cache(ruta: Path) -> msal.SerializableTokenCache:
    cache = msal.SerializableTokenCache()
    if ruta.exists():
        cache.deserialize(ruta.read_text(encoding="utf-8"))
    return cache


def guardar_cache(cache: msal.SerializableTokenCache, ruta: Path) -> None:
    if not cache.has_state_changed:
        return
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(cache.serialize(), encoding="utf-8")
    try:
        ruta.chmod(0o600)  # Contiene tokens: solo lo lee el dueño.
    except OSError:
        pass


def crear_app(tenant: str, client_id: str, cache) -> msal.PublicClientApplication:
    return msal.PublicClientApplication(
        client_id,
        authority=f"https://login.microsoftonline.com/{tenant}",
        token_cache=cache,
    )


class ProveedorToken:
    """Entrega un token de acceso para Graph, renovándolo desde la caché.

    La app de msal se crea una sola vez; el archivo de caché se vuelve a leer
    cuando cambia, así un ``correo_login`` hecho con la aplicación encendida
    se toma sin reiniciarla.
    """

    def __init__(self, tenant: str, client_id: str, usuario: str, cache_path: Path,
                 crear=crear_app):
        self.tenant = tenant
        self.client_id = client_id
        self.usuario = usuario
        self.cache_path = cache_path
        self._crear = crear
        self._cache = None
        self._app = None
        self._leido = None  # fecha de modificación del archivo ya cargado

    def _cargar(self):
        modificado = self.cache_path.stat().st_mtime_ns
        if self._app is None:
            self._cache = cargar_cache(self.cache_path)
            self._app = self._crear(self.tenant, self.client_id, self._cache)
        elif modificado != self._leido:
            self._cache.deserialize(self.cache_path.read_text(encoding="utf-8"))
        self._leido = modificado
        return self._app

    def obtener(self) -> str:
        if not (self.tenant and self.client_id):
            raise SinSesionError("faltan CORREO_M365_TENANT o CORREO_M365_CLIENT_ID")
        if not self.cache_path.exists():
            raise SinSesionError(f"no existe la caché de tokens {self.cache_path}")
        app = self._cargar()
        cuentas = app.get_accounts(username=self.usuario) or app.get_accounts()
        if not cuentas:
            raise SinSesionError("la caché no tiene ninguna cuenta iniciada")
        resultado = app.acquire_token_silent(PERMISOS, account=cuentas[0])
        if self._cache.has_state_changed:
            guardar_cache(self._cache, self.cache_path)
            self._cache.has_state_changed = False
            self._leido = self.cache_path.stat().st_mtime_ns
        if not resultado or "access_token" not in resultado:
            detalle = (resultado or {}).get("error_description") or "la sesión venció"
            raise SinSesionError(detalle)
        return resultado["access_token"]


def iniciar_sesion(tenant: str, client_id: str, cache_path: Path, imprimir=print,
                   crear=crear_app) -> dict:
    """Flujo device code: muestra el código y espera a que se inicie sesión.

    Devuelve el resultado de msal (con ``id_token_claims``). Lanza
    ``SinSesionError`` si no se pudo iniciar.
    """
    cache = cargar_cache(cache_path)
    app = crear(tenant, client_id, cache)
    flujo = app.initiate_device_flow(scopes=PERMISOS)
    if "user_code" not in flujo:
        raise SinSesionError(flujo.get("error_description") or "no se pudo iniciar el flujo")
    imprimir(flujo["message"])
    resultado = app.acquire_token_by_device_flow(flujo)
    if "access_token" not in resultado:
        raise SinSesionError(resultado.get("error_description") or "no se completó el inicio de sesión")
    guardar_cache(cache, cache_path)
    return resultado
