"""Pruebas del comando backend.limpiar_datos, con una base temporal."""

import sqlite3

import pytest
from sqlalchemy import func, select

from backend.limpiar_datos import main
from backend.models import Comment, History, ProcessedEmail, Ticket, TicketExplanation, User


@pytest.fixture(autouse=True)
def admin_inicial(monkeypatch):
    monkeypatch.setenv("ADMIN_INICIAL", "kcastro@data.cr")


def contar(session, modelo):
    return session.scalar(select(func.count()).select_from(modelo))


@pytest.fixture
def datos(session):
    admin = User(name="Kristin", email="KCastro@data.cr", role="Administrador")
    tecnico = User(name="Ana", email="ana@data.cr", role="Técnico")
    solicitante = User(name="Luis", email="luis@data.cr", role="Solicitante")
    session.add_all([admin, tecnico, solicitante])
    session.commit()
    for numero in range(2):
        ticket = Ticket(
            title=f"Prueba {numero}", description="x", category="Red", priority="Alta",
            assigned_to_id=tecnico.id, created_by_id=solicitante.id,
        )
        session.add(ticket)
        session.commit()
        session.add_all([
            Comment(ticket_id=ticket.id, author="Ana", content="Hola"),
            History(ticket_id=ticket.id, action="created", author_id=tecnico.id),
            TicketExplanation(ticket_id=ticket.id, content="{}", fingerprint="f", model="m"),
            ProcessedEmail(message_id=f"<{numero}@data.cr>", sender="luis@data.cr",
                           result="ticket", ticket_id=ticket.id),
        ])
    session.commit()
    return admin


def correr(engine, tmp_path, respuesta="BORRAR"):
    preguntas = []
    codigo = main(
        entrada=lambda texto: preguntas.append(texto) or respuesta,
        db_engine=engine, carpeta_respaldo=tmp_path,
    )
    return codigo, preguntas


def respaldos(tmp_path):
    return sorted(tmp_path.glob("respaldo-antes-de-limpiar-*.db"))


@pytest.mark.parametrize("respuesta", ["", "borrar", "si", "BORRA"])
def test_without_confirmation_nothing_is_deleted(engine, session, tmp_path, datos, respuesta, capsys):
    codigo, preguntas = correr(engine, tmp_path, respuesta)
    assert codigo == 1 and preguntas == ["Escribe BORRAR para confirmar: "]
    assert "No se borró nada" in capsys.readouterr().out
    session.expire_all()
    assert (contar(session, Ticket), contar(session, Comment), contar(session, User)) == (2, 2, 3)


def test_with_borrar_only_the_admin_remains(engine, session, tmp_path, datos, capsys):
    codigo, _ = correr(engine, tmp_path)
    assert codigo == 0
    session.expire_all()
    assert session.scalars(select(User.email)).all() == ["KCastro@data.cr"]
    for modelo in (Ticket, Comment, History, TicketExplanation):
        assert contar(session, modelo) == 0
    salida = capsys.readouterr().out
    assert "Se borraron 2 tickets, 2 comentarios y 2 usuarios" in salida


def test_processed_emails_are_kept_without_ticket(engine, session, tmp_path, datos):
    correr(engine, tmp_path)
    session.expire_all()
    correos = session.scalars(select(ProcessedEmail).order_by(ProcessedEmail.id)).all()
    assert [(c.message_id, c.result, c.ticket_id) for c in correos] == [
        ("<0@data.cr>", "ticket", None), ("<1@data.cr>", "ticket", None),
    ]


def test_backup_is_created_before_deleting(engine, session, tmp_path, datos, capsys):
    correr(engine, tmp_path)
    [respaldo] = respaldos(tmp_path)
    assert f"Respaldo de la base: {respaldo}" in capsys.readouterr().out
    # El respaldo tiene los datos de antes de limpiar.
    with sqlite3.connect(respaldo) as copia:
        assert copia.execute("SELECT count(*) FROM tickets").fetchone() == (2,)
        assert copia.execute("SELECT count(*) FROM users").fetchone() == (3,)


@pytest.mark.parametrize("valor", ["", "otra@data.cr"])
def test_without_admin_inicial_nothing_is_deleted(engine, session, tmp_path, datos, monkeypatch, valor, capsys):
    monkeypatch.setenv("ADMIN_INICIAL", valor)
    codigo, preguntas = correr(engine, tmp_path)
    assert codigo == 1 and preguntas == []
    assert "No se borró nada" in capsys.readouterr().out
    assert respaldos(tmp_path) == []
    session.expire_all()
    assert (contar(session, Ticket), contar(session, User)) == (2, 3)


def test_microsoft_session_cache_is_not_touched(engine, tmp_path, datos):
    cache = tmp_path / "msal_cache.json"
    cache.write_text('{"sesion": 1}')
    correr(engine, tmp_path)
    assert cache.read_text() == '{"sesion": 1}'
