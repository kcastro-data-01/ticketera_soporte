"""Migración idempotente: agrega a ``comments`` quién lo escribió
(``author_id``), de dónde vino (``origen``: ``app``, ``correo`` o ``estado``)
y, para el motivo de un cambio de estado, a qué estado pasó
(``estado_nuevo``). Con eso el detalle muestra los comentarios como una
conversación.

Los comentarios que ya existían se completan con lo que dejó guardado la
app, solo la vez que se agregan las columnas:

- ``author_id``: la entrada «commented» del historial con el mismo ticket y
  el mismo texto (la app la escribe junto con cada comentario).
- ``estado``: un «Cambio de estado» del mismo autor en el mismo ticket a
  menos de 5 segundos (el motivo se guarda en la misma transacción).
- ``correo``: un correo procesado como «comentario» en el mismo ticket hasta
  30 segundos después.

Lo que no se puede deducir queda como ``app`` sin autor: se ve como antes.
"""

from datetime import timedelta, timezone

from sqlalchemy import inspect, text

from backend.database import engine

VENTANA_ESTADO = timedelta(seconds=5)
VENTANA_CORREO = timedelta(seconds=30)


def _utc(valor):
    if valor is None:
        return None
    if isinstance(valor, str):
        from datetime import datetime

        valor = datetime.fromisoformat(valor)
    return valor.replace(tzinfo=timezone.utc) if valor.tzinfo is None else valor.astimezone(timezone.utc)


def _completar_existentes(conn) -> None:
    conn.execute(text(
        "UPDATE comments SET author_id = ("
        " SELECT h.author_id FROM history h"
        " WHERE h.ticket_id = comments.ticket_id AND h.action = 'commented'"
        " AND h.new_value = comments.content AND h.author_id IS NOT NULL"
        " ORDER BY h.id LIMIT 1)"
        " WHERE author_id IS NULL"
    ))
    comentarios = conn.execute(text(
        "SELECT id, ticket_id, author_id, created_at FROM comments")).all()
    cambios = conn.execute(text(
        "SELECT ticket_id, author_id, new_value, created_at FROM history"
        " WHERE action = 'Cambio de estado' AND field = 'state'")).all()
    correos = conn.execute(text(
        "SELECT ticket_id, created_at FROM processed_emails WHERE result = 'comentario'")).all() \
        if inspect(conn).has_table("processed_emails") else []
    for c in comentarios:
        creado = _utc(c.created_at)
        estado = next((h.new_value for h in cambios
                       if h.ticket_id == c.ticket_id and c.author_id is not None
                       and h.author_id == c.author_id
                       and abs(_utc(h.created_at) - creado) <= VENTANA_ESTADO), None)
        if estado:
            conn.execute(text("UPDATE comments SET origen = 'estado', estado_nuevo = :e WHERE id = :i"),
                         {"e": estado, "i": c.id})
            continue
        if any(m.ticket_id == c.ticket_id and timedelta(0) <= _utc(m.created_at) - creado <= VENTANA_CORREO
               for m in correos):
            conn.execute(text("UPDATE comments SET origen = 'correo' WHERE id = :i"), {"i": c.id})


def migrate_add_comment_origen(target_engine=None) -> bool:
    """Agrega las columnas que falten. Devuelve ``True`` si agregó alguna."""
    db_engine = target_engine or engine
    inspector = inspect(db_engine)
    if not inspector.has_table("comments"):
        return False
    columnas = {col["name"] for col in inspector.get_columns("comments")}
    faltan = [c for c in ("author_id", "origen", "estado_nuevo") if c not in columnas]
    if not faltan:
        return False
    with db_engine.connect() as conn:
        if "author_id" in faltan:
            conn.execute(text("ALTER TABLE comments ADD COLUMN author_id INTEGER REFERENCES users(id) ON DELETE SET NULL"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_comments_author_id ON comments (author_id)"))
        if "origen" in faltan:
            conn.execute(text("ALTER TABLE comments ADD COLUMN origen VARCHAR(10) NOT NULL DEFAULT 'app'"))
        if "estado_nuevo" in faltan:
            conn.execute(text("ALTER TABLE comments ADD COLUMN estado_nuevo VARCHAR(20)"))
        _completar_existentes(conn)
        conn.commit()
    return True


if __name__ == "__main__":
    if migrate_add_comment_origen():
        print("Migración aplicada: 'comments' ahora guarda autor, origen y estado nuevo.")
    else:
        print("Las columnas ya existen. No se requiere migración.")
