"""Domain constants for the support ticket system.

Enum *values* are written in Spanish because they are displayed directly in
the user interface. Identifiers (member names, variables, functions) are in
English, following the approved language decision.
"""

from enum import Enum


class TicketState(str, Enum):
    """Workflow states of a ticket (RF3)."""

    NEW = "Nuevo"
    IN_PROGRESS = "En proceso"
    RESOLVED = "Resuelto"
    CLOSED = "Cerrado"


class TicketPriority(str, Enum):
    """Priority levels of a ticket (RF2)."""

    LOW = "Baja"
    MEDIUM = "Media"
    HIGH = "Alta"
    CRITICAL = "Crítica"


class TicketCategory(str, Enum):
    """Fixed categories of a ticket (RF2)."""

    INCIDENT = "Incidente"
    INQUIRY = "Consulta"
    REQUEST = "Solicitud"
    MAINTENANCE = "Mantenimiento"


class UserRole(str, Enum):
    """Roles of the minimal users used to assign tickets (RF4)."""

    ADMIN = "Administrador"
    SUPPORT = "Soporte"
    SUPERVISOR = "Supervisor"
    TECHNICIAN = "Técnico"
    REQUESTER = "Solicitante"


# Tuples of plain values, handy for validation and SQL CHECK constraints.
TICKET_STATES: tuple[str, ...] = tuple(state.value for state in TicketState)
TICKET_PRIORITIES: tuple[str, ...] = tuple(priority.value for priority in TicketPriority)
TICKET_CATEGORIES: tuple[str, ...] = tuple(category.value for category in TicketCategory)
USER_ROLES: tuple[str, ...] = tuple(role.value for role in UserRole)

# Roles whose active users take part in the automatic round-robin assignment
# of new tickets. The remaining roles never receive a ticket automatically,
# but they can still be assigned manually through ``PATCH .../assign``.
AUTO_ASSIGN_ROLES: tuple[str, ...] = (UserRole.SUPPORT.value, UserRole.TECHNICIAN.value)
