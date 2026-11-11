"""Authentication utilities: password hashing and JWT token management."""

import os
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from backend.database import get_session
from backend.entorno import en_vercel
from backend.models import User

# Configuration (can be overridden via environment variables)
JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "").strip() or "dev-secret-key-change-in-production"
if en_vercel() and JWT_SECRET_KEY == "dev-secret-key-change-in-production":
    # Con la clave de desarrollo (pública en el repositorio) cualquiera podría
    # fabricar una sesión: la versión publicada no arranca sin su propia clave.
    raise RuntimeError("Falta JWT_SECRET_KEY en las variables de entorno de Vercel")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_MINUTES = int(os.environ.get("JWT_EXPIRATION_MINUTES", "60"))


def _sesion_maxima_horas() -> float:
    """``SESION_MAXIMA_HORAS`` (10 por defecto): pasado ese tiempo desde el
    inicio de sesión, ninguna renovación la alarga y hay que volver a entrar.
    Acepta decimales (``0.1`` = 6 minutos, para probar en local)."""
    valor = (os.environ.get("SESION_MAXIMA_HORAS") or "").strip().replace(",", ".")
    try:
        horas = float(valor) if valor else 10.0
    except ValueError:
        horas = 10.0
    return horas if horas > 0 else 10.0


SESION_MAXIMA_HORAS = _sesion_maxima_horas()

# Security scheme for extracting Bearer token from Authorization header
bearer_scheme = HTTPBearer(auto_error=False)


def login_local_activo() -> bool:
    """``LOGIN_LOCAL=true``: solo para desarrollo, se mantiene el inicio de
    sesión con contraseña (por defecto, solo con Microsoft). En Vercel
    (público) nunca: solo se entra con Microsoft."""
    if en_vercel():
        return False
    return (os.environ.get("LOGIN_LOCAL") or "").strip().lower() in ("1", "true", "si", "sí", "yes")


def hash_password(plain_password: str) -> str:
    """Hash a plain-text password using bcrypt."""
    # bcrypt has a 72-byte limit; truncate if necessary
    password_bytes = plain_password.encode("utf-8")[:72]
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password_bytes, salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain-text password against a bcrypt hash."""
    password_bytes = plain_password.encode("utf-8")[:72]
    hashed_bytes = hashed_password.encode("utf-8")
    return bcrypt.checkpw(password_bytes, hashed_bytes)


def create_access_token(user_id: int, role: str, inicio: datetime | None = None) -> tuple[str, int]:
    """Create a JWT access token.

    ``inicio`` es cuándo se inició la sesión (por defecto, ahora): la
    renovación lo conserva. El token dura ``JWT_EXPIRATION_MINUTES`` pero
    nunca pasa de ``inicio`` + ``SESION_MAXIMA_HORAS`` (claims ``ini`` y
    ``max``, en segundos Unix, para que el navegador sepa cuándo termina).

    Returns a tuple of (token, expires_in_seconds).
    """
    ahora = datetime.now(timezone.utc)
    inicio = inicio or ahora
    maximo = inicio + timedelta(hours=SESION_MAXIMA_HORAS)
    expire = min(ahora + timedelta(minutes=JWT_EXPIRATION_MINUTES), maximo)

    payload = {
        "sub": str(user_id),
        "role": role,
        "exp": expire,
        "iat": ahora,
        "ini": int(inicio.timestamp()),
        "max": int(maximo.timestamp()),
    }

    token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    expires_in = max(0, int((expire - ahora).total_seconds()))
    return token, expires_in


def inicio_de_sesion(payload: dict) -> datetime:
    """Cuándo empezó la sesión de un token (``ini``; los tokens de antes de
    la sesión deslizante no lo traen y se usa ``iat``)."""
    valor = payload.get("ini", payload.get("iat", 0))
    return datetime.fromtimestamp(int(valor), tz=timezone.utc)


def inicio_valido(valor: int | float | None) -> datetime | None:
    """Un inicio de sesión que manda el navegador al volver a entrar en
    silencio: sirve solo si está en el pasado y dentro del máximo (si no,
    ``None`` y la sesión empieza ahora). Solo puede acortar la sesión."""
    if valor is None:
        return None
    try:
        inicio = datetime.fromtimestamp(float(valor), tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None
    ahora = datetime.now(timezone.utc)
    if inicio > ahora or ahora - inicio >= timedelta(hours=SESION_MAXIMA_HORAS):
        return None
    return inicio


def decode_access_token(token: str) -> dict:
    """Decode and validate a JWT access token.

    Raises ``jwt.ExpiredSignatureError`` if the token has expired.
    Raises ``jwt.InvalidTokenError`` if the token is invalid.
    """
    return jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: Session = Depends(get_session),
) -> User | None:
    """FastAPI dependency that extracts and validates the Bearer token.

    Returns the authenticated ``User`` instance, or ``None`` if no token is
    provided or the token is invalid/expired. The API is open by design:
    users exist only for ticket assignment and comment signing, not for
    authentication.
    """
    if credentials is None:
        return None

    token = credentials.credentials
    try:
        payload = decode_access_token(token)
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None

    user_id = int(payload.get("sub", "0"))
    user = session.get(User, user_id)
    # A deactivated user loses access immediately, even with a valid token.
    if user is None or not user.is_active:
        return None

    return user
