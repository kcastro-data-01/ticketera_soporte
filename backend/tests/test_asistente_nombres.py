"""Nombres mal escritos y preguntas de seguimiento en el chat del asistente.

Los conteos por persona los calcula el servidor; la IA libre nunca cuenta los
tickets de alguien (podría hablar de otra persona).
"""

from types import SimpleNamespace

import pytest

from backend.models import User
from backend.services.asistente_service import (
    NO_ENCONTRE_PERSONA,
    _distancia,
    _parecido,
    _personas_nombradas,
)
from backend.tests.test_asistente import _asignar, _persona, ask, fake_claude, login_as  # noqa: F401


@pytest.fixture
def gente(client, session):
    """Laura (Administrador) con 1, José Solano (Técnico) con 2, Carlos Rojas
    (Técnico) con 1, Daniel Solano (Solicitante) y Ana (Técnico, quien pregunta)."""
    headers = login_as(client, session, "Técnico", "ana@tec.local", "Ana Pérez")
    laura = _persona(session, "Laura Méndez", "Administrador", "laura@x.local")
    jose = _persona(session, "José Solano", "Técnico", "jose@x.local")
    carlos = _persona(session, "Carlos Rojas", "Técnico", "carlos@x.local")
    daniel = _persona(session, "Daniel Solano", "Solicitante", "daniel@x.local")
    return SimpleNamespace(
        headers=headers, laura=laura, jose=jose, carlos=carlos, daniel=daniel,
        de_laura=_asignar(session, "Impresora", laura),
        j1=_asignar(session, "VPN", jose),
        j2=_asignar(session, "Correo", jose, state="En proceso"),
        de_carlos=_asignar(session, "Monitor", carlos),
    )


