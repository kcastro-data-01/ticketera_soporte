"""Authentication utilities: password hashing and JWT token management."""

import os
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from backend.database import get_session
from backend.models import User

# Configuration (can be overridden via environment variables)
JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "dev-secret-key-change-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_MINUTES = int(os.environ.get("JWT_EXPIRATION_MINUTES", "60"))

# Security scheme for extracting Bearer token from Authorization header
bearer_scheme = HTTPBearer(auto_error=False)


def login_local_activo() -> bool:
    """``LOGIN_LOCAL=true``: solo para desarrollo, se mantiene el inicio de
    sesión con contraseña (por defecto, solo con Microsoft)."""
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


def create_access_token(user_id: int, role: str) -> tuple[str, int]:
    """Create a JWT access token.

    Returns a tuple of (token, expires_in_seconds).
    """
    expires_delta = timedelta(minutes=JWT_EXPIRATION_MINUTES)
    expire = datetime.now(timezone.utc) + expires_delta

    payload = {
        "sub": str(user_id),
        "role": role,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }

    token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    expires_in = int(expires_delta.total_seconds())
    return token, expires_in


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
