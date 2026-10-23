"""Conteos por estado en el chat (sin IA): las distintas formas de nombrar
cada estado, el total solo cuando no se pide otra cosa y los períodos
(«hoy», «esta semana»…) con el mismo criterio que el panel de métricas."""

from datetime import date

import pytest

from backend.models import History, Ticket, User
from backend.services import metricas_service
from backend.services.asistente_service import NO_ENTENDI, detectar_consulta
from backend.tests.test_asistente import ask, fake_claude, login_as  # noqa: F401 (fixture)
from backend.tests.test_ia_ticket import preguntar
from backend.tests.test_metricas import cr
from backend.tests.textos_asistente import cabecera, es_forma, lista, negrita

HOY = date(2026, 10, 14)  # miércoles; la semana empieza el lunes 12


@pytest.fixture
def tickets(client, session, monkeypatch):
    """Seis tickets visibles para un Técnico, con sus pasos de estado."""
    monkeypatch.setattr(metricas_service, "hoy", lambda: HOY)
    headers = login_as(client, session, "Técnico", "tec@tec.local", "José Solano")

    def ticket(titulo, creado, estado, *pasos):
        t = Ticket(title=titulo, description="Descripción", category="Red", priority="Media",
                   state=estado, created_at=creado)
        session.add(t)
        session.commit()
        for nuevo, cuando in pasos:
            session.add(History(ticket_id=t.id, action="Cambio de estado", field="state",
                                old_value="—", new_value=nuevo, created_at=cuando))
        session.commit()
        return t

    t = {
        # Resuelto el lunes y cerrado hoy.
        "cerrado": ticket("Cable de red", cr("2026-10-01"), "Cerrado",
                          ("Resuelto", cr("2026-10-12", "08:00")), ("Cerrado", cr("2026-10-14", "09:00"))),
        "semana_pasada": ticket("Impresora", cr("2026-10-05"), "Resuelto",
                                ("Resuelto", cr("2026-10-09"))),
        # Pasó a Resuelto la semana pasada y otra vez esta: cuenta la primera.
        "dos_veces": ticket("Correo lento", cr("2026-10-02"), "Resuelto",
                            ("Resuelto", cr("2026-10-08")), ("Resuelto", cr("2026-10-13"))),
        "nuevo": ticket("Monitor nuevo", cr("2026-10-14", "08:00"), "Nuevo"),
        "en_proceso": ticket("VPN", cr("2026-10-10"), "En proceso",
                             ("En proceso", cr("2026-10-13"))),
        "hoy": ticket("Acceso a carpeta", cr("2026-10-14", "07:00"), "Resuelto",
                      ("Resuelto", cr("2026-10-14", "11:00"))),
    }
    return headers, t


def _directa(client, headers, pregunta, **kwargs):
    resp = preguntar(client, headers, pregunta, **kwargs) if kwargs else ask(client, headers, pregunta)
    assert resp.status_code == 200, resp.text
    assert resp.json()["fuente"] == "directa", resp.json()
    return resp.json()["respuesta"]


def test_resolvido_counts_resolved_not_the_total(client, tickets, fake_claude):
    headers, _ = tickets
    respuesta = _directa(client, headers, "cuantos ticketes se han resolvido?")
    assert es_forma(cabecera(respuesta), "grupo_varios", n=negrita(4), frase="tickets resueltos o cerrados")
    assert "en total" not in respuesta
    assert fake_claude.calls == []


def test_resolved_this_week_uses_the_first_step_to_resolved(client, tickets, fake_claude):
    headers, t = tickets
    respuesta = _directa(client, headers, "cuantos tickets se resolvieron esta semana")
    assert es_forma(cabecera(respuesta), "periodo", cuando="esta semana", verbo="se resolvieron",
                    n=negrita(2), tickets="tickets"), respuesta
    assert {l.split()[1] for l in lista(respuesta)} == {f"#{t['cerrado'].id}", f"#{t['hoy'].id}"}


def test_closed_counts_only_closed(client, tickets, fake_claude):
    headers, t = tickets
    respuesta = _directa(client, headers, "cuantos estan cerrados")
    assert es_forma(cabecera(respuesta), "grupo_uno", n=negrita(1), frase="ticket cerrado"), respuesta
    assert lista(respuesta) == [f"- #{t['cerrado'].id} «Cable de red» "
                                "(Red, prioridad Media, estado Cerrado, asignado a sin asignar)"]


def test_pending_counts_new_and_in_progress(client, tickets, fake_claude):
    headers, t = tickets
    respuesta = _directa(client, headers, "cuantos hay pendientes")
    assert es_forma(cabecera(respuesta), "grupo_varios", n=negrita(2),
                    frase="tickets pendientes (1 nuevo y 1 en proceso)"), respuesta
    assert {l.split()[1] for l in lista(respuesta)} == {f"#{t['nuevo'].id}", f"#{t['en_proceso'].id}"}


def test_pending_this_week_are_created_this_week_and_still_open(client, tickets, fake_claude):
    headers, t = tickets
    respuesta = _directa(client, headers, "cuantos pendientes esta semana")
    # El «En proceso» se creó el sábado 10: no cuenta.
    assert es_forma(cabecera(respuesta), "pendientes_periodo", cuando="esta semana", verbo="se creó",
                    n=negrita(1), tickets="ticket", siguen="sigue pendiente", desglose="(1 nuevo)"), respuesta
    assert lista(respuesta) == [f"- #{t['nuevo'].id} «Monitor nuevo» (Red, prioridad Media, estado Nuevo, "
                                "asignado a sin asignar)"]


