"""Cierre automático de tickets Resuelto sin respuesta del solicitante.

Con ``CIERRE_AUTOMATICO`` encendida (apagada por defecto, toda la función):

* Un ticket en Resuelto pasa solo a Cerrado cuando pasan :func:`dias`
  (``CIERRE_DIAS``, 3 por defecto) sin respuesta del solicitante. Cuentan
  días de 24 horas de lunes a sábado (:data:`DIAS_QUE_CUENTAN`), con la hora
  de Costa Rica (UTC−6, la misma de las métricas): el domingo no cuenta.
  Ejemplos: resuelto el viernes 16:00 → martes 16:00; el domingo 11:00 →
  jueves 00:00 (empieza a contar el lunes).
* Si el solicitante comenta (en la app o respondiendo el correo) mientras
  está en Resuelto, vuelve a En proceso (``ticket_service.create_comment``).
  Al resolverse de nuevo el contador empieza otra vez (``Ticket.resuelto_en``).
* Al cerrarse: «Cerrado automáticamente por falta de respuesta» en el
  historial, hecho por «Sistema», y un correo al solicitante y al asignado.

Revisan los tickets: en Vercel, ``POST /api/cron/correo`` (cada minuto, con
un tope de tiempo y de cierres por llamada); en Docker, un hilo cada
:data:`INTERVALO_HILO` segundos.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update

from backend.constants import TicketState

logger = logging.getLogger("backend.services.correo_service")

COSTA_RICA = timezone(timedelta(hours=-6))
# Días que cuentan (lunes = 0 … sábado = 5): el domingo (6) no.
DIAS_QUE_CUENTAN = frozenset({0, 1, 2, 3, 4, 5})
DIAS_POR_DEFECTO = 3.0
AUTOR = "Sistema"
ACCION_CIERRE = "Cierre automático"
ACCION_REAPERTURA = "Reabierto por respuesta"
# Por llamada del cron (cron-job.org corta a los 30 s; el correo usa el resto).
LIMITE_CRON = 5.0
MAX_CIERRES_POR_VUELTA = 10
INTERVALO_HILO = 60


def _encendido(valor: str | None) -> bool:
    return (valor or "").strip().lower() in ("1", "true", "si", "sí", "yes")


def activo(env=None) -> bool:
    """``CIERRE_AUTOMATICO``: enciende toda la función (cierre, reapertura,
    aviso en el correo de Resuelto, fecha en el detalle y correos de cierre)."""
    env = os.environ if env is None else env
    return _encendido(env.get("CIERRE_AUTOMATICO"))


def dias(env=None) -> float:
    """``CIERRE_DIAS`` (3 por defecto). Acepta decimales para probar en local
    (``0.002`` ≈ 3 minutos de lunes a sábado)."""
    env = os.environ if env is None else env
    valor = (env.get("CIERRE_DIAS") or "").strip().replace(",", ".")
    if not valor:
        return DIAS_POR_DEFECTO
    try:
        numero = float(valor)
    except ValueError:
        numero = 0.0
    if numero <= 0:
        logger.warning("CIERRE_DIAS=%s no es válido: se usan %s días", valor, DIAS_POR_DEFECTO)
        return DIAS_POR_DEFECTO
    return numero


def texto_dias(env=None) -> str:
    """«3 días», «1 día» o «0,5 días» para los correos y la ayuda."""
    numero = dias(env)
    texto = f"{numero:g}".replace(".", ",")
    return f"{texto} día" if numero == 1 else f"{texto} días"


def fecha_de_cierre(resuelto_en: datetime, cantidad: float | None = None) -> datetime:
    """``resuelto_en`` más ``cantidad`` días de 24 h que caen de lunes a
    sábado (hora de Costa Rica), en UTC."""
    cantidad = dias() if cantidad is None else cantidad
    if resuelto_en.tzinfo is None:
        resuelto_en = resuelto_en.replace(tzinfo=timezone.utc)
    momento = resuelto_en.astimezone(COSTA_RICA)
    restante = timedelta(days=cantidad)
    while True:
        medianoche = datetime.combine(momento.date() + timedelta(days=1), datetime.min.time(),
                                      tzinfo=COSTA_RICA)
        if momento.weekday() not in DIAS_QUE_CUENTAN:
            momento = medianoche  # el domingo no cuenta: sigue el lunes a las 00:00
            continue
        disponible = medianoche - momento
        if restante <= disponible:
            return (momento + restante).astimezone(timezone.utc)
        restante -= disponible
        momento = medianoche


def cierre_programado(ticket, env=None) -> datetime | None:
    """Cuándo se cerrará solo (``None`` si la función está apagada o el
    ticket no está en Resuelto)."""
    if not activo(env) or ticket.state != TicketState.RESOLVED.value or ticket.resuelto_en is None:
        return None
    return fecha_de_cierre(ticket.resuelto_en, dias(env))


def es_solicitante(ticket, usuario) -> bool:
    """¿Quien comenta es el solicitante (quien creó el ticket)? Si además es
    el asignado, cuenta como IT: no reabre."""
    return (usuario is not None and ticket.created_by_id is not None
            and usuario.id == ticket.created_by_id and usuario.id != ticket.assigned_to_id)


def _cerrar(session, ticket_id: int, ahora: datetime) -> bool:
    """Pasa el ticket a Cerrado con su entrada de historial, solo si sigue en
    Resuelto (si alguien lo cambió mientras tanto, no hace nada)."""
    from backend.models import History, Ticket

    resultado = session.execute(
        update(Ticket)
        .where(Ticket.id == ticket_id, Ticket.state == TicketState.RESOLVED.value)
        .values(state=TicketState.CLOSED.value, resuelto_en=None, updated_at=ahora)
        .execution_options(synchronize_session=False)
    )
    if resultado.rowcount != 1:
        session.rollback()
        return False
    session.add(History(ticket_id=ticket_id, action=ACCION_CIERRE, field="state",
                        old_value=TicketState.RESOLVED.value, new_value=TicketState.CLOSED.value,
                        author=AUTOR, author_id=None))
    session.commit()
    return True


def revisar(session_factory=None, ahora: datetime | None = None, limite: float | None = None,
            maximo: int = MAX_CIERRES_POR_VUELTA, avisar=None, env=None) -> list[int]:
    """Cierra los tickets Resuelto vencidos y avisa por correo. Para a los
    ``limite`` segundos o con ``maximo`` cierres (el resto, en la próxima
    vuelta). Devuelve los números cerrados. Con la función apagada, nada."""
    if not activo(env):
        return []
    from backend.models import Ticket

    if session_factory is None:
        from backend.database import SessionLocal

        session_factory = SessionLocal
    if avisar is None:
        from backend.services.correo_service import avisar_cierre_automatico as avisar
    hasta = time.monotonic() + limite if limite is not None else None
    # En UTC: SQLite guarda la hora tal cual (sin zona) y la lee como UTC.
    ahora = (ahora or datetime.now(timezone.utc)).astimezone(timezone.utc)
    cantidad = dias(env)
    cerrados: list[int] = []
    with session_factory() as session:
        pendientes = session.execute(
            select(Ticket.id, Ticket.resuelto_en)
            .where(Ticket.state == TicketState.RESOLVED.value)
            .order_by(Ticket.resuelto_en, Ticket.id)
        ).all()
        for ticket_id, resuelto_en in pendientes:
            if len(cerrados) >= maximo or (hasta is not None and time.monotonic() >= hasta):
                break
            if resuelto_en is None:
                # Resuelto sin fecha (copiado de otra base): cuenta desde ahora.
                session.execute(update(Ticket).where(Ticket.id == ticket_id)
                                .values(resuelto_en=ahora, updated_at=Ticket.updated_at)
                                .execution_options(synchronize_session=False))
                session.commit()
                continue
            if fecha_de_cierre(resuelto_en, cantidad) > ahora:
                continue
            if not _cerrar(session, ticket_id, ahora):
                continue
            cerrados.append(ticket_id)
            logger.info("Ticket #%s cerrado automáticamente por falta de respuesta", ticket_id)
            try:
                avisar(session, session.get(Ticket, ticket_id), env=env)
            except Exception:  # noqa: BLE001 — el cierre ya quedó guardado
                logger.exception("No se pudo avisar el cierre automático del ticket #%s", ticket_id)
    return cerrados


# --- Hilo en segundo plano (Docker) -------------------------------------------

_detener = threading.Event()
_hilo: threading.Thread | None = None


def _bucle(session_factory) -> None:
    logger.info("cierre automático: revisando los tickets Resuelto cada %s s (%s de lunes a sábado)",
                INTERVALO_HILO, texto_dias())
    while not _detener.is_set():
        try:
            revisar(session_factory)
        except Exception:
            logger.exception("error al revisar el cierre automático")
        _detener.wait(INTERVALO_HILO)


def iniciar_hilo(session_factory=None) -> bool:
    """En Docker (modo hilo) arranca la revisión periódica si
    ``CIERRE_AUTOMATICO`` está encendida. En Vercel lo hace el cron."""
    global _hilo
    from backend.entorno import en_vercel

    if not activo() or en_vercel() or (os.environ.get("CORREO_MODO") or "").strip().lower() == "cron":
        return False
    if _hilo is not None and _hilo.is_alive():
        return False
    if session_factory is None:
        from backend.database import SessionLocal

        session_factory = SessionLocal
    _detener.clear()
    _hilo = threading.Thread(target=_bucle, args=(session_factory,), name="cierre-automatico",
                             daemon=True)
    _hilo.start()
    return True


def detener_hilo() -> None:
    _detener.set()
