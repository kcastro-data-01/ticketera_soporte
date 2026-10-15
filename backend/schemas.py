"""Pydantic schemas for input and output validation (Tasks 4, 6 and 8)."""

import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from backend.constants import TicketCategory, TicketPriority, TicketState, UserRole

_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Password length accepted when an administrator creates or edits a user.
# bcrypt only uses the first 72 bytes, so longer values are rejected.
PASSWORD_MIN_LENGTH = 6
PASSWORD_MAX_LENGTH = 72


def _validate_password(value: str) -> str:
    if len(value) < PASSWORD_MIN_LENGTH:
        raise ValueError(
            f"la contraseña debe tener al menos {PASSWORD_MIN_LENGTH} caracteres"
        )
    if len(value.encode("utf-8")) > PASSWORD_MAX_LENGTH:
        raise ValueError(
            f"la contraseña debe tener como máximo {PASSWORD_MAX_LENGTH} caracteres"
        )
    return value


# Maximum length of a comment body, validated at the API layer (Task 9).
COMMENT_MAX_LENGTH = 2000


def _validate_title(value: str) -> str:
    """Shared rule (creation and edition): trimmed length between 3 and 200."""
    cleaned = value.strip()
    if len(cleaned) < 3:
        raise ValueError("el título debe tener al menos 3 caracteres")
    if len(cleaned) > 200:
        raise ValueError("el título debe tener como máximo 200 caracteres")
    return cleaned


def _validate_description(value: str) -> str:
    """Shared rule (creation and edition): the description cannot be blank."""
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("la descripción no puede estar vacía")
    return cleaned


class TicketCreate(BaseModel):
    """Payload accepted by ``POST /api/tickets`` (RF1, RF2)."""

    title: str
    description: str
    category: TicketCategory
    priority: TicketPriority

    @field_validator("title")
    @classmethod
    def title_must_be_valid(cls, value: str) -> str:
        return _validate_title(value)

    @field_validator("description")
    @classmethod
    def description_must_not_be_blank(cls, value: str) -> str:
        return _validate_description(value)


class TicketUpdate(BaseModel):
    """Payload accepted by ``PATCH /api/tickets/{ticket_id}`` (partial update).

    Only the editable fields exist here: ``id``, ``state``, ``assigned_to_id``
    and ``created_at`` cannot be modified through this payload. Unknown extra
    keys are ignored, so they never reach the service layer.
    """

    title: str | None = None
    description: str | None = None
    category: TicketCategory | None = None
    priority: TicketPriority | None = None

    @field_validator("title")
    @classmethod
    def title_must_be_valid(cls, value: str | None) -> str | None:
        return _validate_title(value) if value is not None else None

    @field_validator("description")
    @classmethod
    def description_must_not_be_blank(cls, value: str | None) -> str | None:
        return _validate_description(value) if value is not None else None

    @model_validator(mode="after")
    def at_least_one_modifiable_field(self) -> "TicketUpdate":
        """Reject payloads without any field to update (no empty updates)."""
        provided = {
            name
            for name in self.model_fields_set
            if getattr(self, name) is not None
        }
        if not provided:
            raise ValueError(
                "la petición debe incluir al menos un campo a modificar: "
                "title, description, category o priority"
            )
        return self


class TicketResponse(BaseModel):
    """Ticket returned by the API after its creation."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str
    category: TicketCategory
    priority: TicketPriority
    state: TicketState
    assigned_to_id: int | None = None
    created_by_id: int | None = None
    created_at: datetime
    updated_at: datetime


class UserCreate(BaseModel):
    """Payload accepted by ``POST /api/users`` (minimal user data).

    ``role`` is optional and defaults to ``Técnico`` (the same default the
    database applies); an explicit value must still be a valid role.
    ``password`` is required so the new user can log in.
    """

    name: str
    email: str
    password: str
    role: UserRole = UserRole.TECHNICIAN

    @field_validator("password")
    @classmethod
    def password_must_be_valid(cls, value: str) -> str:
        return _validate_password(value)

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("el nombre no puede estar vacío")
        if len(cleaned) > 120:
            raise ValueError("el nombre debe tener como máximo 120 caracteres")
        return cleaned

    @field_validator("email")
    @classmethod
    def email_must_be_valid(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if not _EMAIL_PATTERN.match(cleaned):
            raise ValueError("el email no tiene un formato válido")
        if len(cleaned) > 255:
            raise ValueError("el email debe tener como máximo 255 caracteres")
        return cleaned


class UserUpdate(BaseModel):
    """Payload accepted by ``PATCH /api/users/{user_id}`` (partial update).

    Only the editable fields exist here: ``id`` cannot be modified.
    ``is_active`` deactivates (``false``) or reactivates (``true``) the user.
    At least one field must be provided.
    """

    name: str | None = None
    email: str | None = None
    role: UserRole | None = None
    password: str | None = None
    is_active: bool | None = None

    @field_validator("password")
    @classmethod
    def password_must_be_valid(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _validate_password(value)

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("el nombre no puede estar vacío")
        if len(cleaned) > 120:
            raise ValueError("el nombre debe tener como máximo 120 caracteres")
        return cleaned

    @field_validator("email")
    @classmethod
    def email_must_be_valid(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip().lower()
        if not _EMAIL_PATTERN.match(cleaned):
            raise ValueError("el email no tiene un formato válido")
        if len(cleaned) > 255:
            raise ValueError("el email debe tener como máximo 255 caracteres")
        return cleaned

    @model_validator(mode="after")
    def at_least_one_modifiable_field(self) -> "UserUpdate":
        """Reject payloads without any field to update (no empty updates)."""
        provided = {
            name
            for name in self.model_fields_set
            if getattr(self, name) is not None
        }
        if not provided:
            raise ValueError(
                "la petición debe incluir al menos un campo a modificar: "
                "name, email, role, password o is_active"
            )
        return self


class UserResponse(BaseModel):
    """User returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str
    role: UserRole
    is_active: bool = True


