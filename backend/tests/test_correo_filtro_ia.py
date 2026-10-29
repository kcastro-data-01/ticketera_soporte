"""Filtro del correo con IA (``CORREO_FILTRO=ia``), con la IA simulada: nunca
se llama a Groq ni a Ollama.

* Reglas fijas primero: automáticos, avisos de ticketeras, boletines, más de
  tres destinatarios y otros dominios se ignoran sin preguntarle a la IA.
* «Ticket:» crea siempre; una respuesta en el hilo de un ticket es comentario.
* El resto lo decide la IA; si falla, el respaldo estricto (y queda en el log).
"""

import json

import pytest
from sqlalchemy import select

from backend.models import Comment, ProcessedEmail, Ticket, User
from backend.services import correo_filtro as cf
from backend.services import correo_service as cs
from backend.services.asistente_service import AsistenteNoDisponible, AsistenteOcupado
from backend.tests.test_correo import (FakeGraph, crear_correo, factory, log_correo,  # noqa: F401
                                       procesar, usuario)
from backend.tests.test_correo_enviados import crear_enviado

CONFIG_IA = cs.ConfigCorreo(usuario="kcastro@data.cr", app_url="http://ticketera.data.cr",
                            filtro="ia", dominio_empresa="data.cr")

# Un resumen que no trae las frases fijas de los avisos: lo decide la IA.
RESUMEN_LIBRE = ("Hola, te cuento cómo va nuestra ticketera: esta semana cerramos 12 tickets; "
                 "quedan #1 la impresora no imprime y #4 la VPN no conecta.")
RESUMEN = ("Buen día.\n\nLe compartimos el resumen de la Ticketera de Soporte del 28/10/2026.\n\n"
           "Tickets críticos abiertos: 4\n - #1 | La impresora no imprime | Crítico\n"
           " - #4 | Caída de Red | Crítico\n - #9 | Se dañó el monitor | Alto")


class IAFalsa:
    """Responde según el asunto; anota lo que recibe."""

    nombre = "falsa"

    def __init__(self, solicitudes=(), error=None, texto=None):
        self.solicitudes = set(solicitudes)
        self.error = error
        self.texto = texto
        self.pedidos: list[list[dict]] = []

    def generar_json(self, messages, esquema, temperature=0.1, timeout=None, num_ctx=None):
        self.pedidos.append(messages)
        if self.error is not None:
            raise self.error
        if self.texto is not None:
            return self.texto
        asunto = messages[-1]["content"].split("\n", 1)[0].removeprefix("Asunto: ")
        es = asunto in self.solicitudes
        return json.dumps({"es_solicitud": es, "motivo": "pide ayuda" if es else "no pide ayuda"})


@pytest.fixture
def ia(monkeypatch):
    cf.reiniciar()
    falsa = IAFalsa(solicitudes={"Se dañó mi computadora", "No puedo entrar al sistema",
                                 "Consulta"})
    monkeypatch.setattr(cf, "_crear_proveedor", lambda: falsa)
    yield falsa
    cf.reiniciar()


def tickets(session):
    return session.scalars(select(Ticket)).all()


# --- Los casos pedidos ----------------------------------------------------------


def test_ticketera_summary_is_ignored(session, usuario, ia):
    """Un compañero manda el resumen de SU ticketera (la IA dice que no)."""
    mensaje = crear_correo(asunto="Novedades de nuestra ticketera", cuerpo=RESUMEN_LIBRE)
    assert procesar(session, mensaje, CONFIG_IA) == ("otro", None)
    assert tickets(session) == []
    assert len(ia.pedidos) == 1


def test_real_summary_from_the_incident_is_ignored_without_asking_the_ai(session, usuario, ia):
    """Los 9 correos de ayer: «[Ticketera] Resumen del día» con el resumen."""
    for n in range(9):
        mensaje = crear_correo(asunto="[Ticketera] Resumen del día 28/10/2026", cuerpo=RESUMEN,
                               msg_id=f"<resumen{n}@data.cr>")
        assert procesar(session, mensaje, CONFIG_IA) == ("otro", None)
    aviso = crear_correo(asunto="No pudimos crear su ticket", msg_id="<aviso@data.cr>", cuerpo=(
        "Recibimos su correo, pero esta dirección no está registrada como cliente en la Ticketera "
        "de Soporte.\n\nAgente virtual — Ticketera de Soporte"))
    assert procesar(session, aviso, CONFIG_IA) == ("otro", None)
    assert tickets(session) == []
    assert ia.pedidos == []


