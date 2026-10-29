"""Numeración de tickets: el próximo es el mayor id + 1 (aunque antes se hayan
creado y borrado otros; los huecos del medio no se rellenan), borrar no deja
nada colgado, un hilo de un ticket borrado no comenta en el nuevo con el mismo
número, y la renumeración de una sola vez (#16 → #6).

La suite corre en SQLite; con ``TEST_POSTGRES_URL`` las pruebas marcadas
también corren en un Postgres de prueba (nunca en Neon)."""

import os
import threading

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import sessionmaker

from backend.database import Base
from backend.migrate_renumber_tickets import migrate_renumber_tickets, nuevos_numeros
from backend.models import (Comment, History, ProcessedEmail, SchemaMigration, Ticket,
                            TicketExplanation, User)
from backend.schemas import TicketCreate
from backend.services import correo_service as cs
from backend.services import ticket_service
from backend.tests.test_correo import CONFIG, crear_correo, procesar


@pytest.fixture
def admin(session):
    user = User(name="Kristin Castro", email="kcastro@data.cr", role="Administrador", password_hash="x")
    session.add(user)
    session.commit()
    return user


def crear(session, user, titulo="Impresora no imprime") -> Ticket:
    return ticket_service.create_ticket(
        session, TicketCreate(title=titulo, description="Descripción", category="Hardware",
                              priority="Alta"), user, asignado=user)


def con_salto(session, user, hasta=16, quedan=5) -> None:
    """Lo que pasó en producción: #1–#16 y luego se borraron #(quedan+1)…#(hasta-1)."""
    for _ in range(hasta):
        crear(session, user)
    for numero in range(quedan + 1, hasta):
        ticket_service.delete_ticket(session, numero, user)


def ids(session) -> list[int]:
    return list(session.scalars(select(Ticket.id).order_by(Ticket.id)))


# --- Mayor id + 1 ---------------------------------------------------------------


def test_after_deleting_the_last_ones_the_next_continues_from_the_last(session, admin):
    for _ in range(5):
        crear(session, admin)
    for _ in range(10):
        ticket_service.delete_ticket(session, crear(session, admin).id, admin)
    assert ids(session) == [1, 2, 3, 4, 5]
    assert crear(session, admin).id == 6


def test_middle_holes_are_not_filled(session, admin):
    for _ in range(6):
        crear(session, admin)
    ticket_service.delete_ticket(session, 3, admin)
    assert crear(session, admin).id == 7
    assert ids(session) == [1, 2, 4, 5, 6, 7]


def test_postgres_adjusts_the_sequence_under_a_lock():
    """Sin Postgres a mano: las sentencias que manda en esa base."""
    class Sesion:
        def __init__(self):
            self.sql = []

        def get_bind(self):
            return type("Bind", (), {"dialect": type("D", (), {"name": "postgresql"})()})()

        def execute(self, sentencia, parametros=None):
            self.sql.append(str(sentencia))

    sesion = Sesion()
    ticket_service.reservar_numero(sesion)
    assert sesion.sql[0] == "SELECT pg_advisory_xact_lock(:clave)"
    assert "setval(pg_get_serial_sequence('tickets', 'id'), COALESCE(MAX(id), 0) + 1, false)" in sesion.sql[1]


# --- Borrar no deja nada colgado --------------------------------------------------


def test_new_ticket_with_a_reused_number_inherits_nothing(session, admin):
    for _ in range(5):
        crear(session, admin)
    viejo = crear(session, admin, "Ticket viejo")
    session.add_all([Comment(ticket_id=viejo.id, author="Ana", content="Comentario viejo"),
                     TicketExplanation(ticket_id=viejo.id, content="{}", fingerprint="x", model="m"),
                     ProcessedEmail(message_id="<viejo@x>", result="ticket", ticket_id=viejo.id)])
    session.commit()
    ticket_service.delete_ticket(session, viejo.id, admin)

    nuevo = crear(session, admin, "Ticket nuevo")
    assert nuevo.id == viejo.id == 6
    session.expire_all()
    assert session.scalars(select(Comment).where(Comment.ticket_id == 6)).all() == []
    assert session.scalar(select(TicketExplanation).where(TicketExplanation.ticket_id == 6)) is None
    assert [h.action for h in session.scalars(select(History).where(History.ticket_id == 6))] == ["created"]
    assert session.scalar(select(ProcessedEmail.ticket_id).where(ProcessedEmail.message_id == "<viejo@x>")) is None


