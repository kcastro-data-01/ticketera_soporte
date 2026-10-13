"""Tests for automatic round-robin assignment of new tickets (Task 21).

When a ticket is created, it is auto-assigned to the active Support user
with the fewest assigned tickets. Ties are broken by lowest user id. When
there are no active Support users the ticket is created unassigned.
"""

from backend.constants import TicketCategory, TicketPriority, UserRole

VALID_TICKET = {
    "title": "Ticket de prueba",
    "description": "Descripción del ticket usado en las pruebas de asignación automática.",
    "category": TicketCategory.SOFTWARE.value,
    "priority": TicketPriority.MEDIUM.value,
}


def create_user(auth_client, name, email, role=UserRole.SUPPORT.value, **overrides) -> dict:
    payload = {"name": name, "email": email, "role": role, **overrides}
    response = auth_client.post("/api/users", json=payload)
    assert response.status_code == 201
    return response.json()


def create_ticket(auth_client, **overrides) -> dict:
    payload = {**VALID_TICKET, **overrides}
    response = auth_client.post("/api/tickets", json=payload)
    assert response.status_code == 201
    return response.json()


# ---------------------------------------------------------------------------
# Basic round-robin
# ---------------------------------------------------------------------------


def test_new_ticket_is_assigned_to_first_support_user(auth_client):
    user = create_user(auth_client, "Ana", "ana@test.local")
    ticket = create_ticket(auth_client)

    assert ticket["assigned_to_id"] == user["id"]


def test_second_ticket_goes_to_second_support_user(auth_client):
    user_a = create_user(auth_client, "Ana", "ana@test.local")
    user_b = create_user(auth_client, "Luis", "luis@test.local")

    ticket_a = create_ticket(auth_client, title="Primer ticket")
    ticket_b = create_ticket(auth_client, title="Segundo ticket")

    assert ticket_a["assigned_to_id"] == user_a["id"]
    assert ticket_b["assigned_to_id"] == user_b["id"]


def test_third_ticket_wraps_around_to_first_user(auth_client):
    user_a = create_user(auth_client, "Ana", "ana@test.local")
    _user_b = create_user(auth_client, "Luis", "luis@test.local")

    ticket_a = create_ticket(auth_client, title="Primer ticket")
    _ticket_b = create_ticket(auth_client, title="Segundo ticket")
    ticket_c = create_ticket(auth_client, title="Tercer ticket")

    assert ticket_a["assigned_to_id"] == user_a["id"]
    assert ticket_c["assigned_to_id"] == user_a["id"]


# ---------------------------------------------------------------------------
# Tie-breaking by lowest id
# ---------------------------------------------------------------------------


def test_tie_breaks_by_lowest_id(auth_client):
    user_a = create_user(auth_client, "Ana", "ana@test.local")
    create_user(auth_client, "Luis", "luis@test.local")

    # Both users start with 0 tickets; the first ticket goes to the lowest id.
    ticket = create_ticket(auth_client)
    assert ticket["assigned_to_id"] == user_a["id"]


# ---------------------------------------------------------------------------
# No active Support users
# ---------------------------------------------------------------------------


def test_ticket_is_unassigned_when_no_support_users(auth_client):
    ticket = create_ticket(auth_client)

    assert ticket["assigned_to_id"] is None


def test_ticket_is_unassigned_when_only_admin_users(auth_client):
    create_user(auth_client, "Admin", "admin@test.local", role=UserRole.ADMIN.value)
    ticket = create_ticket(auth_client)

    assert ticket["assigned_to_id"] is None


# ---------------------------------------------------------------------------
# Inactive users are skipped
# ---------------------------------------------------------------------------


def test_inactive_support_user_is_skipped(auth_client, session):
    from backend.models import User as UserModel

    active = create_user(auth_client, "Activo", "activo@test.local")
    inactive = create_user(auth_client, "Inactivo", "inactivo@test.local")

    # Deactivate the second user directly via the ORM.
    db_user = session.get(UserModel, inactive["id"])
    db_user.is_active = False
    session.commit()

    # The round-robin should skip the inactive user.
    ticket_a = create_ticket(auth_client, title="Primer ticket")
    ticket_b = create_ticket(auth_client, title="Segundo ticket")

    # Both tickets go to the active user; the inactive one is never selected.
    assert ticket_a["assigned_to_id"] == active["id"]
    assert ticket_b["assigned_to_id"] == active["id"]


def test_round_robin_only_counts_support_users(auth_client, session):
    from backend.models import Ticket as TicketModel, User as UserModel

    user_a = create_user(auth_client, "Ana", "ana@test.local")
    user_b = create_user(auth_client, "Luis", "luis@test.local")
    admin = create_user(auth_client, "Admin", "admin@test.local", role=UserRole.ADMIN.value)

    # Create a ticket assigned to the admin directly (bypassing the API).
    session.add(
        TicketModel(
            title="Ticket del admin",
            description="Asignado al admin.",
            category="Software",
            priority="Media",
            assigned_to_id=admin["id"],
        )
    )
    session.commit()

    # The round-robin should ignore the admin's ticket count.
    ticket_a = create_ticket(auth_client, title="Primer ticket")
    ticket_b = create_ticket(auth_client, title="Segundo ticket")

    # Both users have 0 Support tickets, so first goes to lowest id.
    assert ticket_a["assigned_to_id"] == user_a["id"]
    # After ticket_a, Ana has 1 and Luis has 0, so ticket_b goes to Luis.
    assert ticket_b["assigned_to_id"] == user_b["id"]


# ---------------------------------------------------------------------------
# Existing assignments are not modified
# ---------------------------------------------------------------------------


def test_existing_assignments_are_not_modified(auth_client):
    user_a = create_user(auth_client, "Ana", "ana@test.local")
    ticket_a = create_ticket(auth_client, title="Ticket existente")

    # Manually reassign the ticket.
    response = auth_client.patch(
        f"/api/tickets/{ticket_a['id']}/assign",
        json={"assigned_to_id": None},
    )
    assert response.status_code == 200
    assert response.json()["assigned_to_id"] is None

    # Create a new ticket; it should go to the user with fewest tickets.
    # Ana now has 0 tickets (the first was unassigned), so she gets it.
    ticket_b = create_ticket(auth_client, title="Ticket nuevo")
    assert ticket_b["assigned_to_id"] == user_a["id"]

    # The first ticket remains unassigned.
    response = auth_client.get(f"/api/tickets/{ticket_a['id']}")
    assert response.json()["assigned_to_id"] is None


# ---------------------------------------------------------------------------
# Manual assignment still works
# ---------------------------------------------------------------------------


def test_manual_assignment_still_works(auth_client):
    user_a = create_user(auth_client, "Ana", "ana@test.local")
    user_b = create_user(auth_client, "Luis", "luis@test.local")

    ticket = create_ticket(auth_client)
    # Auto-assigned to Ana (lowest id, both have 0).
    assert ticket["assigned_to_id"] == user_a["id"]

    # Manually reassign to Luis.
    response = auth_client.patch(
        f"/api/tickets/{ticket['id']}/assign",
        json={"assigned_to_id": user_b["id"]},
    )
    assert response.status_code == 200
    assert response.json()["assigned_to_id"] == user_b["id"]
