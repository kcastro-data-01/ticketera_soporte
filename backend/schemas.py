"""Pydantic schemas for ticket input and output validation (Task 4)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from backend.constants import TicketCategory, TicketPriority, TicketState


class TicketCreate(BaseModel):
    """Payload accepted by ``POST /api/tickets`` (RF1, RF2)."""

    title: str
    description: str
    category: TicketCategory
    priority: TicketPriority

    @field_validator("title")
    @classmethod
    def title_must_be_valid(cls, value: str) -> str:
        """Mirror the database CHECK: trimmed length between 3 and 200."""
        cleaned = value.strip()
        if len(cleaned) < 3:
            raise ValueError("el título debe tener al menos 3 caracteres")
        if len(cleaned) > 200:
            raise ValueError("el título debe tener como máximo 200 caracteres")
        return cleaned

    @field_validator("description")
    @classmethod
    def description_must_not_be_blank(cls, value: str) -> str:
        """Mirror the database CHECK: the description cannot be blank."""
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("la descripción no puede estar vacía")
        return cleaned


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
