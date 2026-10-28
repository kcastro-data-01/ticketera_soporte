"""Authentication endpoints: Microsoft login, local login (development
only, ``LOGIN_LOCAL``) and current user."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.auth import (
    create_access_token,
    get_current_user,
    login_local_activo,
    verify_password,
)
from backend.constants import UserRole
from backend.database import get_session
from backend.models import User
from backend.schemas import (
    LoginConfigResponse,
    LoginRequest,
    MicrosoftLoginRequest,
    TokenResponse,
    UserResponse,
)
from backend.services import login_microsoft

router = APIRouter(prefix="/api/auth", tags=["Autenticación"])

# Roles permitidos por endpoint
ROLES_ADMIN = {UserRole.ADMIN.value}

# Grupos de la tabla de permisos (ver ayuda.html → "Permisos por rol").
# Todos los roles: ver tickets (el Solicitante solo los suyos), crear y comentar.
ROLES_TODOS = {role.value for role in UserRole}
# Todos menos el Solicitante: cambiar estado, historial global y «Explicar con IA».
# Lo demás (editar, asignar, métricas, eliminar y usuarios) es solo ROLES_ADMIN.
ROLES_EQUIPO = ROLES_TODOS - {UserRole.REQUESTER.value}


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


def _token_de(user: User) -> TokenResponse:
    token, expires_in = create_access_token(user.id, user.role)
    return TokenResponse(access_token=token, token_type="bearer", expires_in=expires_in)


@router.get(
    "/config",
    response_model=LoginConfigResponse,
    summary="Datos públicos para iniciar sesión",
)
def login_config() -> LoginConfigResponse:
    """Public: what login.html needs to start the Microsoft login (MSAL.js)
    and whether the password form is enabled (``LOGIN_LOCAL``)."""
    return LoginConfigResponse(
        tenant=login_microsoft.tenant(),
        client_id=login_microsoft.client_id(),
        login_local=login_local_activo(),
    )


@router.post(
    "/microsoft",
    response_model=TokenResponse,
    summary="Iniciar sesión con Microsoft",
)
def login_with_microsoft(
    payload: MicrosoftLoginRequest, session: Session = Depends(get_session)
) -> TokenResponse:
    """Validate the Microsoft ``id_token`` (signature, audience, issuer and
    tenant) and return the app session. New users are created with the role
    from ``asignar_rol_inicial``; existing users keep theirs."""
    try:
        claims = login_microsoft.validar_id_token(payload.id_token)
        user = login_microsoft.usuario_desde_microsoft(session, claims)
    except login_microsoft.LoginNoConfigurado:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="El inicio de sesión con Microsoft no está configurado",
        )
    except login_microsoft.TokenInvalido as error:
        login_microsoft.logger.warning("inicio de sesión con Microsoft rechazado: %s", error)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No se pudo validar la cuenta de Microsoft",
        )
    except login_microsoft.UsuarioDesactivado:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El usuario está desactivado",
        )
    return _token_de(user)


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Iniciar sesión",
)
def login(payload: LoginRequest, session: Session = Depends(get_session)) -> TokenResponse:
    """Authenticate with email and password. Only for development, with
    ``LOGIN_LOCAL=true``; otherwise the endpoint does not exist (404)."""
    if not login_local_activo():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")
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

    return _token_de(user)
