"""Idempotent migration: users with the removed ``Soporte`` role become
``Técnico``.

Safe to run multiple times: once no user has the old role it does nothing.
"""

from sqlalchemy import text

from backend.constants import LEGACY_SUPPORT_ROLE, UserRole
from backend.database import engine


def migrate_remove_support_role(target_engine=None) -> int:
    """Move every ``Soporte`` user to ``Técnico``; return how many changed."""
    db_engine = target_engine or engine
    with db_engine.connect() as conn:
        result = conn.execute(
            text("UPDATE users SET role = :new WHERE role = :old"),
            {"new": UserRole.TECHNICIAN.value, "old": LEGACY_SUPPORT_ROLE},
        )
        conn.commit()
    return result.rowcount


if __name__ == "__main__":
    changed = migrate_remove_support_role()
    print(f"Usuarios movidos de 'Soporte' a 'Técnico': {changed}.")