@pytest.mark.parametrize("asunto,cuerpo", [
    ("Se dañó mi computadora", "Desde esta mañana no enciende."),
    ("No puedo entrar al sistema", "Me dice que la clave es incorrecta."),
])
def test_help_requests_create_a_ticket(session, usuario, ia, asunto, cuerpo):
    resultado, respuesta = procesar(session, crear_correo(asunto=asunto, cuerpo=cuerpo), CONFIG_IA)
    assert resultado == "ticket"
    assert tickets(session)[0].title == asunto
    assert respuesta.asunto.startswith(f"Ticket #{tickets(session)[0].id} creado")


def test_thank_you_is_ignored(session, usuario, ia):
    mensaje = crear_correo(asunto="Gracias por la ayuda", cuerpo="Ya quedó funcionando, saludos.")
    assert procesar(session, mensaje, CONFIG_IA) == ("otro", None)
    assert tickets(session) == []


@pytest.mark.parametrize("asunto,cabeceras", [
    ("Respuesta automática: Fuera de la oficina", {}),
    ("Fuera de la oficina", {"Auto-Submitted": "auto-replied"}),
    ("Se dañó mi computadora", {"Auto-Submitted": "auto-replied"}),
    ("Automatic reply: Se dañó mi computadora", {}),
    ("Undeliverable: Se dañó mi computadora", {}),
])
def test_automatic_replies_are_ignored(session, usuario, ia, asunto, cabeceras):
    mensaje = crear_correo(asunto=asunto, cuerpo="Estaré fuera hasta el lunes.", cabeceras=cabeceras)
    assert procesar(session, mensaje, CONFIG_IA) == ("otro", None)
    assert tickets(session) == []
    assert ia.pedidos == []


def test_ticket_prefix_always_creates_without_asking_the_ai(session, usuario, ia):
    mensaje = crear_correo(asunto="Ticket: algo", cuerpo="Gracias")
    assert procesar(session, mensaje, CONFIG_IA)[0] == "ticket"
    assert tickets(session)[0].title == "algo"
    assert ia.pedidos == []


def test_reply_in_thread_is_a_comment(session, usuario, ia):
    primero = crear_correo(asunto="Se dañó mi computadora", cuerpo="No enciende.",
                           msg_id="<pedido@data.cr>")
    assert procesar(session, primero, CONFIG_IA)[0] == "ticket"
    ticket = tickets(session)[0]
    respuesta = crear_correo(asunto="RE: Se dañó mi computadora", cuerpo="Gracias, ya prendió.",
                             msg_id="<resp@data.cr>")
    respuesta["internetMessageHeaders"] = [{"name": "In-Reply-To", "value": "<pedido@data.cr>"}]
    assert procesar(session, respuesta, CONFIG_IA)[0] == "comentario"
    assert session.scalars(select(Comment)).one().content == "Gracias, ya prendió."
    assert len(ia.pedidos) == 1  # solo el primero


def test_ticket_number_in_subject_is_a_comment(session, usuario, ia):
    procesar(session, crear_correo(asunto="Ticket: impresora"), CONFIG_IA)
    ticket = tickets(session)[0]
    mensaje = crear_correo(asunto=f"RE: [Ticket #{ticket.id}] Nuevo comentario", cuerpo="Sigue igual",
                           msg_id="<n@data.cr>")
    assert procesar(session, mensaje, CONFIG_IA)[0] == "comentario"


def test_ai_down_uses_the_strict_fallback_and_logs_it(session, usuario, ia, log_correo):
    ia.error = AsistenteNoDisponible("No se pudo conectar con Groq")
    pedido = crear_correo(asunto="Se dañó mi computadora", cuerpo="No enciende.", msg_id="<a@x>")
    assert procesar(session, pedido, CONFIG_IA)[0] == "ticket"
    resumen = crear_correo(asunto="Novedades", cuerpo=RESUMEN_LIBRE, msg_id="<b@x>")
    assert procesar(session, resumen, CONFIG_IA) == ("otro", None)
    assert "se usó el filtro de respaldo" in log_correo.text
    # Lo que el respaldo descartó no se anota: se vuelve a probar con la IA.
    assert session.scalar(select(ProcessedEmail).where(ProcessedEmail.message_id == "<b@x>")) is None
    # Tras la falla la IA queda en pausa: el segundo correo no la llamó.
    assert len(ia.pedidos) == 1


def test_rate_limit_429_uses_the_fallback(session, usuario, ia, log_correo):
    ia.error = AsistenteOcupado("La IA está ocupada, intente de nuevo en un minuto")
    mensaje = crear_correo(asunto="Consulta", cuerpo="No puedo entrar al sistema de planillas.")
    assert procesar(session, mensaje, CONFIG_IA)[0] == "ticket"
    assert "respaldo" in log_correo.text and "AsistenteOcupado" in log_correo.text


