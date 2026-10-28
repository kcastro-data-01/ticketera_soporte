"""Tests for the domain constants (Task 2)."""

from backend.constants import (
    AUTO_ASSIGN_ROLES,
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
    assert TICKET_CATEGORIES == ("Hardware", "Software", "Red", "Accesos")
    assert TicketCategory.HARDWARE.value == "Hardware"
    assert TicketCategory.SOFTWARE.value == "Software"
    assert TicketCategory.NETWORK.value == "Red"
    assert TicketCategory.ACCESS.value == "Accesos"


def test_priorities_are_the_approved_four():
    assert TICKET_PRIORITIES == ("Baja", "Media", "Alta", "Crítica")
    assert TicketPriority.LOW.value == "Baja"
    assert TicketPriority.MEDIUM.value == "Media"
    assert TicketPriority.HIGH.value == "Alta"
    assert TicketPriority.CRITICAL.value == "Crítica"


def test_user_roles():
    assert USER_ROLES == (
        "Administrador",
        "Técnico",
        "Solicitante",
    )
    assert UserRole.ADMIN.value == "Administrador"
    assert not hasattr(UserRole, "SUPPORT")
    assert not hasattr(UserRole, "SUPERVISOR")
    assert UserRole.TECHNICIAN.value == "Técnico"
    assert UserRole.REQUESTER.value == "Solicitante"


def test_auto_assign_roles_are_tecnico():
    """Only Técnico takes part in the automatic assignment."""
    assert AUTO_ASSIGN_ROLES == ("Técnico",)
    assert set(AUTO_ASSIGN_ROLES) <= set(USER_ROLES)
