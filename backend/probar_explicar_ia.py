"""Prueba «Explicar con IA» con el modelo real (Ollama) y tres tickets de ejemplo.

Uso (con la app levantada en Docker):

    docker compose exec ticketera python -m backend.probar_explicar_ia

Crea tres tickets de prueba —una impresora que «no sirve», un correo al que
no se puede entrar y uno de red largo y confuso—, le pide la explicación a la
IA configurada (``QWEN_MODELO``) y muestra el resultado y cuánto tardó. Los
tickets quedan creados para que también los pruebes con el botón en la app;
con ``--borrar`` se eliminan al final.
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

# (título, descripción, categoría)
TICKETS = [
    ("Impresora", "no sirve", "Hardware"),
    ("No puedo entrar al correo",
     "Desde ayer intento entrar al correo en la computadora de la oficina y no me deja.", "Accesos"),
    (
        "La red y varias cosas más",
        "\n\n".join([
            "Buenas, escribo porque desde hace como una semana la conexión en el área de ventas es "
            "un desastre, a veces el cable funciona y a veces no, y el wifi en la sala de reuniones "
            "se desconecta justo cuando hay videollamadas con clientes.",
            "Un compañero dice que puede ser porque movieron unos muebles y quizás pisaron algún "
            "cable, pero otro dice que es el proveedor de internet porque en su casa también anda mal.",
            "También la impresora del pasillo hace un ruido raro y el proyector de la sala tarda en "
            "encender, aunque eso es lo de menos.",
            "Ya desconectamos y volvimos a conectar el cable de una de las computadoras y por un "
            "rato funcionó, pero luego se volvió a caer.",
            "Mañana tenemos una presentación importante con un cliente, ojalá lo puedan ver hoy.",
        ]),
        "Software",
    ),
]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--borrar", action="store_true", help="eliminar los tickets de prueba al final")
    parser.add_argument("--solo", metavar="TEXTO",
                        help="probar solo los tickets cuyo título contiene TEXTO (p. ej. impresora)")
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
        tickets = [t for t in TICKETS if not args.solo or args.solo.lower() in t[0].lower()]
        for titulo, descripcion, categoria in tickets:
            ticket = ticket_service.create_ticket(session, TicketCreate(
                title=titulo, description=descripcion, category=categoria, priority="Media"), admin)
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
            if getattr(proveedor, "ultimos_tokens", None):
                print(f"Tokens: {proveedor.ultimos_tokens}")
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
