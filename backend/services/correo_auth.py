"""Inicio de sesión en Microsoft 365 para leer y enviar el correo con Graph.

Se usa ``msal.PublicClientApplication`` con el flujo *device code*: no hay
secreto de cliente. La primera vez se ejecuta ``python -m backend.correo_login``,
que muestra un código para escribir en https://microsoft.com/devicelogin.
Los tokens quedan en la base de datos (tabla ``msal_cache``, igual en Docker
y en Vercel) y después la aplicación los renueva sola con
``acquire_token_silent``. Si la tabla está vacía y existe el archivo de caché
de antes (``CORREO_M365_CACHE``), se importa una vez: no hay que volver a
iniciar sesión.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import msal
from sqlalchemy import select

from backend.database import PROJECT_ROOT

logger = logging.getLogger(__name__)

# Permisos delegados concedidos a la app de Azure.
PERMISOS = ["Mail.ReadWrite", "Mail.Send", "User.Read"]

# Archivo de caché de antes (solo se lee para importarlo a la base): fuera de
# Docker en la raíz del proyecto (en .gitignore); en Docker, en el volumen /data.
CACHE_POR_DEFECTO = PROJECT_ROOT / ".msal_cache.json"


class SinSesionError(Exception):
    """No hay token válido: hay que ejecutar ``python -m backend.correo_login``."""


def ruta_cache(valor: str | None = None) -> Path:
    if valor is None:
        valor = os.environ.get("CORREO_M365_CACHE")
    return Path(valor) if valor and valor.strip() else CACHE_POR_DEFECTO


class AlmacenArchivo:
    """La caché en un archivo (como antes; lo usan las pruebas y la importación)."""

    def __init__(self, ruta: Path):
        self.ruta = Path(ruta)

    def __str__(self) -> str:
        return str(self.ruta)

    def leer(self) -> str | None:
        return self.ruta.read_text(encoding="utf-8") if self.ruta.exists() else None

    def guardar(self, texto: str) -> None:
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        self.ruta.write_text(texto, encoding="utf-8")
        try:
            self.ruta.chmod(0o600)  # Contiene tokens: solo lo lee el dueño.
        except OSError:
            pass

    def version(self):
        """Cambia cuando cambia el contenido (fecha de modificación)."""
        return self.ruta.stat().st_mtime_ns if self.ruta.exists() else None


class AlmacenBD:
    """La caché en la tabla ``msal_cache`` (una fila, ``id=1``).

    ``importar_de``: archivo de caché de antes; si la tabla está vacía y el
    archivo existe, se copia a la base una vez (el archivo no se borra).
    """

    FILA = 1

    def __init__(self, session_factory=None, importar_de: Path | None = None):
        self._session_factory = session_factory
        self.importar_de = Path(importar_de) if importar_de else None

    def __str__(self) -> str:
        return "la base de datos (tabla msal_cache)"

    def _sesion(self):
        if self._session_factory is None:
            from backend.database import SessionLocal

            self._session_factory = SessionLocal
        return self._session_factory()

    def leer(self) -> str | None:
        from backend.models import MsalCache

        with self._sesion() as session:
            fila = session.get(MsalCache, self.FILA)
            if fila is not None:
                return fila.content
        if self.importar_de is not None and self.importar_de.exists():
            texto = self.importar_de.read_text(encoding="utf-8")
            self.guardar(texto)
            logger.info("caché de tokens importada de %s a la base de datos", self.importar_de)
            return texto
        return None

    def guardar(self, texto: str) -> None:
        from backend.models import MsalCache, utc_now

        with self._sesion() as session:
            fila = session.get(MsalCache, self.FILA)
            if fila is None:
                session.add(MsalCache(id=self.FILA, content=texto))
            else:
                fila.content = texto
                fila.updated_at = utc_now()
            session.commit()

    def version(self):
        from backend.models import MsalCache

        with self._sesion() as session:
            return session.scalar(select(MsalCache.updated_at).where(MsalCache.id == self.FILA))


def almacen_de(destino) -> "AlmacenArchivo | AlmacenBD":
    """Acepta un almacén o una ruta (archivo, como antes)."""
    return destino if hasattr(destino, "leer") else AlmacenArchivo(destino)


def almacen_desde_entorno(env=None, session_factory=None) -> AlmacenBD:
    """La caché en la base, importando el archivo de ``CORREO_M365_CACHE``."""
    env = os.environ if env is None else env
    return AlmacenBD(session_factory, importar_de=ruta_cache(env.get("CORREO_M365_CACHE")))


def cargar_cache(destino) -> msal.SerializableTokenCache:
    cache = msal.SerializableTokenCache()
    texto = almacen_de(destino).leer()
    if texto:
        cache.deserialize(texto)
    return cache


def guardar_cache(cache: msal.SerializableTokenCache, destino) -> None:
    if not cache.has_state_changed:
        return
    almacen_de(destino).guardar(cache.serialize())


def crear_app(tenant: str, client_id: str, cache) -> msal.PublicClientApplication:
    return msal.PublicClientApplication(
        client_id,
        authority=f"https://login.microsoftonline.com/{tenant}",
        token_cache=cache,
    )


class ProveedorToken:
    """Entrega un token de acceso para Graph, renovándolo desde la caché.

    La app de msal se crea una sola vez; la caché se vuelve a leer cuando
    cambia (otra versión en el almacén), así un ``correo_login`` hecho con la
    aplicación encendida se toma sin reiniciarla.

    ``almacen``: :class:`AlmacenBD` o :class:`AlmacenArchivo` (una ruta
    también sirve, como antes).
    """

    def __init__(self, tenant: str, client_id: str, usuario: str, almacen,
                 crear=crear_app):
        self.tenant = tenant
        self.client_id = client_id
        self.usuario = usuario
        self.almacen = almacen_de(almacen)
        self._crear = crear
        self._cache = None
        self._app = None
        self._leido = None  # versión de la caché ya cargada

    def _cargar(self):
        """La app de msal con la caché al día; solo se lee de nuevo si cambió."""
        if self._app is not None and self.almacen.version() == self._leido:
            return self._app
        texto = self.almacen.leer()
        if texto is None:
            raise SinSesionError(f"no existe la caché de tokens en {self.almacen}")
        if self._app is None:
            self._cache = msal.SerializableTokenCache()
            self._cache.deserialize(texto)
            self._app = self._crear(self.tenant, self.client_id, self._cache)
        else:
            self._cache.deserialize(texto)
        self._leido = self.almacen.version()
        return self._app

    def obtener(self) -> str:
        if not (self.tenant and self.client_id):
            raise SinSesionError("faltan CORREO_M365_TENANT o CORREO_M365_CLIENT_ID")
        app = self._cargar()
        cuentas = app.get_accounts(username=self.usuario) or app.get_accounts()
        if not cuentas:
            raise SinSesionError("la caché no tiene ninguna cuenta iniciada")
        resultado = app.acquire_token_silent(PERMISOS, account=cuentas[0])
        if self._cache.has_state_changed:
            guardar_cache(self._cache, self.almacen)
            self._cache.has_state_changed = False
            self._leido = self.almacen.version()
        if not resultado or "access_token" not in resultado:
            detalle = (resultado or {}).get("error_description") or "la sesión venció"
            raise SinSesionError(detalle)
        return resultado["access_token"]


def iniciar_sesion(tenant: str, client_id: str, almacen, imprimir=print,
                   crear=crear_app) -> dict:
    """Flujo device code: muestra el código y espera a que se inicie sesión.

    Devuelve el resultado de msal (con ``id_token_claims``). Lanza
    ``SinSesionError`` si no se pudo iniciar.
    """
    cache = cargar_cache(almacen)
    app = crear(tenant, client_id, cache)
    flujo = app.initiate_device_flow(scopes=PERMISOS)
    if "user_code" not in flujo:
        raise SinSesionError(flujo.get("error_description") or "no se pudo iniciar el flujo")
    imprimir(flujo["message"])
    resultado = app.acquire_token_by_device_flow(flujo)
    if "access_token" not in resultado:
        raise SinSesionError(resultado.get("error_description") or "no se completó el inicio de sesión")
    guardar_cache(cache, almacen)
    return resultado
