"""Inicio de sesión con la cuenta de Microsoft de la empresa (Entra ID).

El navegador inicia sesión con MSAL.js (flujo de código con PKCE) usando la
app ya registrada (``CORREO_M365_TENANT`` y ``CORREO_M365_CLIENT_ID``) y manda
el ``id_token`` al backend. Aquí se valida:

* la firma, con las claves públicas de Microsoft del tenant (``jwks_uri``),
* la audiencia (= ``CORREO_M365_CLIENT_ID``), el emisor (= el tenant) y el
  vencimiento,
* que ``tid`` sea el del tenant: solo entran cuentas de la empresa,
* que no sea un invitado (B2B) del tenant: el ``idp`` (si viene) es el mismo
  tenant y el correo es del dominio ``DOMINIO_EMPRESA`` (p. ej. ``data.cr``).

Con los datos del token se busca o se crea el usuario de la ticketera y el
router entrega la sesión de la app como siempre (JWT propio). El rol de los
usuarios nuevos lo decide :func:`asignar_rol_inicial`.
"""

import logging
import os
import threading

import httpx
import jwt
from sqlalchemy import func, select

from backend.constants import UserRole
from backend.models import User

logger = logging.getLogger(__name__)

AUTORIDAD = "https://login.microsoftonline.com"
TIMEOUT_MICROSOFT = 10.0


class LoginNoConfigurado(Exception):
    """Faltan ``CORREO_M365_TENANT`` o ``CORREO_M365_CLIENT_ID``."""


class TokenInvalido(Exception):
    """El id_token no es válido o no es de una cuenta de la empresa."""


class UsuarioDesactivado(Exception):
    """La cuenta existe en la ticketera pero está desactivada."""


def tenant() -> str:
    return (os.environ.get("CORREO_M365_TENANT") or "").strip()


def client_id() -> str:
    return (os.environ.get("CORREO_M365_CLIENT_ID") or "").strip()


def dominio_empresa() -> str:
    """``DOMINIO_EMPRESA`` sin «@» (vacío: no se revisa el dominio)."""
    return (os.environ.get("DOMINIO_EMPRESA") or "").strip().lower().lstrip("@")


def admin_inicial() -> str:
    """``ADMIN_INICIAL``: el correo que entra siempre como Administrador."""
    return (os.environ.get("ADMIN_INICIAL") or "").strip().lower()


# --- Configuración pública del tenant -------------------------------------

_cache_openid: dict[str, dict] = {}
_clientes_jwks: dict[str, jwt.PyJWKClient] = {}
_candado = threading.Lock()


def config_openid() -> dict:
    """``issuer`` y ``jwks_uri`` del tenant (sirve con el GUID o el dominio),
    leídos una vez de la configuración pública de Microsoft."""
    t = tenant()
    with _candado:
        if t not in _cache_openid:
            url = f"{AUTORIDAD}/{t}/v2.0/.well-known/openid-configuration"
            try:
                respuesta = httpx.get(url, timeout=TIMEOUT_MICROSOFT)
                respuesta.raise_for_status()
                datos = respuesta.json()
            except (httpx.HTTPError, ValueError) as error:
                raise TokenInvalido(f"no se pudo leer la configuración del tenant: {error}") from error
            _cache_openid[t] = {"issuer": datos["issuer"], "jwks_uri": datos["jwks_uri"]}
        return _cache_openid[t]


def clave_publica(token: str, jwks_uri: str):
    """La clave pública de Microsoft con la que se firmó ``token`` (por ``kid``)."""
    with _candado:
        cliente = _clientes_jwks.setdefault(jwks_uri, jwt.PyJWKClient(jwks_uri, cache_keys=True))
    try:
        return cliente.get_signing_key_from_jwt(token).key
    except jwt.PyJWKClientError as error:
        raise TokenInvalido(f"clave de firma desconocida: {error}") from error


# --- Validación del token -------------------------------------------------


def validar_id_token(token: str) -> dict:
    """Los datos (claims) del ``id_token`` si es válido y de la empresa."""
    if not tenant() or not client_id():
        raise LoginNoConfigurado("faltan CORREO_M365_TENANT o CORREO_M365_CLIENT_ID")
    config = config_openid()
    try:
        claims = jwt.decode(
            token,
            clave_publica(token, config["jwks_uri"]),
            algorithms=["RS256"],
            audience=client_id(),
            issuer=config["issuer"],
            options={"require": ["exp", "iat", "aud", "iss", "tid"]},
        )
    except jwt.InvalidTokenError as error:
        raise TokenInvalido(str(error)) from error
    # El emisor ya es el del tenant; ``tid`` lo confirma (otra organización
    # tendría otro).
    if f"/{claims['tid']}/" not in config["issuer"]:
        raise TokenInvalido("la cuenta no es del tenant de la empresa")
    # Un invitado trae el tid de la empresa, pero ``idp`` dice dónde se
    # autenticó (su propia organización, una cuenta personal…).
    idp = claims.get("idp")
    if idp and claims["tid"] not in idp:
        raise TokenInvalido(f"cuenta invitada (idp {idp})")
    dominio = dominio_empresa()
    if dominio:
        correo, _ = datos_de_microsoft(claims)
        if not correo.endswith("@" + dominio):
            raise TokenInvalido(f"el correo {correo} no es del dominio {dominio}")
    return claims


def datos_de_microsoft(claims: dict) -> tuple[str, str]:
    """``(correo, nombre)`` de la cuenta, el correo en minúsculas."""
    correo = (claims.get("email") or claims.get("preferred_username") or "").strip().lower()
    if "@" not in correo:
        raise TokenInvalido("el token no trae el correo de la cuenta")
    nombre = (claims.get("name") or "").strip() or correo.split("@")[0]
    return correo, nombre[:120]


# --- Usuarios y roles -----------------------------------------------------


def asignar_rol_inicial(correo: str, claims: dict | None = None) -> UserRole:
    """Rol con el que se crea un usuario nuevo.

    ``ADMIN_INICIAL`` es Administrador; los demás, Solicitante. ``claims``
    (los datos de Microsoft, o ``None`` si llega por correo) queda para
    agregar reglas por puesto o departamento.
    """
    if correo.strip().lower() == admin_inicial():
        return UserRole.ADMIN
    return UserRole.REQUESTER


def usuario_desde_microsoft(session, claims: dict) -> User:
    """El usuario de la ticketera para esa cuenta: lo crea si no existe (con
    nombre y correo de Microsoft); si existe mantiene su rol, salvo
    ``ADMIN_INICIAL``, que siempre es Administrador."""
    correo, nombre = datos_de_microsoft(claims)
    usuario = session.scalar(select(User).where(func.lower(User.email) == correo))
    if usuario is None:
        usuario = User(name=nombre, email=correo, role=asignar_rol_inicial(correo, claims).value)
        session.add(usuario)
        logger.info("usuario nuevo desde Microsoft: %s (%s)", correo, usuario.role)
    elif not usuario.is_active:
        raise UsuarioDesactivado(correo)
    elif correo == admin_inicial() and usuario.role != UserRole.ADMIN.value:
        usuario.role = UserRole.ADMIN.value
    session.commit()
    session.refresh(usuario)
    return usuario
