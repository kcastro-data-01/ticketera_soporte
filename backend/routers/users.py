"""User endpoints (Task 8: creation and listing, no authentication)."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.auth import get_current_user
from backend.database import get_session
from backend.models import User
from backend.routers.auth import ROLES_ADMIN, ROLES_TODOS, role_required
from backend.schemas import UserCreate, UserResponse, UserUpdate
from backend.services import user_service

router = APIRouter(prefix="/api/users", tags=["Usuarios"])


@router.post(
    "",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear un usuario",
)
def create_user(
    payload: UserCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(
        role_required(ROLES_ADMIN)
    ),
) -> UserResponse:
    """Create a minimal user used to own tickets (name, email, role)."""
    user = user_service.create_user(session, payload)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"El email {payload.email} ya está registrado",
        )
    return UserResponse.model_validate(user)


@router.get(
    "",
    response_model=list[UserResponse],
    summary="Listar usuarios",
)
def list_users(
    todos: bool = Query(
        False,
        description="Incluye usuarios desactivados (solo Administrador).",
    ),
    session: Session = Depends(get_session),
    current_user: User = Depends(
        role_required(ROLES_TODOS)
    ),
) -> list[UserResponse]:
    """Return the active users available for assignment (read-only).

    An administrator can pass ``todos=true`` to also get deactivated users.
    """
    include_inactive = todos and current_user.role in ROLES_ADMIN
    users = user_service.list_users(session, include_inactive=include_inactive)
    return [UserResponse.model_validate(user) for user in users]


@router.patch(
    "/{user_id}",
    response_model=UserResponse,
    summary="Actualizar un usuario",
)
def update_user(
    user_id: int,
    payload: UserUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(
        role_required(ROLES_ADMIN)
    ),
) -> UserResponse:
    """Update an existing user (partial update)."""
    if payload.is_active is False and user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No puedes desactivar tu propio usuario",
        )
    try:
        user = user_service.update_user(session, user_id, payload)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Usuario {user_id} no encontrado",
        )
    return UserResponse.model_validate(user)
