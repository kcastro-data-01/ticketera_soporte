"""Prueba «Explicar con IA» con el modelo real (Ollama) y dos tickets de ejemplo.

Uso (con la app levantada en Docker):

    docker compose exec ticketera python -m backend.probar_explicar_ia

Crea dos tickets de prueba —uno que dice solo «no sirve» y uno largo y
confuso—, le pide la explicación a la IA configurada (``QWEN_MODELO``) y
muestra el resultado y cuánto tardó. Los tickets quedan creados para que
también los pruebes con el botón en la app; con ``--borrar`` se eliminan al
final.
"""

from __future__ import annotations

import argparse
import json
import sys
import time

from sqlalchemy import select

from backend.constants import UserRole
from backend.database import SessionLocal, init_db
from backend.models import User
from backend.schemas import TicketCreate
from backend.services import asistente_service, explicacion_service, ticket_service

CORTO = ("No sirve", "no sirve")
LARGO = (
    "Problema con la impresora y otras cosas",
    "\n\n".join([
        "Hola buenas, les escribo porque desde el lunes la impresora HP 4020 del segundo piso "
        "marca error 49 cada vez que alguien manda a imprimir algo largo.",
        "Mi compañera dice que a ella también le pasaba con la otra impresora el año pasado y que "
        "se arregló sola, pero no sé si es lo mismo porque esa era de otra marca y estaba en otro piso.",
        "También quería comentar que el aire acondicionado de la sala está muy frío y que la "
        "cafetera no funciona bien desde hace semanas, aunque eso no es urgente para nada.",
        "Además el wifi a veces anda lento en la tarde, pero creo que es porque hay mucha gente "
        "conectada a esa hora y no sé si eso tiene algo que ver con la impresora o no.",
        "Ya reinicié la impresora dos veces y cambié el tóner, pero sigue saliendo el mismo error.",
        "Necesitamos imprimir los contratos del viernes, por favor ayúdenme lo antes posible.",
    ]),
)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--borrar", action="store_true", help="eliminar los tickets de prueba al final")
    args = parser.parse_args(argv)

    init_db()
    proveedor = asistente_service.crear_proveedor()
    print(f"Proveedor: {getattr(proveedor, 'nombre', '?')} · modelo: {getattr(proveedor, 'modelo', '-')}")

    with SessionLocal() as session:
        admin = session.scalar(select(User).where(
            User.role == UserRole.ADMIN.value, User.is_active.is_(True)).order_by(User.id))
        if admin is None:
            print("No hay un Administrador activo: crea uno en la app primero.")
            return 1
        creados = []
        for titulo, descripcion in (CORTO, LARGO):
            ticket = ticket_service.create_ticket(session, TicketCreate(
                title=titulo, description=descripcion, category="Software", priority="Media"), admin)
            creados.append(ticket.id)
            print("\n" + "=" * 70)
            print(f"Ticket #{ticket.id} «{titulo}» ({len(descripcion.split())} palabras)")
            inicio = time.monotonic()
            try:
                datos = explicacion_service.explicar(session, proveedor, ticket, admin)
            except (asistente_service.AsistenteNoDisponible,
                    explicacion_service.ExplicacionInvalida) as error:
                print(f"ERROR: {error}  (detalle en: docker compose logs ticketera | grep IA:)")
                continue
            print(f"Tardó {time.monotonic() - inicio:.1f} s")
            print(f"Claridad (servidor): {datos['claridad']} — {datos['motivo_claridad']}")
            print(f"Explicación: {datos['explicacion']['explicacion']}")
            print(json.dumps(datos["explicacion"], ensure_ascii=False, indent=2))
            print(f"Ábrelo en la app: http://localhost:8000/detalle.html?id={ticket.id}")

        if args.borrar:
            for ticket_id in creados:
                ticket_service.delete_ticket(session, ticket_id, admin)
            print(f"\nTickets de prueba eliminados: {', '.join(f'#{i}' for i in creados)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
