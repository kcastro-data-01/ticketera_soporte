"""Única función de fecha y hora del backend, igual que ``formatearFechaHora``
de ``frontend/js/auth.js``: hora de Costa Rica (UTC-6, sin horario de verano)
en 12 horas y sin segundos.

    formatear_fecha_hora(dt)                 → «11/11/2026, 3:40 p. m.»
    formatear_fecha_hora(dt, parte="fecha")  → «11/11/2026»
    formatear_fecha_hora(dt, parte="hora")   → «3:40 p. m.»

Una fecha sin zona se toma como UTC (así las guarda la base de datos).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

ZONA_COSTA_RICA = timezone(timedelta(hours=-6), "America/Costa_Rica")


def formatear_fecha_hora(fecha: datetime | None, parte: str | None = None) -> str:
    if fecha is None:
        return "—"
    if fecha.tzinfo is None:
        fecha = fecha.replace(tzinfo=timezone.utc)
    local = fecha.astimezone(ZONA_COSTA_RICA)
    texto_fecha = f"{local.day:02d}/{local.month:02d}/{local.year}"
    texto_hora = f"{local.hour % 12 or 12}:{local.minute:02d} {'a. m.' if local.hour < 12 else 'p. m.'}"
    if parte == "fecha":
        return texto_fecha
    if parte == "hora":
        return texto_hora
    return f"{texto_fecha}, {texto_hora}"
