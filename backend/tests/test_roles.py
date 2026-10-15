"""Tests for the user roles (Task 22).

The system accepts ``Administrador``, ``Supervisor``, ``Técnico`` and
``Solicitante`` (``Soporte`` was removed). Only the active users with the
``Técnico`` role take part in the automatic round-robin assignment of new tickets; every
role can still be assigned manually, and no row is ever deleted.
"""

import pytest

from backend.constants import (
    AUTO_ASSIGN_ROLES,
    TicketCategory,
    TicketPriority,
    USER_ROLES,
    UserRole,
)

VALID_TICKET = {
    "title": "Ticket de prueba",
    "description": "Descripción del ticket usado en las pruebas de roles.",
    "category": TicketCategory.SOFTWARE.value,
    "priority": TicketPriority.MEDIUM.value,
}

NON_AUTO_ASSIGN_ROLES = [
    role for role in USER_ROLES if role not in AUTO_ASSIGN_ROLES
]


def create_user(auth_client, name, email, role=UserRole.TECHNICIAN.value, **overrides) -> dict:
    payload = {"name": name, "email": email, "role": role, **overrides}
    response = auth_client.post("/api/users", json=payload)
    assert response.status_code == 201
    return response.json()


def create_ticket(auth_client, **overrides) -> dict:
    payload = {**VALID_TICKET, **overrides}
    response = auth_client.post("/api/tickets", json=payload)
    assert response.status_code == 201
    return response.json()


def assign(auth_client, ticket_id, user_id) -> dict:
    response = auth_client.patch(
        f"/api/tickets/{ticket_id}/assign",
        json={"assigned_to_id": user_id},
    )
    assert response.status_code == 200
    return response.json()


# ---------------------------------------------------------------------------
# Every role is accepted
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("role", USER_ROLES, ids=USER_ROLES)
def test_every_role_can_be_created(auth_client, role):
    response = auth_client.post(
        "/api/users",
        json={"name": f"Persona {role}", "email": f"{role}@soporte.local", "role": role},
    )

    assert response.status_code == 201
    assert response.json()["role"] == role


@pytest.mark.parametrize("role", USER_ROLES, ids=USER_ROLES)
def test_every_role_round_trips_in_the_listing(auth_client, role):
    auth_client.post(
        "/api/users",
        json={"name": f"Persona {role}", "email": f"{role}@soporte.local", "role": role},
    )

    data = auth_client.get("/api/users").json()

    real_data = [u for u in data if u["email"] != "testadmin@test.com"]
    assert [user["role"] for user in real_data] == [role]


def test_unknown_role_is_still_rejected(auth_client):
    response = auth_client.post(
        "/api/users",
        json={"name": "Nadie", "email": "nadie@soporte.local", "role": "SuperUsuario"},
    )

    assert response.status_code == 422


def test_roles_fit_the_model_role_column():
    """Every role must fit in ``users.role`` (``String(30)`` in models.py)."""
    from backend.models import User

    column_length = User.__table__.c.role.type.length
    assert max(len(role) for role in USER_ROLES) <= column_length


# ---------------------------------------------------------------------------
# Automatic assignment: Técnico only
# ---------------------------------------------------------------------------


def test_technician_receives_the_ticket(auth_client):
    technician = create_user(
        auth_client, "Tina", "tina@soporte.local", role=UserRole.TECHNICIAN.value
    )

    ticket = create_ticket(auth_client)

    assert ticket["assigned_to_id"] == technician["id"]


def test_technicians_share_the_round_robin(auth_client):
    support = create_user(auth_client, "Ana", "ana@soporte.local")
    technician = create_user(
        auth_client, "Tomás", "tomas@soporte.local", role=UserRole.TECHNICIAN.value
    )

    ticket_a = create_ticket(auth_client, title="Primer ticket")
    ticket_b = create_ticket(auth_client, title="Segundo ticket")

    # Both are eligible, so they alternate in id order.
    assert ticket_a["assigned_to_id"] == support["id"]
    assert ticket_b["assigned_to_id"] == technician["id"]


def test_tie_between_technicians_breaks_by_lowest_id(auth_client):
    technician = create_user(
        auth_client, "Tomás", "tomas@soporte.local", role=UserRole.TECHNICIAN.value
    )
    support = create_user(auth_client, "Ana", "ana@soporte.local")

    ticket = create_ticket(auth_client)

    # Both have 0 tickets; the lowest id (the technician) wins.
    assert ticket["assigned_to_id"] == technician["id"]


