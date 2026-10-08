"""User endpoints (Task 8: creation and listing, no authentication)."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.database import get_session
from backend.schemas import UserCreate, UserResponse
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
def list_users(session: Session = Depends(get_session)) -> list[UserResponse]:
    """Return the active users available for assignment (read-only)."""
    users = user_service.list_users(session)
    return [UserResponse.model_validate(user) for user in users]
