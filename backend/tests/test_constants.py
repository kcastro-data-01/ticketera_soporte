"""Tests for the domain constants (Task 2)."""

from backend.constants import (
    TICKET_CATEGORIES,
    TICKET_PRIORITIES,
    TICKET_STATES,
    USER_ROLES,
    TicketCategory,
    TicketPriority,
    TicketState,
    UserRole,
)


def test_states_are_the_approved_four():
    assert TICKET_STATES == ("Nuevo", "En proceso", "Resuelto", "Cerrado")
    assert TicketState.NEW.value == "Nuevo"
    assert TicketState.IN_PROGRESS.value == "En proceso"
    assert TicketState.RESOLVED.value == "Resuelto"
    assert TicketState.CLOSED.value == "Cerrado"


def test_categories_are_the_approved_four():
    assert TICKET_CATEGORIES == ("Incidente", "Consulta", "Solicitud", "Mantenimiento")
    assert TicketCategory.INCIDENT.value == "Incidente"
    assert TicketCategory.INQUIRY.value == "Consulta"
    assert TicketCategory.REQUEST.value == "Solicitud"
    assert TicketCategory.MAINTENANCE.value == "Mantenimiento"


def test_priorities_are_the_approved_four():
    assert TICKET_PRIORITIES == ("Baja", "Media", "Alta", "Crítica")
    assert TicketPriority.LOW.value == "Baja"
    assert TicketPriority.MEDIUM.value == "Media"
    assert TicketPriority.HIGH.value == "Alta"
    assert TicketPriority.CRITICAL.value == "Crítica"


def test_user_roles():
    assert USER_ROLES == ("Administrador", "Soporte")
    assert UserRole.ADMIN.value == "Administrador"
    assert UserRole.SUPPORT.value == "Soporte"
