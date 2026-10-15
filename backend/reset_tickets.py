"""Borra todos los tickets con sus comentarios e historial para empezar de
cero. Los usuarios no se tocan.

Uso (dentro del contenedor o en local):

    python -m backend.reset_tickets              # solo muestra cuántos hay
    python -m backend.reset_tickets --confirmar  # los borra

Sin ``--confirmar`` no se modifica nada. Después del borrado la numeración
de los tickets vuelve a empezar en 1.
"""

import argparse

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from backend.database import SessionLocal, init_db
from backend.models import Comment, History, Ticket


def count_rows(session: Session) -> dict[str, int]:
    """Number of tickets, comments and history entries currently stored."""
    return {
        "tickets": session.scalar(select(func.count()).select_from(Ticket)),
        "comentarios": session.scalar(select(func.count()).select_from(Comment)),
        "historial": session.scalar(select(func.count()).select_from(History)),
    }


def reset_tickets(session: Session, apply: bool = False) -> dict[str, int]:
    """Delete every ticket, comment and history entry when ``apply`` is true.

    Returns the counts found before deleting.
    """
    counts = count_rows(session)
    if apply:
        session.execute(delete(History))
        session.execute(delete(Comment))
        session.execute(delete(Ticket))
        session.commit()
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--confirmar", action="store_true", help="aplica el borrado")
    args = parser.parse_args()

    init_db()
    with SessionLocal() as session:
        counts = reset_tickets(session, apply=args.confirmar)

    verbo = "Se borraron" if args.confirmar else "Se borrarían"
    print(
        f"{verbo}: {counts['tickets']} tickets, {counts['comentarios']} comentarios "
        f"y {counts['historial']} registros de historial. Los usuarios no se tocan."
    )
    if not args.confirmar:
        print("\nNo se modificó nada. Repite el comando con --confirmar para aplicarlo.")


if __name__ == "__main__":
    main()