def test_invalid_json_uses_the_fallback(session, usuario, ia):
    ia.texto = "no es json"
    mensaje = crear_correo(asunto="Hola", cuerpo="Gracias por todo.")
    assert procesar(session, mensaje, CONFIG_IA) == ("otro", None)


# --- Más reglas ------------------------------------------------------------------


def _con_destinatarios(mensaje, para, cc=()):
    mensaje["toRecipients"] = [{"emailAddress": {"address": c}} for c in para]
    mensaje["ccRecipients"] = [{"emailAddress": {"address": c}} for c in cc]
    return mensaje


def test_more_than_three_recipients_is_ignored(session, usuario, ia):
    mensaje = _con_destinatarios(crear_correo(asunto="Se dañó mi computadora"),
                                 ["kcastro@data.cr", "b@data.cr"], ["c@data.cr", "d@data.cr"])
    assert procesar(session, mensaje, CONFIG_IA) == ("otro", None)
    assert ia.pedidos == []
    tres = _con_destinatarios(crear_correo(asunto="Se dañó mi computadora", msg_id="<3@x>"),
                              ["kcastro@data.cr", "b@data.cr"], ["c@data.cr"])
    assert procesar(session, tres, CONFIG_IA)[0] == "ticket"


def test_other_domain_is_ignored_even_with_an_account(session, ia):
    session.add(User(name="Ext", email="ext@otro.com", role="Solicitante", password_hash="x"))
    session.commit()
    mensaje = crear_correo(remitente="ext@otro.com", asunto="Se dañó mi computadora")
    assert procesar(session, mensaje, CONFIG_IA) == ("otro", None)
    assert ia.pedidos == []


@pytest.mark.parametrize("cabeceras", [{"List-Unsubscribe": "<mailto:baja@x.com>"},
                                       {"Precedence": "bulk"}, {"X-Zendesk-From-Account-Id": "1"}])
def test_newsletters_and_other_ticketeras_are_ignored(session, usuario, ia, cabeceras):
    mensaje = crear_correo(asunto="Se dañó mi computadora", cabeceras=cabeceras)
    assert procesar(session, mensaje, CONFIG_IA) == ("otro", None)
    assert ia.pedidos == []


def test_no_account_gets_the_notice_only_for_a_request(session, ia):
    pedido = crear_correo(remitente="luis@data.cr", asunto="Se dañó mi computadora", msg_id="<l1@x>")
    resultado, respuesta = procesar(session, pedido, CONFIG_IA)
    assert resultado == "sin_cuenta" and respuesta.asunto == cs.ASUNTO_SIN_CUENTA
    gracias = crear_correo(remitente="luis@data.cr", asunto="Gracias", msg_id="<l2@x>")
    assert procesar(session, gracias, CONFIG_IA) == ("otro", None)


def test_rejected_mail_is_not_classified_again(session, usuario, ia):
    mensaje = crear_correo(asunto="Gracias por la ayuda", cuerpo="Saludos.")
    assert procesar(session, mensaje, CONFIG_IA) == ("otro", None)
    assert procesar(session, mensaje, CONFIG_IA) == ("visto", None)
    assert len(ia.pedidos) == 1
    # Se anota sin la conversación: no cuenta como hilo ya procesado.
    fila = session.scalars(select(ProcessedEmail)).one()
    assert (fila.result, fila.conversation_id) == (cs.NO_SOLICITUD, None)


def test_ai_gets_only_subject_and_first_800_chars_with_examples(session, usuario, ia):
    cuerpo = "No enciende. " + "x" * 2000
    procesar(session, crear_correo(asunto="Se dañó mi computadora", cuerpo=cuerpo), CONFIG_IA)
    mensajes = ia.pedidos[0]
    assert mensajes[0]["role"] == "system"
    assert mensajes[-1]["content"] == f"Asunto: Se dañó mi computadora\n\n{cuerpo[:800]}"
    respuestas = [json.loads(m["content"]) for m in mensajes if m["role"] == "assistant"]
    assert {r["es_solicitud"] for r in respuestas} == {True, False}