class TicketAssignment(BaseModel):
    """Payload accepted by ``PATCH /api/tickets/{ticket_id}/assign``.

    ``assigned_to_id`` is required but nullable: ``null`` unassigns the ticket.
    """

    assigned_to_id: int | None


class TicketStateUpdate(BaseModel):
    """Payload accepted by ``PATCH /api/tickets/{ticket_id}/state`` (RF3).

    Reuses the existing ``TicketState`` enum: an unknown value is rejected
    with the usual FastAPI/Pydantic ``422``.
    """

    state: TicketState


class CommentCreate(BaseModel):
    """Payload accepted by ``POST /api/tickets/{ticket_id}/comments``.

    ``ticket_id`` comes from the URL path, not from the body. ``author`` is
    optional (no authentication). If not supplied, the backend determines the
    author from the ticket's assigned user; otherwise it defaults to ``"Anónimo"``.
    """

    content: str
    author: str | None = None

    @field_validator("content")
    @classmethod
    def content_must_not_be_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("el contenido no puede estar vacío")
        if len(cleaned) > COMMENT_MAX_LENGTH:
            raise ValueError(
                f"el contenido debe tener como máximo {COMMENT_MAX_LENGTH} caracteres"
            )
        return cleaned

    @field_validator("author")
    @classmethod
    def author_must_not_be_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("el autor no puede estar vacío")
        if len(cleaned) > 120:
            raise ValueError("el autor debe tener como máximo 120 caracteres")
        return cleaned


class CommentResponse(BaseModel):
    """Comment returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    ticket_id: int
    author: str
    content: str
    created_at: datetime


class HistoryResponse(BaseModel):
    """History entry returned by ``GET /api/tickets/{ticket_id}/history`` (RF9).

    Mirrors the ``History`` model as-is: ``field``, ``old_value``,
    ``new_value``, ``author`` and ``author_id`` are optional and come back
    as ``null`` when the record does not provide them. ``author`` carries the
    display name of the authenticated user that performed the action;
    ``author_id`` is the referenced user (``null`` for legacy rows).
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    ticket_id: int
    ticket_title: str | None = None
    action: str
    field: str | None = None
    old_value: str | None = None
    new_value: str | None = None
    author: str | None = None
    author_id: int | None = None
    created_at: datetime


# --- Authentication schemas ---


class LoginRequest(BaseModel):
    """Payload accepted by ``POST /api/auth/login``."""

    email: str
    password: str

    @field_validator("email")
    @classmethod
    def email_must_not_be_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("el email no puede estar vacío")
        return cleaned

    @field_validator("password")
    @classmethod
    def password_must_not_be_blank(cls, value: str) -> str:
        if not value:
            raise ValueError("la contraseña no puede estar vacía")
        return value


class ChangePasswordRequest(BaseModel):
    """Payload accepted by ``POST /api/auth/change-password``."""

    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def new_password_must_be_valid(cls, value: str) -> str:
        return _validate_password(value)


class SetupResponse(BaseModel):
    """``needs_setup`` is true while no user can log in yet (first run)."""

    needs_setup: bool


class TicketSummary(BaseModel):
    """Ticket counters for the dashboard, limited to the visible tickets."""

    total: int
    nuevos: int
    en_proceso: int
    resueltos: int
    cerrados: int
    criticos_abiertos: int
    mios_abiertos: int


class RegisterRequest(BaseModel):
    """Payload accepted by ``POST /api/auth/register``."""

    name: str
    email: str
    password: str
    role: UserRole | None = None

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("el nombre no puede estar vacío")
        if len(cleaned) > 120:
            raise ValueError("el nombre debe tener como máximo 120 caracteres")
        return cleaned

    @field_validator("email")
    @classmethod
    def email_must_be_valid(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if not _EMAIL_PATTERN.match(cleaned):
            raise ValueError("el email no tiene un formato válido")
        if len(cleaned) > 255:
            raise ValueError("el email debe tener como máximo 255 caracteres")
        return cleaned

    @field_validator("password")
    @classmethod
    def password_must_be_strong_enough(cls, value: str) -> str:
        if len(value) < 6:
            raise ValueError("la contraseña debe tener al menos 6 caracteres")
        if len(value) > 128:
            raise ValueError("la contraseña debe tener como máximo 128 caracteres")
        return value


class TokenResponse(BaseModel):
    """Response returned after successful registration or login."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int