def test_round_robin_counts_tickets_of_each_technician(auth_client, session):
    from backend.models import Ticket as TicketModel

    support = create_user(auth_client, "Ana", "ana@soporte.local")
    technician = create_user(
        auth_client, "Tomás", "tomas@soporte.local", role=UserRole.TECHNICIAN.value
    )

    # One ticket already assigned to the technician (bypassing the API).
    session.add(
        TicketModel(
            title="Ticket existente",
            description="Ya asignado al técnico.",
            category="Software",
            priority="Media",
            assigned_to_id=technician["id"],
        )
    )
    session.commit()

    # Ana has 0, Tomás has 1 → the new ticket goes to Ana.
    ticket = create_ticket(auth_client)
    assert ticket["assigned_to_id"] == support["id"]

    # Now both have 1 → tie, lowest id (Ana) wins again.
    ticket = create_ticket(auth_client, title="Segundo ticket")
    assert ticket["assigned_to_id"] == support["id"]

    # Ana has 2, Tomás has 1 → Tomás wins.
    ticket = create_ticket(auth_client, title="Tercer ticket")
    assert ticket["assigned_to_id"] == technician["id"]


@pytest.mark.parametrize("role", NON_AUTO_ASSIGN_ROLES, ids=NON_AUTO_ASSIGN_ROLES)
def test_other_roles_never_receive_a_ticket_automatically(auth_client, role):
    create_user(auth_client, "Otra Persona", f"otra-{role}@soporte.local", role=role)

    ticket = create_ticket(auth_client)

    assert ticket["assigned_to_id"] is None


def test_inactive_technician_is_skipped(auth_client, session):
    from backend.models import User as UserModel

    active = create_user(auth_client, "Ana", "ana@soporte.local")
    inactive = create_user(
        auth_client,
        "Tomás",
        "tomas@soporte.local",
        role=UserRole.TECHNICIAN.value,
    )

    db_user = session.get(UserModel, inactive["id"])
    db_user.is_active = False
    session.commit()

    ticket = create_ticket(auth_client)

    assert ticket["assigned_to_id"] == active["id"]


# ---------------------------------------------------------------------------
# Existing and manual assignments are preserved
# ---------------------------------------------------------------------------


def test_existing_assignments_survive_new_tickets(auth_client):
    requester = create_user(
        auth_client, "Sara", "sara@soporte.local", role=UserRole.REQUESTER.value
    )
    support = create_user(auth_client, "Ana", "ana@soporte.local")

    ticket_a = create_ticket(auth_client, title="Ticket existente")
    assert ticket_a["assigned_to_id"] == support["id"]

    # Manual assignment to a role outside AUTO_ASSIGN_ROLES.
    ticket_a = assign(auth_client, ticket_a["id"], requester["id"])
    assert ticket_a["assigned_to_id"] == requester["id"]

    # A new ticket must not disturb it.
    ticket_b = create_ticket(auth_client, title="Ticket nuevo")
    assert ticket_b["assigned_to_id"] == support["id"]

    stored = auth_client.get(f"/api/tickets/{ticket_a['id']}").json()
    assert stored["assigned_to_id"] == requester["id"]


def test_manual_assignment_can_unassign(auth_client):
    support = create_user(auth_client, "Ana", "ana@soporte.local")

    ticket = create_ticket(auth_client)
    assert ticket["assigned_to_id"] == support["id"]

    ticket = assign(auth_client, ticket["id"], None)

    assert ticket["assigned_to_id"] is None
    # Unassigning does not deactivate or delete the user.
    users = auth_client.get("/api/users").json()
    real_users = [u for u in users if u["email"] != "testadmin@test.com"]
    assert len(real_users) == 1


def test_manual_assignment_to_supervisor_is_accepted(auth_client):
    supervisor = create_user(
        auth_client, "Sonia", "sonia@soporte.local", role=UserRole.SUPERVISOR.value
    )
    technician = create_user(
        auth_client, "Tomás", "tomas@soporte.local", role=UserRole.TECHNICIAN.value
    )

    ticket = create_ticket(auth_client)
    assert ticket["assigned_to_id"] == technician["id"]

    ticket = assign(auth_client, ticket["id"], supervisor["id"])

    assert ticket["assigned_to_id"] == supervisor["id"]


def test_removed_support_role_is_rejected(auth_client):
    response = auth_client.post(
        "/api/users",
        json={"name": "Ana", "email": "ana-soporte@soporte.local", "role": "Soporte"},
    )
    assert response.status_code == 422
