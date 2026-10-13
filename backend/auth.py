"""Authentication utilities: password hashing and JWT token management."""

import os
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

# Configuration (can be overridden via environment variables)
JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "dev-secret-key-change-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_MINUTES = int(os.environ.get("JWT_EXPIRATION_MINUTES", "60"))


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
