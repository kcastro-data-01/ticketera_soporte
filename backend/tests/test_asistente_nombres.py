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
from backend.tests.textos_asistente import es_forma, negrita


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


def es_de_jose(texto, g):
    """¿Es el conteo de José Solano (2 tickets), dicho de cualquier forma?"""
    return es_forma(texto, "persona", persona="José Solano (Técnico)", n=negrita(2), tickets="tickets",
                    asignados="asignados", lista=f"#{g.j1.id} «VPN», #{g.j2.id} «Correo»")


def es_de_una(texto, persona, ticket, titulo):
    """¿Es el conteo de ``persona`` con un solo ticket?"""
    return es_forma(texto, "persona", persona=persona, n=negrita(1), tickets="ticket",
                    asignados="asignado", lista=f"#{ticket.id} «{titulo}»")


def directa(datos):
    assert datos["fuente"] == "directa", datos
    return datos["respuesta"]


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
    assert es_de_jose(directa(datos), gente), datos
    assert fake_claude.calls == []


def test_follow_up_with_misspelled_person_changes_only_the_person(client, gente, fake_claude):
    primera = "cuantos tickets tiene Laura?"
    laura = ask(client, gente.headers, primera).json()["respuesta"]
    assert es_de_una(laura, "Laura Méndez (Administrador)", gente.de_laura, "Impresora"), laura

    datos = conversar(client, gente.headers, primera, laura, "y jsoe solano ?")
    assert es_de_jose(directa(datos), gente), datos
    assert "Laura" not in datos["respuesta"]
    assert fake_claude.calls == []


def test_count_with_misspelled_first_name_only(client, gente, fake_claude):
    datos = ask(client, gente.headers, "cuantos tiene crlos").json()
    assert es_de_una(directa(datos), "Carlos Rojas (Técnico)", gente.de_carlos, "Monitor"), datos


def test_unknown_name_is_not_sent_to_the_free_ai(client, gente, fake_claude):
    for pregunta in ("cuantos tickets tiene Fernanda", "Fernanda cuantos tickets tiene", "tickets de fernanda"):
        datos = ask(client, gente.headers, pregunta).json()
        assert directa(datos) in NO_ENCONTRE_PERSONA, pregunta
    assert fake_claude.calls == []


def test_unknown_name_as_follow_up(client, gente, fake_claude):
    primera = "cuantos tickets tiene Laura?"
    laura = ask(client, gente.headers, primera).json()["respuesta"]
    datos = conversar(client, gente.headers, primera, laura, "y fernanda?")
    assert directa(datos) in NO_ENCONTRE_PERSONA
    assert fake_claude.calls == []


def test_follow_up_with_a_role(client, gente, fake_claude):
    primera = "cuantos tickets tiene Laura?"
    laura = ask(client, gente.headers, primera).json()["respuesta"]
    datos = conversar(client, gente.headers, primera, laura, "y los tecnicos?")
    g = gente
    assert es_forma(directa(datos), "rol", despues=" Ana Pérez (Técnico) no tiene ninguno.", n=negrita(3),
                    tickets="tickets", asignados="asignados", rol="técnicos",
                    detalle=(f"José Solano (Técnico) tiene 2 (#{g.j1.id}, #{g.j2.id}) y "
                             f"Carlos Rojas (Técnico) tiene 1 (#{g.de_carlos.id})")), datos


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
    assert es_de_jose(r2, gente), r2
    r3 = conversar(client, gente.headers, p1, r1, "y jsoe?", r2, "y crlos?")["respuesta"]
    assert es_de_una(r3, "Carlos Rojas (Técnico)", gente.de_carlos, "Monitor"), r3


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
    assert es_forma(directa(datos), "persona_varias",
                    personas="Carlos Rojas (Técnico) y Carlos Mora (Técnico)"), datos
    completo = ask(client, gente.headers, "cuantos tickets tiene crlos rojas").json()["respuesta"]
    assert es_de_una(completo, "Carlos Rojas (Técnico)", gente.de_carlos, "Monitor"), completo


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
    assert es_de_jose(directa.texto, gente), directa.texto


def test_interpreted_unknown_name_never_reaches_the_free_ai(session, gente):
    from backend.services.asistente_service import calcular_desde_interpretacion

    ana = session.query(User).filter_by(email="ana@tec.local").one()
    directa, _ = calcular_desde_interpretacion(session, ana, _datos("fernanda"), None, "q onda los tikets d fernanda")
    assert directa.texto in NO_ENCONTRE_PERSONA
    # Un nombre que la IA inventó (no está en la pregunta) se descarta.
    assert calcular_desde_interpretacion(session, ana, _datos("maria"), None, "que significa prioridad alta") is None
