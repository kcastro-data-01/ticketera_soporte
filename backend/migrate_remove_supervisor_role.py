"""Idempotent migration: users with the removed ``Supervisor`` role become
``Técnico``.

Runs on every start (``init_db``) with plain SQL, so it works the same on
SQLite (Docker) and Postgres (Neon, Vercel). Once no user has the old role it
does nothing. Each change is written to the log (at ``WARNING`` so it shows in
the default output of Docker and Vercel).
"""

import logging

from sqlalchemy import text

from backend.constants import LEGACY_SUPERVISOR_ROLE, UserRole
from backend.database import engine

logger = logging.getLogger(__name__)


def migrate_remove_supervisor_role(target_engine=None) -> int:
    """Move every ``Supervisor`` user to ``Técnico``; return how many changed."""
    db_engine = target_engine or engine
    with db_engine.begin() as conn:
        emails = conn.execute(
            text("SELECT email FROM users WHERE role = :old ORDER BY id"),
            {"old": LEGACY_SUPERVISOR_ROLE},
        ).scalars().all()
        if not emails:
            return 0
        conn.execute(
            text("UPDATE users SET role = :new WHERE role = :old"),
            {"new": UserRole.TECHNICIAN.value, "old": LEGACY_SUPERVISOR_ROLE},
        )
    logger.warning(
        "Rol Supervisor eliminado: %d usuario(s) pasaron a Técnico (%s)",
        len(emails), ", ".join(emails),
    )
    return len(emails)


if __name__ == "__main__":
    changed = migrate_remove_supervisor_role()
    print(f"Usuarios movidos de 'Supervisor' a 'Técnico': {changed}.")