def conversar(client, headers, *turnos):
    """Envía la conversación (preguntas y respuestas alternadas) y devuelve el JSON."""
    roles = ["user", "assistant"]
    mensajes = [{"role": roles[i % 2], "content": texto} for i, texto in enumerate(turnos)]
    resp = client.post("/api/asistente", json={"messages": mensajes}, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


def jose_texto(g):
    return (f"José Solano (Técnico) tiene 2 tickets sin resolver asignados: "
            f"#{g.j1.id} «VPN», #{g.j2.id} «Correo».")


# --- Comparación tolerante -------------------------------------------------------


@pytest.mark.parametrize("a, b, esperado", [
    ("jsoe", "jose", 1),  # letras intercambiadas = un error
    ("crlos", "carlos", 1),
    ("solano", "solano", 0),
    ("lara", "laura", 1),
    ("jose", "josue", 1),
])
def test_edit_distance_counts_swaps_as_one(a, b, esperado):
    assert _distancia(a, b) == esperado


@pytest.mark.parametrize("palabra, parte, coincide", [
    ("jsoe", "jose", True),
    ("joes", "jose", True),
    ("jsee", "jose", False),  # 2 errores en un nombre corto (≤5 letras): no
    ("crlos", "carlos", True),
    ("castilo", "castillo", True),
    ("cstllo", "castillo", True),  # 2 errores en un nombre largo: sí
    ("cstlo", "castillo", False),  # 3 errores: no
    ("osé", "jose", False),  # la primera letra tiene que coincidir
])
def test_similarity_limits(palabra, parte, coincide):
    assert (_parecido(palabra, parte) is not None) is coincide


# --- Casos del chat ---------------------------------------------------------------


def test_misspelled_full_name_is_that_person_not_ambiguous(client, gente, fake_claude):
    datos = ask(client, gente.headers, "jsoe solano cuantos tiketes tiene?").json()
    assert datos == {"respuesta": jose_texto(gente), "fuente": "directa"}
    assert fake_claude.calls == []


def test_follow_up_with_misspelled_person_changes_only_the_person(client, gente, fake_claude):
    primera = "cuantos tickets tiene Laura?"
    laura = ask(client, gente.headers, primera).json()["respuesta"]
    assert laura.startswith("Laura Méndez (Administrador) tiene 1 ticket")

    datos = conversar(client, gente.headers, primera, laura, "y jsoe solano ?")
    assert datos == {"respuesta": jose_texto(gente), "fuente": "directa"}
    assert "Laura" not in datos["respuesta"]
    assert fake_claude.calls == []


def test_count_with_misspelled_first_name_only(client, gente, fake_claude):
    datos = ask(client, gente.headers, "cuantos tiene crlos").json()
    assert datos == {
        "respuesta": f"Carlos Rojas (Técnico) tiene 1 ticket sin resolver asignado: #{gente.de_carlos.id} «Monitor».",
        "fuente": "directa",
    }


def test_unknown_name_is_not_sent_to_the_free_ai(client, gente, fake_claude):
    for pregunta in ("cuantos tickets tiene Fernanda", "Fernanda cuantos tickets tiene", "tickets de fernanda"):
        datos = ask(client, gente.headers, pregunta).json()
        assert datos == {"respuesta": NO_ENCONTRE_PERSONA, "fuente": "directa"}, pregunta
    assert fake_claude.calls == []


def test_unknown_name_as_follow_up(client, gente, fake_claude):
    primera = "cuantos tickets tiene Laura?"
    laura = ask(client, gente.headers, primera).json()["respuesta"]
    datos = conversar(client, gente.headers, primera, laura, "y fernanda?")
    assert datos == {"respuesta": NO_ENCONTRE_PERSONA, "fuente": "directa"}
    assert fake_claude.calls == []


def test_follow_up_with_a_role(client, gente, fake_claude):
    primera = "cuantos tickets tiene Laura?"
    laura = ask(client, gente.headers, primera).json()["respuesta"]
    datos = conversar(client, gente.headers, primera, laura, "y los tecnicos?")
    assert datos["fuente"] == "directa"
    assert datos["respuesta"].startswith("Hay 3 tickets sin resolver asignados a técnicos: "
                                         "José Solano (Técnico) tiene 2")
    assert "Carlos Rojas (Técnico) tiene 1" in datos["respuesta"]


def test_follow_up_with_a_period_keeps_the_rest(client, gente, fake_claude):
    primera = "cuantos tickets nuevos hay hoy?"
    hoy = ask(client, gente.headers, primera).json()["respuesta"]
    assert "hoy" in hoy.lower()
    ayer = conversar(client, gente.headers, primera, hoy, "y ayer?")["respuesta"]
    # Misma consulta (tickets nuevos), solo cambia el período.
    assert "ayer" in ayer.lower() and "hoy" not in ayer.lower()
    assert fake_claude.calls == []


def test_follow_ups_can_chain(client, gente, fake_claude):
    p1 = "cuantos tickets tiene Laura?"
    r1 = ask(client, gente.headers, p1).json()["respuesta"]
    r2 = conversar(client, gente.headers, p1, r1, "y jsoe?")["respuesta"]
    assert r2 == jose_texto(gente)
    r3 = conversar(client, gente.headers, p1, r1, "y jsoe?", r2, "y crlos?")["respuesta"]
    assert r3.startswith("Carlos Rojas (Técnico) tiene 1 ticket")


def test_y_without_a_previous_count_is_not_a_follow_up(client, gente, fake_claude):
    primera = "¿cómo creo un ticket?"
    guia = ask(client, gente.headers, primera).json()["respuesta"]
    conversar(client, gente.headers, primera, guia, "y hola?")
    assert fake_claude.calls, "sin conteo anterior, la pregunta sigue su camino normal"


# --- Desempates -----------------------------------------------------------------------


def test_surname_only_prefers_who_can_have_tickets(session, gente):
    ana = session.query(User).filter_by(email="ana@tec.local").one()
    # José (Técnico) y Daniel (Solicitante) se llaman Solano: para contar, José.
    assert _personas_nombradas(session, ana, "cuantos tickets tiene solano") == [gente.jose]
    assert set(_personas_nombradas(session, ana, "solano", para_conteo=False)) == {gente.jose, gente.daniel}


def test_better_match_wins(session, gente):
    _persona(session, "Josué Mora", "Técnico", "josue@x.local")
    ana = session.query(User).filter_by(email="ana@tec.local").one()
    # «jose» es exacto para José Solano y tiene un error para Josué.
    assert _personas_nombradas(session, ana, "cuantos tiene jose") == [gente.jose]


def test_same_first_name_and_same_role_still_asks(client, session, gente, fake_claude):
    _persona(session, "Carlos Mora", "Técnico", "cmora@x.local")
    datos = ask(client, gente.headers, "cuantos tickets tiene carlos").json()
    assert datos["respuesta"].startswith("Hay varias personas con ese nombre: Carlos Rojas (Técnico) y "
                                         "Carlos Mora (Técnico)")
    completo = ask(client, gente.headers, "cuantos tickets tiene crlos rojas").json()["respuesta"]
    assert completo.startswith("Carlos Rojas (Técnico) tiene 1 ticket")


def test_common_words_are_not_names(session, gente):
    ana = session.query(User).filter_by(email="ana@tec.local").one()
    assert _personas_nombradas(session, ana, "cuantos tickets nuevos hay hoy") == []
    assert _personas_nombradas(session, ana, "cuantos tickets tienen los tecnicos") == []


# --- Interpretación con IA -----------------------------------------------------------


def _datos(persona):
    return {"tipo": "conteo", "estado": None, "periodo": None, "persona": persona, "rol": None, "ticket": None}


def test_interpreted_name_may_be_corrected_by_the_ai(session, gente):
    from backend.services.asistente_service import calcular_desde_interpretacion

    ana = session.query(User).filter_by(email="ana@tec.local").one()
    # La IA corrigió «jsoe» a «jose»: antes se descartaba por no estar tal cual.
    directa, _ = calcular_desde_interpretacion(session, ana, _datos("jose solano"), None, "q onda los tikets d jsoe solano")
    assert directa.texto == jose_texto(gente)


def test_interpreted_unknown_name_never_reaches_the_free_ai(session, gente):
    from backend.services.asistente_service import calcular_desde_interpretacion

    ana = session.query(User).filter_by(email="ana@tec.local").one()
    directa, _ = calcular_desde_interpretacion(session, ana, _datos("fernanda"), None, "q onda los tikets d fernanda")
    assert directa.texto == NO_ENCONTRE_PERSONA
    # Un nombre que la IA inventó (no está en la pregunta) se descarta.
    assert calcular_desde_interpretacion(session, ana, _datos("maria"), None, "que significa prioridad alta") is None
