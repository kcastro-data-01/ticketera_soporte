"""Authentication endpoints: register, login, and current user."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.auth import (
    create_access_token,
    hash_password,
    verify_password,
)
from backend.constants import UserRole
from backend.database import get_session
from backend.models import User
from backend.schemas import LoginRequest, RegisterRequest, TokenResponse, UserResponse

router = APIRouter(prefix="/api/auth", tags=["Autenticación"])


def _get_user_by_email(session: Session, email: str) -> User | None:
    """Find a user by email (case-insensitive)."""
    return session.scalar(
        select(User).where(func.lower(User.email) == email.lower())
    )


def _count_users_with_password(session: Session) -> int:
    """Count users that have a password hash (i.e., registered via auth)."""
    return session.scalar(
        select(func.count()).select_from(User).where(User.password_hash.is_not(None))
    )


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar un nuevo usuario",
)
def register(payload: RegisterRequest, session: Session = Depends(get_session)) -> TokenResponse:
    """Register a new user and return an access token.

    The first user to register can choose their role (typically Administrador).
    Subsequent registrations are always forced to the Solicitante role.
    """
    # Check if email already exists
    existing = _get_user_by_email(session, payload.email)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"El email {payload.email} ya está registrado",
        )

    # Determine role: first user can choose, rest are forced to Solicitante
    user_count = _count_users_with_password(session)
    if user_count == 0:
        # First registration: allow the requested role (default to Solicitante if not provided)
        role = payload.role if payload.role else UserRole.REQUESTER
    else:
        # Subsequent registrations: always Solicitante
        role = UserRole.REQUESTER

    # Create the user with hashed password
    user = User(
        name=payload.name,
        email=payload.email,
        role=role.value,
        password_hash=hash_password(payload.password),
    )
    session.add(user)
    session.commit()
    session.refresh(user)

    # Generate and return token
    token, expires_in = create_access_token(user.id, user.role)
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=expires_in,
    )


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Iniciar sesión",
)
def login(payload: LoginRequest, session: Session = Depends(get_session)) -> TokenResponse:
    """Authenticate a user and return an access token."""
    user = _get_user_by_email(session, payload.email)

    # Check if user exists and has a password
    if user is None or user.password_hash is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales inválidas",
        )

    # Verify password
    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales inválidas",
        )

    # Check if user is active
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El usuario está desactivado",
        )

    # Generate and return token
    token, expires_in = create_access_token(user.id, user.role)
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=expires_in,
    )


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Obtener usuario actual",
)
def get_current_user_info(
    token: str,
    session: Session = Depends(get_session),
) -> UserResponse:
    """Return the currently authenticated user's information.

    Requires a valid Bearer token in the Authorization header.
    """
    from fastapi import HTTPException, status
    from backend.auth import decode_access_token
    import jwt

    try:
        payload = decode_access_token(token)
        user_id = int(payload.get("sub"))
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado",
        )

    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado",
        )

    return UserResponse.model_validate(user)
