"""Authentication endpoints: register, login, and current user."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.auth import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from backend.constants import UserRole
from backend.database import get_session
from backend.models import User
from backend.schemas import LoginRequest, RegisterRequest, TokenResponse, UserResponse

router = APIRouter(prefix="/api/auth", tags=["Autenticación"])

# Roles permitidos por endpoint
ROLES_ADMIN = {UserRole.ADMIN.value}
ROLES_SOPORTE = {UserRole.SUPPORT.value, UserRole.ADMIN.value}
ROLES_SUPERVISOR = {UserRole.SUPERVISOR.value, UserRole.ADMIN.value}
ROLES_TECNICO = {UserRole.TECHNICIAN.value, UserRole.ADMIN.value}
ROLES_SOLICITANTE = {UserRole.REQUESTER.value, UserRole.ADMIN.value}

# Grupos de la tabla de permisos (ver ayuda.html → "Permisos por rol").
# Todos los roles: ver tickets (el Solicitante solo los suyos), crear y comentar.
ROLES_TODOS = {role.value for role in UserRole}
# Todos menos el Solicitante: cambiar estado e historial global.
ROLES_EQUIPO = ROLES_TODOS - {UserRole.REQUESTER.value}
# Gestión de tickets: editar y asignar.
ROLES_GESTION = {
    UserRole.ADMIN.value,
    UserRole.SUPERVISOR.value,
    UserRole.SUPPORT.value,
}


def role_required(allowed_roles: set[str]) -> callable:
    """Dependency that checks if the current user has one of the allowed roles.

    Raises 403 Forbidden when the user doesn't have the required role.
    Works with the existing ``get_current_user`` dependency: if the user is
    ``None`` (no token), the 401 from ``get_current_user`` takes precedence.
    """

    def dependency(current_user: User | None = Depends(get_current_user)) -> User:
        if current_user is None:
            # Dejar que la dependencia original levante 401
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="No autenticado",
            )
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tiene permisos para acceder a este recurso",
            )
        return current_user

    return dependency


def optional_role_required(allowed_roles: set[str]) -> callable:
    """Dependency that checks roles only when a user is authenticated.

    If no user is authenticated (``current_user is None``), it returns the
    user (None) and allows the request to proceed. This preserves the "open
    by design" API behavior while still restricting authenticated users.

    Raises 403 Forbidden when an authenticated user doesn't have the required
    role.
    """

    def dependency(current_user: User | None = Depends(get_current_user)) -> User | None:
        if current_user is None:
            # Sin token: permitir el acceso (API abierta por diseño)
            return None
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tiene permisos para acceder a este recurso",
            )
        return current_user

    return dependency


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Obtener usuario actual",
)
def get_current_user_info(
    current_user: User | None = Depends(get_current_user),
) -> UserResponse:
    """Return the currently authenticated user's information.

    Requires a valid Bearer token in the Authorization header.
    """
    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No autenticado",
        )
    return UserResponse.model_validate(current_user)


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
