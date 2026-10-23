"""Respuestas del sistema con lenguaje natural (sin IA): cada tipo se dice de
varias formas elegidas al azar, en tono formal, y en ninguna cambian los
números, los nombres ni los #tickets."""

import re
import string

import pytest

from backend.models import User
from backend.services import asistente_service as a
from backend.tests.test_asistente import _asignar, _persona, login_as
from backend.tests.textos_asistente import CIERRES, sin_cierre

SEMILLAS = range(60)

# Tipos que pide el chat: conteos por estado, pendientes, por persona, por
# rol, sin asignar, críticos, estado de un ticket, saludos, hora y fecha y
# «no entendí».
TIPOS = [
    "grupo_cero", "grupo_cero_bueno", "grupo_uno", "grupo_varios", "total",
    "periodo_cero", "periodo", "pendientes_periodo_cero", "pendientes_periodo",
    "persona_varias", "persona_cero", "persona", "no_encontre_persona", "rol_cero", "rol",
    "estado_ticket", "ticket_no_encontrado", "no_entendi", "saludo", "agradecimiento",
    "ayuda_solicitante", "ayuda_equipo", "sistema", "hora", "fecha",
]


def _campos(plantilla: str) -> set[str]:
    return {campo for _, campo, _, _ in string.Formatter().parse(plantilla) if campo}


# --- Las formas -------------------------------------------------------------------


@pytest.mark.parametrize("tipo", TIPOS)
def test_each_type_has_at_least_three_different_forms(tipo):
    formas = a.VARIANTES[tipo]
    assert len(formas) >= 3
    assert len(set(formas)) == len(formas)


@pytest.mark.parametrize("tipo", TIPOS)
def test_every_form_uses_all_the_data(tipo):
    """Todas las formas de un tipo llevan los mismos datos: ninguna pierde un
    número, un nombre o un #ticket."""
    campos = [_campos(p) for p in a.VARIANTES[tipo]]
    assert all(c == campos[0] for c in campos), campos
    datos = {campo: f"«{campo} #{i + 7} {i + 40}»" for i, campo in enumerate(sorted(campos[0]))}
    for plantilla in a.VARIANTES[tipo]:
        texto = plantilla.format(**datos)
        for valor in datos.values():
            assert texto.count(valor) == 1, (plantilla, valor)


def test_formal_tone_without_extra_exclamations():
    textos = [p for formas in a.VARIANTES.values() for p in formas] + CIERRES
    for texto in textos:
        assert "!" not in texto and "¡" not in texto, texto
        assert not re.search(r"\b(querés|podés|tenés|quieres|puedes|tienes|tuyos?|te|ti)\b", texto), texto


def test_the_requester_is_never_offered_an_explanation(session):
    andrea = User(name="Andrea Castillo", email="a@x.local", role="Solicitante", password_hash="x")
    jose = User(name="José Solano", email="j@x.local", role="Técnico", password_hash="x")
    a._azar.seed(1)
    cierres_andrea = {a._cierre(andrea, n, "pendientes") for n in (1, 3) for _ in range(40)}
    cierres_jose = {a._cierre(jose, n, "pendientes") for n in (1, 3) for _ in range(40)}
    assert not any(c and "explique" in c for c in cierres_andrea)
    assert any(c and "explique" in c for c in cierres_jose)
    assert None in cierres_jose, "el cierre va a veces, no siempre"


# --- En el chat -------------------------------------------------------------------


@pytest.fixture
def datos(client, session):
    """Técnico (José) con tickets en cada estado, uno crítico, uno sin asignar
    y Carlos (Técnico) con dos asignados."""
    login_as(client, session, "Técnico", "tec@tec.local", "José Solano")
    jose = session.query(User).filter_by(email="tec@tec.local").one()
    carlos = _persona(session, "Carlos Solís", "Técnico", "carlos@x.local")
    t = {
        "vpn": _asignar(session, "VPN", carlos),
        "correo": _asignar(session, "Correo", carlos, state="En proceso"),
        "monitor": _asignar(session, "Monitor", jose),
        "teclado": _asignar(session, "Teclado", None),
        "cable": _asignar(session, "Cable", carlos, state="Cerrado"),
    }
    t["teclado"].priority = "Crítica"
    session.commit()
    return jose, t


PREGUNTAS = [
    "cuantos tickets nuevos hay",
    "cuantos hay pendientes",
    "cuantos estan cerrados",
    "cuantos se resolvieron",
    "cuantos tickets hay en total",
    "cuantos tickets criticos hay",
    "cuantos ticketes sin asignar",
    "que tickets tengo pendientes",
    "cuantos tickets tiene Carlos",
    "cuantos tickets tienen los tecnicos",
    "cuantos tickets se cerraron hoy",
    "en que estado esta el ticket #{vpn}",
]