def test_log_has_the_decision_but_not_the_body(session, usuario, ia, log_correo):
    procesar(session, crear_correo(asunto="Se dañó mi computadora", cuerpo="secreto-123 no enciende"),
             CONFIG_IA)
    procesar(session, crear_correo(asunto="Gracias", cuerpo="secreto-456", msg_id="<g@x>"), CONFIG_IA)
    assert "Correo aceptado (ia: pide ayuda)" in log_correo.text
    assert "Correo ignorado (ia: no pide ayuda)" in log_correo.text
    assert "secreto" not in log_correo.text


def test_end_to_end_keeps_the_brake_and_leaves_rejected_mail_unread(factory, session, usuario, ia):
    pedidos = [crear_correo(asunto="Se dañó mi computadora", msg_id=f"<p{n}@x>") for n in range(7)]
    gracias = crear_correo(asunto="Gracias", msg_id="<g@x>")
    graph = FakeGraph([*pedidos, gracias])
    conteo = cs.revisar_buzon(factory, CONFIG_IA, graph.cliente)
    assert conteo == {"ticket": 5, "frenado": 2, "otro": 1}
    assert len(tickets(session)) == 5
    # El «Gracias» sigue sin leer y no se vuelve a clasificar.
    assert cs.revisar_buzon(factory, CONFIG_IA, graph.cliente) == {"ticket": 2, "visto": 1}
    assert {m["internetMessageId"] for m in graph.no_leidos()} == {"<g@x>"}
    assert sum(m[-1]["content"].startswith("Asunto: Gracias") for m in ia.pedidos) == 1


# --- Enviados: solo «Ticket:» crea; las reglas fijas también -----------------------


def _enviado(asunto, msg_id="<e1@data.cr>", cabeceras=None):
    return cs.correo_desde_graph(crear_enviado(asunto=asunto, cuerpo="Hola", msg_id=msg_id,
                                               cabeceras=cabeceras))


def test_sent_mail_only_creates_with_ticket_prefix(session, ia):
    assert cs.procesar_enviado(session, _enviado("Se dañó mi computadora"), CONFIG_IA)[0] == "otro"
    assert cs.procesar_enviado(session, _enviado("Ticket: impresora", msg_id="<e2@x>"),
                               CONFIG_IA)[0] == "ticket"
    assert ia.pedidos == []


def test_sent_automatic_mail_is_ignored_even_with_prefix(session, ia):
    correo = _enviado("Ticket: algo", cabeceras={"Auto-Submitted": "auto-generated"})
    assert cs.procesar_enviado(session, correo, CONFIG_IA) == ("ignorado", None)
    assert tickets(session) == []


# --- Respaldo estricto y configuración ------------------------------------------------


@pytest.mark.parametrize("asunto,cuerpo", [
    ("Se dañó mi computadora", ""),
    ("No puedo entrar al sistema", ""),
    ("Hola", "La impresora no imprime desde ayer"),
    ("Outlook", "me sale un error al enviar"),
    ("Clave", "Olvidé mi contraseña"),
    ("Acceso", "Necesito acceso a la carpeta de Ventas"),
    ("Red", "Estamos sin internet en el segundo piso"),
])
def test_strict_fallback_accepts_real_problems(asunto, cuerpo):
    assert cf.es_solicitud_estricta(asunto, cuerpo)[0]


@pytest.mark.parametrize("asunto,cuerpo", [
    ("Ticket", "Le comparto el estado del ticket y su prioridad."),
    ("Ticketera de soporte", "Les presento el proyecto de la ticketera de soporte."),
    ("Soporte", ""),
    ("Gracias por la ayuda", "Saludos"),
    ("Resumen semanal", "La impresora no imprime (#3) y la VPN no conecta (#5)."),
    ("Reunión", "Nos vemos el viernes"),
])
def test_strict_fallback_rejects_everything_else(asunto, cuerpo):
    assert not cf.es_solicitud_estricta(asunto, cuerpo)[0]


def test_filter_default_depends_on_ai():
    assert cs.filtro_desde_entorno({}, ia_disponible=True) == "ia"
    assert cs.filtro_desde_entorno({}, ia_disponible=False) == "auto"
    for valor in ("ia", "auto", "todos"):
        assert cs.filtro_desde_entorno({"CORREO_FILTRO": valor.upper()}, ia_disponible=False) == valor


def test_filter_default_reads_the_assistant_provider(monkeypatch):
    monkeypatch.setenv("ASISTENTE_PROVEEDOR", "groq")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    assert cs.filtro_desde_entorno({}) == "auto"
    monkeypatch.setenv("GROQ_API_KEY", "clave")
    assert cs.filtro_desde_entorno({}) == "ia"
    monkeypatch.setenv("ASISTENTE_PROVEEDOR", "ninguno")
    assert cs.filtro_desde_entorno({}) == "auto"
