"""Pruebas del script backend.reset_tickets."""

from backend.models import Comment, History, Ticket, User
from backend.reset_tickets import count_rows, reset_tickets


def seed(session):
    user = User(name="Ana", email="ana.reset@tec.local", role="Técnico")
    session.add(user)
    session.commit()
    ticket = Ticket(
        title="Ticket a borrar", description="x", category="Red",
        priority="Alta", assigned_to_id=user.id,
    )
    session.add(ticket)
    session.commit()
    session.add_all([
        Comment(ticket_id=ticket.id, author="Ana", content="Hola"),
        History(ticket_id=ticket.id, action="created"),
    ])
    session.commit()
    return user


def test_dry_run_only_counts(session):
    seed(session)
    assert reset_tickets(session) == {"tickets": 1, "comentarios": 1, "historial": 1}
    assert count_rows(session) == {"tickets": 1, "comentarios": 1, "historial": 1}


def test_apply_deletes_tickets_comments_and_history_but_keeps_users(session):
    user = seed(session)

    reset_tickets(session, apply=True)

    assert count_rows(session) == {"tickets": 0, "comentarios": 0, "historial": 0}
    assert session.get(User, user.id) is not None

    # La numeración vuelve a empezar.
    ticket = Ticket(title="Nuevo inicio", description="x", category="Red", priority="Baja")
    session.add(ticket)
    session.commit()
    assert ticket.id == 1
