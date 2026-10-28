"""Tareas programadas desde afuera (cron-job.org) para la versión de Vercel,
donde no hay hilos en segundo plano.

``POST /api/cron/correo`` hace un ciclo de lectura del buzón (Elementos
enviados y bandeja de entrada). Lo protege ``CRON_SECRET``: hay que mandar
``Authorization: Bearer <CRON_SECRET>``. Sin ``CRON_SECRET`` configurado la
ruta no existe (404).
"""

import hmac
import logging
import os
from contextlib import contextmanager

from fastapi import APIRouter, Header, HTTPException, status
from sqlalchemy import text

from backend import database
from backend.services import correo_service
from backend.services.correo_auth import SinSesionError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/cron", tags=["Cron"])

# Número fijo del candado de Postgres (pg_try_advisory_lock) del buzón.
CANDADO_CORREO = 4_270_001


def secreto_cron() -> str:
    return (os.environ.get("CRON_SECRET") or "").strip()


def verificar_secreto(authorization: str | None) -> None:
    secreto = secreto_cron()
    if not secreto:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")
    esperado = f"Bearer {secreto}".encode()
    recibido = (authorization or "").strip().encode()
    if not hmac.compare_digest(recibido, esperado):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No autorizado")


@contextmanager
def candado(nombre: int):
    """``True`` si esta llamada tiene el candado; ``False`` si otra lo tiene.

    En Postgres es un candado de sesión (se libera solo si la función se
    corta). En SQLite (Docker) no hace falta: siempre ``True``.
    """
    if database.es_sqlite(database.engine):
        yield True
        return
    with database.engine.connect() as conn:
        obtenido = conn.execute(text("SELECT pg_try_advisory_lock(:n)"), {"n": nombre}).scalar()
        try:
            yield bool(obtenido)
        finally:
            if obtenido:
                conn.execute(text("SELECT pg_advisory_unlock(:n)"), {"n": nombre})
            conn.commit()


@router.post("/correo", summary="Revisar el buzón una vez (cron-job.org)")
def revisar_correo(authorization: str | None = Header(default=None)) -> dict:
    """Un ciclo de lectura del buzón que termina en menos de 30 s. Devuelve
    cuántos correos terminaron en cada resultado (``pendientes``: los que
    quedan para la próxima llamada)."""
    verificar_secreto(authorization)
    with candado(CANDADO_CORREO) as obtenido:
        if not obtenido:
            return {"estado": "ocupado", "conteo": {}}
        try:
            conteo = correo_service.revisar_una_vez()
        except correo_service.CorreoApagado as error:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error))
        except SinSesionError as error:
            logger.error("sesión de Microsoft no iniciada o vencida (%s): ejecuta "
                         "python -m backend.correo_login con DATABASE_URL de esta base", error)
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                                detail="La sesión del buzón no está iniciada o venció")
    return {"estado": "ok", "conteo": conteo}