# --- Correo ------------------------------------------------------------------------


@pytest.fixture
def ana(session):
    user = User(name="Ana Pérez", email="ana@data.cr", role="Solicitante", password_hash="x")
    session.add(user)
    session.commit()
    return user


def test_ticket_number_from_someone_outside_the_ticket_does_not_comment(session, admin, ana):
    for _ in range(6):
        crear(session, admin)
    mensaje = crear_correo(asunto="RE: [Ticket #6] Nuevo comentario", cuerpo="Yo también tengo eso")
    assert procesar(session, mensaje) != ("comentario", None)
    assert session.scalars(select(Comment)).all() == []


def test_reply_in_the_thread_of_a_deleted_ticket_never_goes_to_the_new_one(session, admin, ana):
    for _ in range(5):
        crear(session, admin)
    resultado, respuesta = procesar(session, crear_correo(msg_id="<pedido@data.cr>"))
    assert resultado == "ticket"
    borrado = session.scalar(select(ProcessedEmail.ticket_id).where(
        ProcessedEmail.message_id == "<pedido@data.cr>"))
    assert borrado == 6
    ticket_service.delete_ticket(session, 6, admin)
    # Ana es la solicitante del ticket nuevo #6, pero el hilo era del borrado.
    nuevo = ticket_service.create_ticket(
        session, TicketCreate(title="Otro problema", description="x", category="Red", priority="Alta"),
        ana, asignado=admin)
    assert nuevo.id == 6

    respuesta = crear_correo(asunto="RE: Ticket #6 creado: La impresora no imprime",
                             cuerpo="Sigue sin imprimir", msg_id="<resp@data.cr>")
    respuesta["internetMessageHeaders"] = [{"name": "In-Reply-To", "value": "<pedido@data.cr>"}]
    assert procesar(session, respuesta)[0] != "comentario"
    assert session.scalars(select(Comment)).all() == []


# --- Renumeración de una sola vez ---------------------------------------------------


@pytest.mark.parametrize("antes,cambios", [
    ([1, 2, 3, 4, 5, 16], [(16, 6)]),
    ([1, 2, 3, 4, 5, 16, 20], [(16, 6), (20, 7)]),
    ([1, 2, 3], []),
    ([], []),
    ([4, 5, 9], [(9, 6)]),
])
def test_new_numbers(antes, cambios):
    assert nuevos_numeros(antes) == cambios


def test_renumbers_16_to_6_with_everything_it_references(engine, session, admin):
    con_salto(session, admin)
    session.get(Ticket, 16).title = "Ticket dieciséis"
    assert ids(session) == [1, 2, 3, 4, 5, 16]
    session.add_all([Comment(ticket_id=16, author="Ana", content="Primer comentario"),
                     Comment(ticket_id=16, author="Ana", content="Segundo comentario"),
                     History(ticket_id=16, action="updated"),
                     TicketExplanation(ticket_id=16, content="{}", fingerprint="x", model="m"),
                     ProcessedEmail(message_id="<m16@x>", result="ticket", ticket_id=16)])
    session.commit()

    assert migrate_renumber_tickets(engine) == [(16, 6)]

    session.expire_all()
    assert ids(session) == [1, 2, 3, 4, 5, 6]
    assert session.get(Ticket, 6).title == "Ticket dieciséis"
    assert sorted(c.content for c in session.scalars(select(Comment).where(Comment.ticket_id == 6))) == [
        "Primer comentario", "Segundo comentario"]
    assert session.scalar(select(func.count()).select_from(History).where(History.ticket_id == 6)) == 2
    assert session.scalar(select(TicketExplanation.ticket_id)) == 6
    assert session.scalar(select(ProcessedEmail.ticket_id).where(ProcessedEmail.message_id == "<m16@x>")) == 6
    for tabla in (Comment, History, TicketExplanation, ProcessedEmail):
        assert session.scalar(select(func.count()).select_from(tabla).where(tabla.ticket_id == 16)) == 0
    assert crear(session, admin).id == 7