def _numeros(texto: str) -> list[str]:
    """Los #tickets y los números del texto, en orden, sin el nombre del
    principio ni el cierre."""
    return re.findall(r"#\d+|\d+", sin_cierre(texto).replace("**", ""))


def _respuestas(session, user, pregunta):
    respuestas = []
    for semilla in SEMILLAS:
        a._azar.seed(semilla)
        respuestas.append(a.calcular_directa(session, user, pregunta))
    return respuestas


@pytest.mark.parametrize("pregunta", PREGUNTAS)
def test_numbers_and_tickets_never_change_between_forms(session, datos, pregunta):
    jose, t = datos
    pregunta = pregunta.format(**{k: v.id for k, v in t.items()})
    respuestas = _respuestas(session, jose, pregunta)
    assert all(r is not None for r in respuestas)
    # Los mismos datos en cada forma (el orden puede cambiar con la frase).
    numeros = {tuple(sorted(_numeros(r.texto))) for r in respuestas}
    assert len(numeros) == 1, numeros
    # La lista de tickets va igual, debajo del texto.
    listas = {r.lista for r in respuestas}
    assert len(listas) == 1
    for r in respuestas:
        lineas = r.texto.splitlines()
        assert tuple(lineas[1:1 + len(r.lista)]) == r.lista
        # Lo que la IA redacta no cambia: la forma fija de siempre.
        assert r.resumen is None or "**" not in r.resumen
    # Se dice de más de una forma.
    assert len({r.texto.splitlines()[0] for r in respuestas}) >= 3


@pytest.mark.parametrize("pregunta, principal", [
    ("cuantos hay pendientes", "**4**"),
    ("cuantos tickets hay en total", "**5**"),
    ("cuantos tickets tiene Carlos", "**2**"),
    ("cuantos tickets tienen los tecnicos", "**3**"),
    ("en que estado esta el ticket #{vpn}", "**#{vpn}**"),
])
def test_the_main_number_is_in_bold(session, datos, pregunta, principal):
    jose, t = datos
    ids = {k: v.id for k, v in t.items()}
    for r in _respuestas(session, jose, pregunta.format(**ids)):
        assert principal.format(**ids) in r.texto.splitlines()[0], r.texto


def test_introduction_depends_on_the_result(session, datos):
    jose, t = datos
    tres = {r.texto.splitlines()[0] for r in _respuestas(session, jose, "cuantos tickets nuevos hay")}
    assert any(c.startswith("Revisé y hay **3** tickets nuevos") for c in tres), tres
    uno = {r.texto.splitlines()[0] for r in _respuestas(session, jose, "cuantos estan cerrados")}
    assert any(c.startswith("Encontré **1** ticket cerrado") for c in uno), uno
    for ticket in t.values():
        ticket.state = "Resuelto"
    session.commit()
    cero = {r.texto for r in _respuestas(session, jose, "cuantos hay pendientes")}
    assert "Buenas noticias: no hay tickets pendientes." in cero, cero
    assert any(c.startswith("Por ahora no hay tickets pendientes") for c in cero), cero


def test_the_name_and_the_closing_appear_only_sometimes(session, datos):
    jose, _ = datos
    textos = [r.texto for r in _respuestas(session, jose, "cuantos tickets nuevos hay")]
    con_nombre = [x for x in textos if x.startswith("José, ")]
    con_cierre = [x for x in textos if x.splitlines()[-1] in CIERRES]
    assert 0 < len(con_nombre) < len(textos)
    assert 0 < len(con_cierre) < len(textos)


def test_greetings_hour_and_not_understood_vary(session, datos):
    jose, _ = datos
    for pregunta in ("hola", "gracias", "cuantos tickets estan congelados", "que dia es hoy"):
        textos = {r.texto for r in _respuestas(session, jose, pregunta)}
        assert len(textos) >= 3, (pregunta, textos)
    assert {r.texto for r in _respuestas(session, jose, "cuantos tickets estan congelados")} <= set(a.NO_ENTENDI)


def test_same_seed_same_answer(session, datos):
    jose, _ = datos
    a._azar.seed(3)
    primera = a.calcular_directa(session, jose, "cuantos hay pendientes")
    a._azar.seed(3)
    assert a.calcular_directa(session, jose, "cuantos hay pendientes") == primera


def test_ticket_list_is_unchanged(session, datos):
    jose, t = datos
    respuesta = _respuestas(session, jose, "cuantos ticketes sin asignar")[0]
    assert respuesta.lista == (
        f"- #{t['teclado'].id} «Teclado» (Red, prioridad Crítica, estado Nuevo, asignado a sin asignar)",
    )
