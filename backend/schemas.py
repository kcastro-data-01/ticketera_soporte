"""Pydantic schemas for ticket input and output validation (Tasks 4 and 6)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from backend.constants import TicketCategory, TicketPriority, TicketState


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