def test_renumbering_runs_only_once(engine, session, admin, caplog):
    for _ in range(3):
        crear(session, admin)
    assert migrate_renumber_tickets(engine) == []
    assert "ya estaba seguida" in caplog.text
    assert session.get(SchemaMigration, "renumerar_tickets") is not None
    # Después, ningún borrado renumera los demás.
    for _ in range(6):
        crear(session, admin)
    for numero in (1, 4, 5, 6, 7, 8):
        ticket_service.delete_ticket(session, numero, admin)
    assert migrate_renumber_tickets(engine) == []
    assert ids(session) == [2, 3, 9]


def test_log_says_which_ticket_moved(engine, session, admin, caplog):
    con_salto(session, admin, hasta=16, quedan=2)
    assert migrate_renumber_tickets(engine) == [(16, 3)]
    assert "el ticket #16 ahora es el #3" in caplog.text


# --- Postgres de prueba (opcional) ---------------------------------------------------

POSTGRES = os.environ.get("TEST_POSTGRES_URL")
solo_postgres = pytest.mark.skipif(not POSTGRES, reason="sin TEST_POSTGRES_URL")


@pytest.fixture
def pg():
    motor = create_engine(POSTGRES)
    Base.metadata.drop_all(motor)
    Base.metadata.create_all(motor)
    yield motor
    Base.metadata.drop_all(motor)
    motor.dispose()


@solo_postgres
def test_postgres_next_number_and_renumbering(pg):
    Sesion = sessionmaker(bind=pg, expire_on_commit=False)
    with Sesion() as session:
        admin = User(name="Kristin Castro", email="kcastro@data.cr", role="Administrador")
        session.add(admin)
        session.commit()
        for _ in range(5):
            crear(session, admin)
        for _ in range(10):
            ticket_service.delete_ticket(session, crear(session, admin).id, admin)
        assert crear(session, admin).id == 6
        ticket_service.delete_ticket(session, 3, admin)
        assert crear(session, admin).id == 7
        # Lo que pasó en producción (antes de este arreglo): un ticket #16.
        session.execute(text("INSERT INTO tickets (id, title, description, category, priority, state, "
                             "created_at, updated_at) VALUES (16, 'Dieciséis', 'x', 'Red', 'Alta', "
                             "'Nuevo', now(), now())"))
        session.add(Comment(ticket_id=16, author="Ana", content="Del dieciséis"))
        session.commit()
    # Bloque 1-2; después 4, 5, 6, 7 y 16 → 3, 4, 5, 6 y 7.
    assert migrate_renumber_tickets(pg) == [(4, 3), (5, 4), (6, 5), (7, 6), (16, 7)]
    with Sesion() as session:
        assert session.scalar(select(Comment.ticket_id).where(Comment.content == "Del dieciséis")) == 7
        assert crear(session, session.get(User, admin.id)).id == 8


@solo_postgres
def test_postgres_concurrent_creations_never_share_a_number(pg):
    Sesion = sessionmaker(bind=pg, expire_on_commit=False)
    with Sesion() as session:
        admin = User(name="Kristin Castro", email="kcastro@data.cr", role="Administrador")
        session.add(admin)
        session.commit()
        for _ in range(3):
            ticket_service.delete_ticket(session, crear(session, admin).id, admin)
    creados, errores = [], []

    def una():
        try:
            with Sesion() as s:
                creados.append(crear(s, s.get(User, admin.id)).id)
        except Exception as error:  # noqa: BLE001
            errores.append(error)

    hilos = [threading.Thread(target=una) for _ in range(8)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    assert errores == []
    assert sorted(creados) == list(range(1, 9))
