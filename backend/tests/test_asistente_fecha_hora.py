"""«¿Qué hora es?», «¿qué día es hoy?», «¿qué fecha es?»: las responde el
servidor, sin IA, con la hora de Costa Rica y tolerando errores de escritura."""

from datetime import datetime, timezone

import pytest

from backend.services import asistente_service as a
from backend.tests.test_asistente import ask, fake_claude, login_as  # noqa: F401
from backend.tests.test_asistente_saludos import eventos

JUEVES_TARDE = datetime(2026, 10, 22, 15, 50, tzinfo=a.ZONA_COSTA_RICA)
CON_HORA = "Son las 3:50 p. m. del jueves 22 de octubre de 2026."
SOLO_FECHA = "Hoy es jueves 22 de octubre de 2026."


@pytest.fixture
def tecnico(client, session):
    return login_as(client, session, "Técnico", "jose@tec.local", "José Solano")


@pytest.fixture(autouse=True)
def reloj(monkeypatch):
    monkeypatch.setattr(a, "_ahora_costa_rica", lambda: JUEVES_TARDE)


@pytest.mark.parametrize("pregunta", [
    "qué hora es", "¿Qué hora es?", "QUE HORA ES", "que hroa es", "q ora es", "ke hora es",
    "me dice la hora, por favor", "¿qué hora es en Costa Rica?", "buenos días, ¿qué hora es?",
    "que hora es ahora", "sabes que hora es",
])
def test_la_hora_la_responde_el_servidor(client, tecnico, fake_claude, pregunta):
    assert ask(client, tecnico, pregunta).json() == {"respuesta": CON_HORA, "fuente": "directa"}
    assert fake_claude.calls == []


@pytest.mark.parametrize("pregunta", [
    "qué día es hoy", "¿Qué fecha es?", "que fehca es hoy", "qué dia es oy", "a qué fecha estamos",
    "cual es la fecha de hoy", "Buenas tardes, ¿qué día es?", "que dai es hoy",
])
def test_la_fecha_la_responde_el_servidor(client, tecnico, fake_claude, pregunta):
    assert ask(client, tecnico, pregunta).json() == {"respuesta": SOLO_FECHA, "fuente": "directa"}
    assert fake_claude.calls == []


def test_tambien_para_el_solicitante_y_por_partes(client, session, tecnico, fake_claude):
    solicitante = login_as(client, session, "Solicitante", "andrea@soli.local", "Andrea Castillo")
    assert ask(client, solicitante, "qué hora es").json()["respuesta"] == CON_HORA
    assert eventos(client, tecnico, "que fecha es") == [{"t": SOLO_FECHA}, {"fin": True, "fuente": "directa"}]
    assert fake_claude.calls == []


@pytest.mark.parametrize("pregunta", [
    "¿a qué hora se cerró el ticket #5?", "qué tickets se crearon hoy", "qué día vence el ticket",
    "cuántos tickets nuevos hay", "buenos días", "qué día es mañana", "hola", "y hola?", "que hola es",
])
def test_otras_preguntas_siguen_su_camino(pregunta):
    assert a.respuesta_fecha_hora(pregunta, JUEVES_TARDE) is None


@pytest.mark.parametrize(("hora", "minuto", "esperado"), [
    (1, 5, "Es la 1:05 a. m."),
    (0, 0, "Son las 12:00 a. m."),
    (12, 30, "Son las 12:30 p. m."),
    (13, 7, "Es la 1:07 p. m."),
    (23, 59, "Son las 11:59 p. m."),
])
def test_formato_de_la_hora(hora, minuto, esperado):
    ahora = datetime(2026, 1, 4, hora, minuto, tzinfo=a.ZONA_COSTA_RICA)
    assert a.respuesta_fecha_hora("qué hora es", ahora) == f"{esperado} del domingo 4 de enero de 2026."


def test_hora_de_costa_rica_sin_horario_de_verano():
    utc = datetime(2026, 7, 1, 3, 30, tzinfo=timezone.utc)
    assert utc.astimezone(a.ZONA_COSTA_RICA).strftime("%d %H:%M") == "30 21:30"


def test_en_medio_de_una_conversacion(client, tecnico, fake_claude):
    mensajes = [
        {"role": "user", "content": "¿cuántos tickets nuevos hay?"},
        {"role": "assistant", "content": "No hay tickets nuevos."},
        {"role": "user", "content": "y qué hora es"},
    ]
    resp = client.post("/api/asistente", json={"messages": mensajes}, headers=tecnico)
    assert resp.json() == {"respuesta": CON_HORA, "fuente": "directa"}
    assert fake_claude.calls == []
