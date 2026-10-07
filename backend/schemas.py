"""Pydantic schemas for input and output validation (Tasks 4, 6 and 8)."""

import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from backend.constants import TicketCategory, TicketPriority, TicketState, UserRole

_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

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
    created_at: datetime
    updated_at: datetime


class UserCreate(BaseModel):
    """Payload accepted by ``POST /api/users`` (minimal user data)."""

    name: str
    email: str
    role: UserRole

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


class UserResponse(BaseModel):
    """User returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str
    role: UserRole


class TicketAssignment(BaseModel):
    """Payload accepted by ``PATCH /api/tickets/{ticket_id}/assign``.

    ``assigned_to_id`` is required but nullable: ``null`` unassigns the ticket.
    """

    assigned_to_id: int | None


class CommentCreate(BaseModel):
    """Payload accepted by ``POST /api/tickets/{ticket_id}/comments``.

    ``ticket_id`` comes from the URL path, not from the body. ``author`` is
    optional (no authentication) and defaults to "Anónimo".
    """

    content: str
    author: str = "Anónimo"

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
