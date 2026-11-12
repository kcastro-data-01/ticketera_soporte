"""Comentarios como conversación: cada comentario dice quién lo escribió
(``author_id``), si es de IT (``author_es_it``), de dónde vino (``origen``:
app, correo o estado) y, para el motivo de un cambio de estado, a qué
estado pasó (``estado_nuevo``). Incluye la migración que completa los
comentarios que ya existían."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, inspect, text

from backend.constants import TicketCategory, TicketPriority, UserRole
from backend.models import Comment, Ticket, User
from backend.schemas import CommentCreate
from backend.services import ticket_service
from backend.tests.test_access_control import headers, register_requester

TICKET = {
    "title": "Impresora sin tóner",
    "description": "La impresora del segundo piso no imprime.",
    "category": TicketCategory.HARDWARE.value,
    "priority": TicketPriority.MEDIUM.value,
}


def _ticket(client, token):
    respuesta = client.post("/api/tickets", json=TICKET, headers=headers(token))
    assert respuesta.status_code == 201
    return respuesta.json()["id"]


def test_comentario_de_it_y_del_solicitante(client, auth_client, session):
    token_sol = register_requester(client)
    ticket_id = _ticket(client, token_sol)
    admin = session.query(User).filter_by(role=UserRole.ADMIN.value).one()

    propio = client.post(f"/api/tickets/{ticket_id}/comments", json={"content": "¿Alguna novedad?"},
                         headers=headers(token_sol)).json()
    it = auth_client.post(f"/api/tickets/{ticket_id}/comments", json={"content": "Ya voy en camino."}).json()

    solicitante = session.query(User).filter_by(role=UserRole.REQUESTER.value).one()
    assert (propio["author_id"], propio["author_es_it"], propio["origen"], propio["estado_nuevo"]) == (
        solicitante.id, False, "app", None)
    assert (it["author_id"], it["author_es_it"], it["origen"]) == (admin.id, True, "app")

    lista = auth_client.get(f"/api/tickets/{ticket_id}/comments").json()
    assert [(c["author"], c["author_es_it"]) for c in lista] == [
        ("Solicitante Test", False), ("Test Admin", True)]


def test_el_motivo_del_cambio_de_estado_queda_como_comentario_del_sistema(auth_client):
    ticket_id = auth_client.post("/api/tickets", json=TICKET).json()["id"]
    respuesta = auth_client.patch(f"/api/tickets/{ticket_id}/state",
                                  json={"state": "En proceso", "motivo": "Reviso el equipo hoy."})
    assert respuesta.status_code == 200

    [comentario] = auth_client.get(f"/api/tickets/{ticket_id}/comments").json()
    assert comentario["content"] == "Reviso el equipo hoy."
    assert comentario["origen"] == "estado"
    assert comentario["estado_nuevo"] == "En proceso"
    assert comentario["author_es_it"] is True


def test_la_respuesta_por_correo_queda_marcada(session):
    usuario = User(name="Ana Solicitante", email="ana@data.cr", role=UserRole.REQUESTER.value)
    ticket = Ticket(**TICKET)
    session.add_all([usuario, ticket])
    session.commit()

    comentario = ticket_service.create_comment(
        session, ticket.id, CommentCreate(content="Ya funciona, gracias."), usuario, origen="correo")

    assert (comentario.origen, comentario.author_id, comentario.author_es_it) == ("correo", usuario.id, False)


def test_sin_usuario_no_es_de_it(session):
    ticket = Ticket(**TICKET)
    session.add(ticket)
    session.commit()
    session.add(Comment(ticket_id=ticket.id, author="Anónimo", content="Viejo"))
    session.commit()
    viejo = session.query(Comment).one()
    assert (viejo.author_id, viejo.origen, viejo.author_es_it) == (None, "app", False)


# --- Migración --------------------------------------------------------------

ESQUEMA_VIEJO = [
    "CREATE TABLE users (id INTEGER PRIMARY KEY, name VARCHAR(120), role VARCHAR(30))",
    "CREATE TABLE comments (id INTEGER PRIMARY KEY, ticket_id INTEGER, author VARCHAR(120),"
    " content TEXT, created_at DATETIME)",
    "CREATE TABLE history (id INTEGER PRIMARY KEY, ticket_id INTEGER, action VARCHAR(40),"
    " field VARCHAR(40), old_value TEXT, new_value TEXT, author VARCHAR(120), author_id INTEGER,"
    " created_at DATETIME)",
    "CREATE TABLE processed_emails (id INTEGER PRIMARY KEY, ticket_id INTEGER, result VARCHAR(20),"
    " created_at DATETIME)",
]


def _fecha(base, segundos=0):
    return (base + timedelta(seconds=segundos)).strftime("%Y-%m-%d %H:%M:%S.%f")


def test_migracion_agrega_las_columnas_y_completa_los_comentarios_viejos(tmp_path):
    from backend.migrate_add_comment_origen import migrate_add_comment_origen

    motor = create_engine(f"sqlite:///{tmp_path / 'vieja.db'}")
    base = datetime(2026, 11, 10, 15, 0, tzinfo=timezone.utc).replace(tzinfo=None)
    with motor.begin() as conn:
        for sentencia in ESQUEMA_VIEJO:
            conn.execute(text(sentencia))
        conn.execute(text("INSERT INTO users VALUES (1, 'Karla', 'Administrador'), (2, 'Ana', 'Solicitante')"))
        filas = [
            (1, "Karla", "Ya voy.", 0),         # comentario normal de IT
            (2, "Karla", "Se cambió el tóner.", 600),  # motivo de un cambio de estado
            (3, "Ana", "Ya funciona.", 1200),   # respuesta por correo
            (4, "Anónimo", "Muy viejo.", 1800),  # sin historial: queda como estaba
        ]
        for id_, autor, texto, seg in filas:
            conn.execute(text("INSERT INTO comments VALUES (:i, 7, :a, :t, :f)"),
                         {"i": id_, "a": autor, "t": texto, "f": _fecha(base, seg)})
        for id_, autor_id, texto, seg in [(1, 1, "Ya voy.", 0), (2, 1, "Se cambió el tóner.", 600),
                                          (3, 2, "Ya funciona.", 1200)]:
            conn.execute(text("INSERT INTO history VALUES (:i, 7, 'commented', 'comment', NULL, :t, 'x', :u, :f)"),
                         {"i": id_, "t": texto, "u": autor_id, "f": _fecha(base, seg)})
        conn.execute(text("INSERT INTO history VALUES (10, 7, 'Cambio de estado', 'state', 'En proceso',"
                          " 'Resuelto', 'Karla', 1, :f)"), {"f": _fecha(base, 600.2)})
        conn.execute(text("INSERT INTO processed_emails VALUES (1, 7, 'comentario', :f)"),
                     {"f": _fecha(base, 1201)})

    assert migrate_add_comment_origen(motor) is True
    assert migrate_add_comment_origen(motor) is False, "se puede correr varias veces"
    columnas = {c["name"] for c in inspect(motor).get_columns("comments")}
    assert {"author_id", "origen", "estado_nuevo"} <= columnas
    with motor.connect() as conn:
        filas = conn.execute(text("SELECT id, author_id, origen, estado_nuevo FROM comments ORDER BY id")).all()
    assert [tuple(f) for f in filas] == [
        (1, 1, "app", None),
        (2, 1, "estado", "Resuelto"),
        (3, 2, "correo", None),
        (4, None, "app", None),
    ]
