"""Reinicia los usuarios: borra los existentes y crea un usuario de prueba
por cada rol con una contraseña conocida.

Uso (dentro del contenedor o en local):

    python -m backend.reset_users                          # solo muestra
    python -m backend.reset_users --confirmar              # deja solo los de prueba
    python -m backend.reset_users --conservar sofi --confirmar

Con ``--conservar`` se conserva además todo usuario cuyo nombre o email
contenga ese texto (sin distinguir mayúsculas); si nadie coincide, el script
se detiene. Sin ``--confirmar`` no se modifica nada: solo se muestra lo que
se haría.

Los tickets asignados a usuarios borrados quedan sin asignar y el historial
conserva el nombre del autor (las claves foráneas usan ``ON DELETE SET NULL``).
Volver a ejecutarlo es seguro: si un usuario de prueba ya existe, solo se
reactiva y se le restablece la contraseña.
"""

import argparse

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from backend.auth import hash_password
from backend.constants import UserRole
from backend.database import SessionLocal, init_db
from backend.models import User

DEFAULT_PASSWORD = "482026"

# Un usuario de prueba por rol: (nombre, email).
TEST_USERS: dict[UserRole, tuple[str, str]] = {
    UserRole.ADMIN: ("Laura Méndez", "laura.mendez@adn.local"),
    UserRole.TECHNICIAN: ("José Solano", "jose.solano@tec.local"),
    UserRole.REQUESTER: ("Andrea Castillo", "andrea.castillo@soli.local"),
}


def reset_users(
    session: Session, keep: str | None = None, password: str = DEFAULT_PASSWORD, apply: bool = False
) -> dict:
    """Delete every user except the test users (and those matching ``keep``,
    when given) and create or refresh one test user per role.

    Returns a summary ``{"kept": [...], "deleted": [...], "test_users": [...]}``
    with emails. Nothing is written unless ``apply`` is true.
    """
    kept = []
    if keep is not None:
        if not keep.strip():
            raise ValueError("El texto de --conservar no puede estar vacío.")
        term = f"%{keep.strip().lower()}%"
        kept = session.scalars(
            select(User).where(
                or_(func.lower(User.name).like(term), func.lower(User.email).like(term))
            )
        ).all()
        if not kept:
            raise ValueError(
                f"Ningún usuario coincide con '{keep}': no se borra nada."
            )

    test_emails = {email for _, email in TEST_USERS.values()}
    kept_ids = {user.id for user in kept}
    to_delete = [
        user
        for user in session.scalars(select(User)).all()
        if user.id not in kept_ids and user.email.lower() not in test_emails
    ]

    summary = {
        "kept": [user.email for user in kept],
        "deleted": [user.email for user in to_delete],
        "test_users": [],
    }

    for role, (name, email) in TEST_USERS.items():
        summary["test_users"].append((role.value, email))
        if not apply:
            continue
        user = session.scalar(select(User).where(func.lower(User.email) == email))
        if user is None:
            user = User(name=name, email=email)
            session.add(user)
        user.name = name
        user.role = role.value
        user.is_active = True
        user.password_hash = hash_password(password)

    if apply:
        for user in to_delete:
            session.delete(user)
        session.commit()
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--conservar", help="texto del nombre o email a conservar (opcional)")
    parser.add_argument("--password", default=DEFAULT_PASSWORD, help="contraseña de los usuarios de prueba")
    parser.add_argument("--confirmar", action="store_true", help="aplica los cambios")
    args = parser.parse_args()

    init_db()
    with SessionLocal() as session:
        try:
            summary = reset_users(session, args.conservar, args.password, args.confirmar)
        except ValueError as error:
            raise SystemExit(f"ERROR: {error}")

    if summary["kept"]:
        print("Se conservan:")
        for email in summary["kept"]:
            print(f"  - {email}")
    print("Se borran:" if args.confirmar else "Se borrarían:")
    for email in summary["deleted"] or ["(ninguno)"]:
        print(f"  - {email}")
    print(f"Usuarios de prueba (contraseña: {args.password}):")
    for role, email in summary["test_users"]:
        print(f"  - {role:<14} {email}")
    if not args.confirmar:
        print("\nNo se modificó nada. Repite el comando con --confirmar para aplicarlo.")
    else:
        print("\nCambios aplicados.")


if __name__ == "__main__":
    main()