def test_finished_counts_as_resolved(client, tickets, fake_claude):
    headers, _ = tickets
    respuesta = _directa(client, headers, "cuantos tickets terminados")
    assert es_forma(cabecera(respuesta), "grupo_varios", n=negrita(4), frase="tickets resueltos o cerrados")


def test_solved_today(client, tickets, fake_claude):
    headers, t = tickets
    respuesta = _directa(client, headers, "cuantos tickets solucionados hoy")
    assert es_forma(cabecera(respuesta), "periodo", cuando="hoy", verbo="se resolvió", n=negrita(1),
                    tickets="ticket"), respuesta
    assert lista(respuesta)[0].startswith(f"- #{t['hoy'].id} «Acceso a carpeta»")


def test_unknown_state_does_not_answer_the_total(client, tickets, fake_claude):
    headers, _ = tickets
    respuesta = _directa(client, headers, "cuantos tickets estan congelados")
    assert "en total" not in respuesta
    assert respuesta in NO_ENTENDI


@pytest.mark.parametrize(
    "pregunta, cuando, verbo, total",
    [
        ("cuantos tickets se cerraron hoy", "hoy", "se cerró", 1),
        ("cuantos pasaron a en proceso ayer", "ayer", "pasó a En proceso", 1),
        ("cuantos tickets hay hoy", "hoy", "se crearon", 2),
        ("cuantos tickets nuevos este mes", "este mes", "se crearon", 6),
        ("cuantos resueltos en los ultimos 7 dias", "en los últimos 7 días", "se resolvieron", 4),
        ("cuantos tickets se resolvieron ayer", "ayer", "se resolvió", 0),
    ],
)
def test_other_periods(client, tickets, fake_claude, pregunta, cuando, verbo, total):
    headers, _ = tickets
    respuesta = _directa(client, headers, pregunta)
    if total:
        assert es_forma(cabecera(respuesta), "periodo", cuando=cuando, verbo=verbo, n=negrita(total),
                        tickets="ticket" if total == 1 else "tickets"), respuesta
        assert len(lista(respuesta)) == total
    else:
        assert es_forma(respuesta, "periodo_cero", cuando=cuando, verbo=verbo, ticket="ticket"), respuesta


def test_plain_total_still_works(client, tickets, fake_claude):
    headers, _ = tickets
    respuesta = _directa(client, headers, "¿cuántos tickets hay en total?")
    assert es_forma(respuesta, "total", n=negrita(6), tickets="tickets que usted puede ver"), respuesta


@pytest.mark.parametrize(
    "pregunta",
    ["cuantos tickets de Hardware hay", "cuantos tickets de prioridad alta", "cuantos tickets criticos hubo esta semana"],
)
def test_category_priority_or_unsupported_period_go_to_ai(client, tickets, fake_claude, pregunta):
    headers, _ = tickets
    resp = ask(client, headers, pregunta)
    assert resp.json()["fuente"] == "ia"
    assert len(fake_claude.calls) == 1


def test_counting_resolved_with_a_ticket_on_screen_still_counts(client, tickets, fake_claude):
    headers, t = tickets
    respuesta = _directa(client, headers, "cuantos ticketes se han resolvido?", ticket_id=t["nuevo"].id)
    assert es_forma(cabecera(respuesta), "grupo_varios", n=negrita(4), frase="tickets resueltos o cerrados")


def test_requester_only_counts_own_tickets_in_a_period(client, session, tickets, fake_claude):
    _, t = tickets
    headers = login_as(client, session, "Solicitante", "sol@soli.local", "Andrea Castillo")
    andrea = session.query(User).filter_by(email="sol@soli.local").one()
    t["hoy"].created_by_id = andrea.id
    session.commit()
    semana = _directa(client, headers, "cuantos tickets se resolvieron esta semana")
    assert es_forma(cabecera(semana), "periodo", cuando="esta semana", verbo="se resolvió", n=negrita(1),
                    tickets="ticket suyo"), semana
    hoy = _directa(client, headers, "cuantos se cerraron hoy")
    assert es_forma(hoy, "periodo_cero", cuando="hoy", verbo="se cerró", ticket="ticket suyo"), hoy


@pytest.mark.parametrize(
    "pregunta, clave",
    [
        ("cuantos se resolvieron", "resueltos"),
        ("cuantos tickets arreglados hay", "resueltos"),
        ("cuantos fueron atendidos", "resueltos"),
        ("cuantos estan finalizados", "resueltos"),
        ("cuantos tickets terminados", "resueltos"),
        ("cuantos se terminaron", "resueltos"),
        ("cuantos estan cerrados", "cerrados"),
        ("cuantos hay pendientes", "pendientes"),
        ("tengo pendientes?", "mios"),
        ("en que estan trabajando?", "en_proceso"),
        ("cuantos estan atendiendo", "en_proceso"),
        ("cuantos tickets en curso", "en_proceso"),
        ("cuantos estan sin atender", "nuevos"),
        ("cuantos sin revisar hay", "nuevos"),
        ("cuantos tickets hay", "total"),
        ("cuantos tickets estan pausados", "no_entendi"),
        ("cuantos tickets tiene Fernanda", None),
        ("cuantos tickets tienen los tecnicos", None),
        ("cuanto tarda en resolverse un ticket", None),
    ],
)
def test_detect_more_ways_to_name_states(pregunta, clave):
    assert detectar_consulta(pregunta) == clave
