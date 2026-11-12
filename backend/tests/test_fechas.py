"""backend/fechas.py: la única función de fecha y hora del backend, con el
mismo texto que formatearFechaHora (frontend/js/auth.js)."""

from datetime import datetime, timezone

import pytest

from backend.fechas import formatear_fecha_hora


@pytest.mark.parametrize("utc, esperado", [
    (datetime(2026, 11, 11, 17, 15, tzinfo=timezone.utc), "11/11/2026, 11:15 a. m."),
    (datetime(2026, 11, 11, 21, 40, 9, tzinfo=timezone.utc), "11/11/2026, 3:40 p. m."),
    (datetime(2026, 11, 12, 6, 5, tzinfo=timezone.utc), "12/11/2026, 12:05 a. m."),
    (datetime(2026, 11, 12, 18, 0, tzinfo=timezone.utc), "12/11/2026, 12:00 p. m."),
    (datetime(2026, 11, 12, 5, 59, tzinfo=timezone.utc), "11/11/2026, 11:59 p. m."),
])
def test_doce_horas_sin_segundos_en_hora_de_costa_rica(utc, esperado):
    assert formatear_fecha_hora(utc) == esperado


def test_sin_zona_se_toma_como_utc_y_las_partes_sueltas():
    sin_zona = datetime(2026, 11, 11, 21, 40)
    assert formatear_fecha_hora(sin_zona) == "11/11/2026, 3:40 p. m."
    assert formatear_fecha_hora(sin_zona, parte="fecha") == "11/11/2026"
    assert formatear_fecha_hora(sin_zona, parte="hora") == "3:40 p. m."
    assert formatear_fecha_hora(None) == "—"
