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

    HARDWARE = "Hardware"
    SOFTWARE = "Software"
    NETWORK = "Red"
    ACCESS = "Accesos"


class UserRole(str, Enum):
    """Roles of the minimal users used to assign tickets (RF4)."""

    ADMIN = "Administrador"
    TECHNICIAN = "Técnico"
    REQUESTER = "Solicitante"


class TicketDateField(str, Enum):
    """Which date the listing's «Desde / Hasta» filter looks at: the creation
    or the first time the ticket reached a state (from its history)."""

    CREATED = "creacion"
    IN_PROGRESS = "en_proceso"
    RESOLVED = "resuelto"
    CLOSED = "cerrado"


# Estado del historial que marca cada «Fecha de» (la creación no tiene).
DATE_FIELD_STATE: dict[TicketDateField, str] = {
    TicketDateField.IN_PROGRESS: TicketState.IN_PROGRESS.value,
    TicketDateField.RESOLVED: TicketState.RESOLVED.value,
    TicketDateField.CLOSED: TicketState.CLOSED.value,
}


# Tuples of plain values, handy for validation and SQL CHECK constraints.
TICKET_STATES: tuple[str, ...] = tuple(state.value for state in TicketState)
TICKET_PRIORITIES: tuple[str, ...] = tuple(priority.value for priority in TicketPriority)
TICKET_CATEGORIES: tuple[str, ...] = tuple(category.value for category in TicketCategory)
USER_ROLES: tuple[str, ...] = tuple(role.value for role in UserRole)

# One-to-one correspondence used by ``backend.migrate_categories`` to bring
# tickets created before the category change over to the current list. It is
# only read by the migration: the API never accepts the legacy values.
LEGACY_CATEGORY_MAP: dict[str, str] = {
    "Incidente": "Hardware",
    "Consulta": "Software",
    "Solicitud": "Accesos",
    "Mantenimiento": "Red",
}

# Role removed from the system: its users become ``Técnico``. Only read by
# ``backend.migrate_remove_support_role``; the API never accepts it.
LEGACY_SUPPORT_ROLE = "Soporte"

# Role removed later: its users become ``Técnico`` too. Only read by
# ``backend.migrate_remove_supervisor_role``; the API answers 422 to it.
LEGACY_SUPERVISOR_ROLE = "Supervisor"

# Roles whose active users take part in the automatic round-robin assignment
# of new tickets. The remaining roles never receive a ticket automatically,
# but they can still be assigned manually through ``PATCH .../assign``.
AUTO_ASSIGN_ROLES: tuple[str, ...] = (UserRole.TECHNICIAN.value,)

# IT solo recibe: un ticket se asigna únicamente a estos roles (nunca a un
# Solicitante). Son también los que pueden tener área de IT.
IT_ROLES: tuple[str, ...] = (UserRole.ADMIN.value, UserRole.TECHNICIAN.value)

# Áreas de IT fijas (no se crean, renombran ni desactivan desde la app). La
# migración ``backend.migrate_add_it_areas`` deja exactamente estas, en este
# orden, que es también el orden en que se muestran.
IT_AREA_SUPPORT = "Soporte"
IT_AREA_NETWORK = "Redes e Infraestructura"
IT_AREA_SECURITY = "Ciberseguridad"
IT_AREA_PROGRAMMING = "Programación"
IT_AREAS: tuple[str, ...] = (IT_AREA_SUPPORT, IT_AREA_NETWORK, IT_AREA_SECURITY, IT_AREA_PROGRAMMING)

# Qué atiende cada área (ayuda del formulario «Nuevo ticket» y del chat).
IT_AREA_SCOPE: dict[str, str] = {
    IT_AREA_SUPPORT: "computadoras, impresoras, programas",
    IT_AREA_NETWORK: "internet, wifi, servidores, VPN",
    IT_AREA_SECURITY: "accesos, contraseñas, cuentas, incidentes de seguridad",
    IT_AREA_PROGRAMMING: "sistemas internos, Odoo, desarrollos y reportes",
}

# Área de un ticket que no la trae (p. ej. un correo al buzón general),
# según su categoría. Programación solo se elige a mano.
CATEGORY_IT_AREA: dict[str, str] = {
    TicketCategory.HARDWARE.value: IT_AREA_SUPPORT,
    TicketCategory.SOFTWARE.value: IT_AREA_SUPPORT,
    TicketCategory.NETWORK.value: IT_AREA_NETWORK,
    TicketCategory.ACCESS.value: IT_AREA_SECURITY,
}

# Nombres de antes que la migración convierte en un área fija (los tickets y
# técnicos pasan a esa área). Cualquier otra área se borra: lo suyo queda
# «Sin área».
LEGACY_IT_AREA_NAMES: dict[str, str] = {
    "Soporte técnico": IT_AREA_SUPPORT,
    "Redes": IT_AREA_NETWORK,
    "Infraestructura": IT_AREA_NETWORK,
}

# Texto que se muestra para un ticket o usuario sin área.
NO_AREA_LABEL = "Sin área"
