"""Tests de la creación de tickets por correo (Graph simulado, sin correo real)."""

import json
from datetime import datetime, timedelta, timezone
from itertools import count

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from backend.models import Comment, ProcessedEmail, Ticket, User
from backend.services import correo_service as cs
from backend.services.correo_auth import SinSesionError

# Sin filtro para probar el procesamiento; la detección tiene sus pruebas.
CONFIG = cs.ConfigCorreo(usuario="kcastro@data.cr", app_url="http://ticketera.data.cr",
                         filtro="todos")
CONFIG_FILTRO = cs.ConfigCorreo(usuario="kcastro@data.cr", app_url="http://ticketera.data.cr")

_ids = count(1)


def crear_correo(remitente="ana@data.cr", nombre="Ana Pérez", asunto="La impresora no imprime",
                 cuerpo="Desde ayer la impresora del segundo piso no imprime.",
                 msg_id="<m1@data.cr>", fecha=None, cabeceras=None, html=False) -> dict:
    """Mensaje con la forma que devuelve Graph en /me/mailFolders/inbox/messages."""
    fecha = fecha or datetime.now(timezone.utc) + timedelta(minutes=1)
    return {
        "id": f"AAMk{next(_ids)}",
        "internetMessageId": msg_id,
        "subject": asunto,
        "from": {"emailAddress": {"name": nombre, "address": remitente}},
        "body": {"contentType": "html" if html else "text", "content": cuerpo},
        "receivedDateTime": fecha.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "internetMessageHeaders": [{"name": k, "value": v} for k, v in (cabeceras or {}).items()],
    }


@pytest.fixture
def usuario(session):
    user = User(name="Ana Pérez", email="Ana@data.cr", role="Solicitante",
                password_hash="x", is_active=True)
    session.add(user)
    session.commit()
    return user


def procesar(session, mensaje, config=CONFIG):
    return cs.procesar_correo(session, cs.correo_desde_graph(mensaje), config)


# --- Lógica de procesamiento ------------------------------------------------


def test_known_user_gets_a_ticket_and_a_reply(session, usuario):
    resultado, respuesta = procesar(session, crear_correo(asunto="URGENTE: la impresora no imprime"))
    assert resultado == "ticket"
    ticket = session.scalars(select(Ticket)).one()
    assert ticket.title == "URGENTE: la impresora no imprime"
    assert ticket.created_by_id == usuario.id
    assert ticket.category == "Hardware"
    assert ticket.priority == "Crítica"
    assert "segundo piso" in ticket.description
    assert "Recibido por correo de ana@data.cr" in ticket.description
    assert respuesta.para == "ana@data.cr"
    assert f"#{ticket.id}" in respuesta.asunto
    assert f"http://ticketera.data.cr/detalle.html?id={ticket.id}" in respuesta.texto


def test_unknown_sender_is_asked_to_register(session):
    resultado, respuesta = procesar(session, crear_correo(remitente="luis@otro.com", nombre="Luis"))
    assert resultado == "registro"
    assert session.scalars(select(Ticket)).first() is None
    assert respuesta.para == "luis@otro.com"
    assert "http://ticketera.data.cr/login.html?registro=1&email=luis@otro.com" in respuesta.texto
    assert "Hola Luis" in respuesta.texto

    # Un segundo correo el mismo día no vuelve a enviar el aviso.
    resultado, respuesta = procesar(session, crear_correo(remitente="luis@otro.com", msg_id="<m2@x>"))
    assert (resultado, respuesta) == ("ignorado", None)


def test_inactive_user_is_told_the_account_is_disabled(session, usuario):
    usuario.is_active = False
    session.commit()
    resultado, respuesta = procesar(session, crear_correo())
    assert resultado == "inactivo"
    assert "desactivada" in respuesta.texto
    assert session.scalars(select(Ticket)).first() is None


@pytest.mark.parametrize("cabeceras,remitente", [
    ({"Auto-Submitted": "auto-replied"}, "ana@data.cr"),
    ({"Precedence": "bulk"}, "ana@data.cr"),
    ({}, "MAILER-DAEMON@data.cr"),
    ({}, "noreply@servicio.com"),
    ({}, "kcastro@data.cr"),
    ({}, "KCastro@Data.cr"),
])
def test_automatic_or_own_mail_is_ignored(session, usuario, cabeceras, remitente):
    resultado, respuesta = procesar(session, crear_correo(remitente=remitente, cabeceras=cabeceras))
    assert (resultado, respuesta) == ("ignorado", None)
    assert session.scalars(select(Ticket)).first() is None


def test_same_message_is_processed_only_once(session, usuario):
    mensaje = crear_correo()
    assert procesar(session, mensaje)[0] == "ticket"
    assert procesar(session, mensaje) == ("repetido", None)
    assert len(session.scalars(select(Ticket)).all()) == 1


def test_reply_with_ticket_number_adds_a_comment(session, usuario):
    procesar(session, crear_correo())
    ticket = session.scalars(select(Ticket)).one()
    mensaje = crear_correo(asunto=f"RE: Ticket #{ticket.id} creado: La impresora",
                           cuerpo="Ya probé reiniciarla.\n\n________________________________\n"
                                  "De: Mesa de ayuda\nTexto viejo",
                           msg_id="<m3@data.cr>")
    resultado, respuesta = procesar(session, mensaje)
    assert resultado == "comentario"
    comentario = session.scalars(select(Comment)).one()
    assert comentario.content == "Ya probé reiniciarla."
    assert comentario.author == "Ana Pérez"
    assert len(session.scalars(select(Ticket)).all()) == 1
    assert f"#{ticket.id}" in respuesta.asunto


def test_reply_to_someone_elses_ticket_creates_a_new_one(session, usuario):
    otro = Ticket(title="Ajeno", description="x", category="Red", priority="Baja")
    session.add(otro)
    session.commit()
    resultado, _ = procesar(session, crear_correo(asunto=f"Ticket #{otro.id} ayuda"))
    assert resultado == "ticket"
    assert len(session.scalars(select(Ticket)).all()) == 2


def test_short_subject_and_html_body(session, usuario):
    mensaje = crear_correo(asunto="Re:", cuerpo="<p>No tengo <b>internet</b></p><br>gracias",
                           html=True)
    procesar(session, mensaje)
    ticket = session.scalars(select(Ticket)).one()
    assert ticket.title == cs.TITULO_POR_DEFECTO
    assert ticket.category == "Red"
    assert ticket.priority == "Media"
    assert "<p>" not in ticket.description


def test_message_without_internet_message_id_uses_graph_id():
    mensaje = crear_correo()
    mensaje["internetMessageId"] = None
    assert cs.correo_desde_graph(mensaje).message_id == f"<graph:{mensaje['id']}>"


@pytest.mark.parametrize("asunto,cuerpo,categoria,prioridad", [
    ("Olvidé mi contraseña", "", "Accesos", "Media"),
    ("Consulta", "¿Cómo instalo Excel?", "Software", "Baja"),
    ("VPN no conecta", "no puedo trabajar", "Red", "Alta"),
    ("Hola", "algo raro", "Software", "Media"),
])
def test_classification(asunto, cuerpo, categoria, prioridad):
    cat, pri = cs.clasificar(asunto, cuerpo)
    assert (cat.value, pri.value) == (categoria, prioridad)


@pytest.mark.parametrize("asunto,cuerpo", [
    ("Se dañó una impresora, ocupo arreglo urgente", "La impresora no enciende"),
    ("Ayuda", "hola"),
    ("Hola", "Desde hoy la computadora no prende"),
    ("Consulta", "No puedo entrar al sistema de planillas"),
    ("Outlook", "me sale un error al enviar"),
    ("Olvidé mi contraseña", ""),
    ("Sin internet", "En el segundo piso estamos sin conexión"),
    ("Soporte", ""),
])
def test_help_requests_are_detected(asunto, cuerpo):
    assert cs.es_de_soporte(asunto, cuerpo, CONFIG_FILTRO)


@pytest.mark.parametrize("asunto,cuerpo", [
    ("Reunión del viernes", "Les recuerdo la reunión a las 10 am."),
    ("Factura de octubre", "Adjunto la factura del mes."),
    ("Cumpleaños", "Mañana celebramos el cumpleaños de Ana en la sala."),
    ("Propuesta comercial", "Le envío la propuesta para su revisión."),
])
def test_normal_company_mail_is_not_a_ticket(session, usuario, asunto, cuerpo):
    assert not cs.es_de_soporte(asunto, cuerpo, CONFIG_FILTRO)
    resultado, respuesta = procesar(session, crear_correo(asunto=asunto, cuerpo=cuerpo), CONFIG_FILTRO)
    assert (resultado, respuesta) == ("otro", None)
    assert session.scalars(select(Ticket)).first() is None
    assert session.scalars(select(ProcessedEmail)).first() is None


def test_unknown_sender_asking_for_help_gets_the_register_mail(session):
    mensaje = crear_correo(remitente="kristin@gmail.com", nombre="Kristin",
                           asunto="Se dañó una impresora, ocupo arreglo urgente",
                           cuerpo="La impresora no enciende y la necesito para el trabajo")
    resultado, respuesta = procesar(session, mensaje, CONFIG_FILTRO)
    assert resultado == "registro"
    assert "login.html?registro=1&email=kristin@gmail.com" in respuesta.texto


def test_non_support_mail_from_unknown_sender_gets_no_reply(session):
    mensaje = crear_correo(remitente="cliente@otro.com", asunto="Cotización",
                           cuerpo="Adjunto la cotización solicitada.")
    assert procesar(session, mensaje, CONFIG_FILTRO) == ("otro", None)


# --- Configuración ------------------------------------------------------------


def test_config_from_env(tmp_path):
    assert cs.config_desde_entorno({}) is None
    assert cs.config_desde_entorno({"CORREO_ACTIVO": "1"}) is None
    cfg = cs.config_desde_entorno({
        "CORREO_ACTIVO": "si", "CORREO_USUARIO": "kcastro@data.cr",
        "APP_URL": "http://10.0.0.5:8000/", "CORREO_M365_TENANT": "t", "CORREO_M365_CLIENT_ID": "c",
        "CORREO_M365_CACHE": str(tmp_path / "cache.json"),
    })
    assert cfg.usuario == "kcastro@data.cr"
    assert cfg.app_url == "http://10.0.0.5:8000"
    assert (cfg.m365_tenant, cfg.m365_client_id) == ("t", "c")
    assert cfg.cache_path == tmp_path / "cache.json"
    assert cfg.carpeta_procesados == "Tickets-Procesados"
    assert cfg.filtro == "auto"


def test_filter_from_env():
    base = {"CORREO_ACTIVO": "1", "CORREO_USUARIO": "kcastro@data.cr"}
    assert cs.config_desde_entorno({**base, "CORREO_FILTRO": "Todos"}).filtro == "todos"
    cfg = cs.config_desde_entorno({**base, "CORREO_CARPETA_PROCESADOS": "Soporte-Hecho"})
    assert cfg.carpeta_procesados == "Soporte-Hecho"


# --- Graph simulado -------------------------------------------------------------


class FakeGraph:
    """Simula los endpoints de Graph que usa la ticketera."""

    def __init__(self, mensajes, carpetas=None, rechazar_cabecera=False, paginas=1):
        self.mensajes = {m["id"]: dict(m, isRead=False, carpeta="inbox") for m in mensajes}
        self.carpetas = dict(carpetas or {})  # nombre -> id
        self.respuestas = []  # (id, json enviado)
        self.llamadas = []
        self.rechazar_cabecera = rechazar_cabecera
        self.paginas = paginas
        self.cliente = cs.ClienteGraph(FakeToken(),
                                       httpx.Client(transport=httpx.MockTransport(self.manejar)))

    def no_leidos(self):
        return [m for m in self.mensajes.values() if not m["isRead"] and m["carpeta"] == "inbox"]

    def manejar(self, request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer token-falso"
        ruta = request.url.path.removeprefix("/v1.0")
        cuerpo = json.loads(request.content) if request.content else None
        self.llamadas.append((request.method, ruta))

        if request.method == "GET" and ruta == "/me/mailFolders/inbox/messages":
            assert request.url.params.get("$filter", "isRead eq false") == "isRead eq false"
            assert request.headers["Prefer"] == 'outlook.body-content-type="text"'
            pendientes = self.no_leidos()
            pagina = int(request.url.params.get("pagina", "0"))
            tam = max(1, -(-len(pendientes) // self.paginas))
            datos = {"value": pendientes[pagina * tam:(pagina + 1) * tam]}
            if pagina + 1 < self.paginas:
                datos["@odata.nextLink"] = (f"{cs.GRAPH_URL}/me/mailFolders/inbox/messages"
                                            f"?pagina={pagina + 1}")
            return httpx.Response(200, json=datos)
        if request.method == "GET" and ruta == "/me/mailFolders":
            nombre = request.url.params["$filter"].split("'")[1]
            valor = [{"id": self.carpetas[nombre]}] if nombre in self.carpetas else []
            return httpx.Response(200, json={"value": valor})
        if request.method == "POST" and ruta == "/me/mailFolders":
            self.carpetas[cuerpo["displayName"]] = f"carpeta-{len(self.carpetas) + 1}"
            return httpx.Response(201, json={"id": self.carpetas[cuerpo["displayName"]]})

        partes = ruta.split("/")  # ['', 'me', 'messages', id, accion?]
        mensaje = self.mensajes.get(partes[3]) if len(partes) > 3 else None
        if mensaje is None:
            return httpx.Response(404, json={"error": {"message": "no existe"}})
        if request.method == "PATCH" and len(partes) == 4:
            mensaje["isRead"] = cuerpo["isRead"]
            return httpx.Response(200, json={})
        if request.method == "POST" and partes[4] == "move":
            mensaje["carpeta"] = cuerpo["destinationId"]
            # Como en Graph, al mover el correo cambia de id.
            nuevo = mensaje["id"] + "-movido"
            self.mensajes[nuevo] = dict(self.mensajes.pop(mensaje["id"]), id=nuevo)
            return httpx.Response(201, json={"id": nuevo})
        if request.method == "POST" and partes[4] == "reply":
            if self.rechazar_cabecera and "internetMessageHeaders" in cuerpo["message"]:
                return httpx.Response(400, json={"error": {"message": "header no permitido"}})
            self.respuestas.append((mensaje["id"], cuerpo))
            return httpx.Response(202)
        return httpx.Response(400, json={"error": {"message": f"no simulado: {ruta}"}})


class FakeToken:
    def __init__(self, error=None):
        self.error = error

    def obtener(self):
        if self.error:
            raise SinSesionError(self.error)
        return "token-falso"


@pytest.fixture
def factory(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)


def test_revisar_buzon_replies_in_thread_marks_read_and_moves(factory, session, usuario):
    viejo = crear_correo(msg_id="<viejo@x>", fecha=datetime.now(timezone.utc) - timedelta(days=2))
    nuevo = crear_correo(msg_id="<nuevo@x>")
    desconocido = crear_correo(remitente="otro@x.com", msg_id="<otro@x>")
    graph = FakeGraph([viejo, nuevo, desconocido])

    conteo = cs.revisar_buzon(factory, CONFIG, graph.cliente)
    assert conteo == {"ticket": 1, "registro": 1}

    # Respuestas en el mismo hilo, con la cabecera anti respuestas automáticas.
    assert [r[0] for r in graph.respuestas] == [nuevo["id"], desconocido["id"]]
    enviado = graph.respuestas[0][1]["message"]
    assert enviado["subject"].startswith("Ticket #")
    assert enviado["body"]["contentType"] == "Text"
    assert enviado["internetMessageHeaders"] == [{"name": "X-Auto-Response-Suppress", "value": "All"}]
    # Se respondió antes de mover (después el id cambia).
    assert graph.llamadas.index(("POST", f"/me/messages/{nuevo['id']}/reply")) < \
        graph.llamadas.index(("POST", f"/me/messages/{nuevo['id']}/move"))

    # Procesados: leídos y en la carpeta, que se creó porque no existía.
    carpeta = graph.carpetas["Tickets-Procesados"]
    movidos = [m for m in graph.mensajes.values() if m["carpeta"] == carpeta]
    assert sorted(m["internetMessageId"] for m in movidos) == ["<nuevo@x>", "<otro@x>"]
    assert all(m["isRead"] for m in movidos)
    # El que llegó antes de activar la función no se toca.
    assert [m["internetMessageId"] for m in graph.no_leidos()] == ["<viejo@x>"]

    # Segunda revisión: nada nuevo, no se repite ninguna respuesta.
    assert cs.revisar_buzon(factory, CONFIG, graph.cliente) == {}
    assert len(graph.respuestas) == 2
    assert session.scalar(select(ProcessedEmail).where(
        ProcessedEmail.message_id == cs.MARCA_INICIO)) is not None


def test_mail_that_does_not_ask_for_help_is_left_untouched(factory, usuario):
    reunion = crear_correo(asunto="Reunión del viernes", cuerpo="Nos vemos a las 10.")
    graph = FakeGraph([reunion])
    assert cs.revisar_buzon(factory, CONFIG_FILTRO, graph.cliente) == {"otro": 1}
    assert graph.respuestas == []
    assert graph.no_leidos()[0]["id"] == reunion["id"]  # sigue sin leer, en la bandeja
    assert not any(m in ("PATCH", "POST") for m, _ in graph.llamadas)


def test_existing_folder_is_reused(factory, usuario):
    graph = FakeGraph([crear_correo()], carpetas={"Tickets-Procesados": "ya-existe"})
    cs.revisar_buzon(factory, CONFIG, graph.cliente)
    assert ("POST", "/me/mailFolders") not in graph.llamadas
    assert list(graph.mensajes.values())[0]["carpeta"] == "ya-existe"


def test_already_processed_mail_still_in_inbox_is_moved_without_replying(factory, session, usuario):
    mensaje = crear_correo()
    procesar(session, mensaje)  # procesado antes, pero no se pudo mover
    graph = FakeGraph([mensaje])
    assert cs.revisar_buzon(factory, CONFIG, graph.cliente) == {"repetido": 1}
    assert graph.respuestas == []
    assert graph.no_leidos() == []


def test_unread_messages_are_read_from_every_page(factory, usuario):
    mensajes = [crear_correo(msg_id=f"<p{i}@x>") for i in range(4)]
    graph = FakeGraph(mensajes, paginas=2)
    assert len(graph.cliente.no_leidos()) == 4


def test_reply_falls_back_without_header_if_graph_rejects_it(factory, usuario):
    graph = FakeGraph([crear_correo()], rechazar_cabecera=True)
    assert cs.revisar_buzon(factory, CONFIG, graph.cliente) == {"ticket": 1}
    assert len(graph.respuestas) == 1
    assert "internetMessageHeaders" not in graph.respuestas[0][1]["message"]


def test_reply_failure_does_not_stop_processing(factory, usuario):
    graph = FakeGraph([crear_correo(msg_id="<a@x>"), crear_correo(msg_id="<b@x>")])

    def falla(*args):
        raise cs.ErrorGraph("POST → 500: caído")

    graph.cliente.responder = falla
    assert cs.revisar_buzon(factory, CONFIG, graph.cliente) == {"ticket": 2}
    assert graph.no_leidos() == []  # igual se marcan y se mueven


def test_missing_session_is_raised_without_touching_mail(factory, usuario):
    graph = FakeGraph([crear_correo()])
    graph.cliente._token = FakeToken(error="no existe la caché de tokens")
    with pytest.raises(SinSesionError):
        cs.revisar_buzon(factory, CONFIG, graph.cliente)
    assert len(graph.no_leidos()) == 1


def test_expired_token_401_is_a_session_error(usuario):
    cliente = cs.ClienteGraph(FakeToken(), httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(401, json={}))))
    with pytest.raises(SinSesionError):
        cliente.no_leidos()


def test_loop_logs_session_error_and_keeps_running(factory, caplog, monkeypatch):
    graph = FakeGraph([])
    graph.cliente._token = FakeToken(error="la sesión venció")
    vueltas = []

    def esperar(segundos):
        vueltas.append(segundos)
        if len(vueltas) == 2:
            cs._detener.set()
        return cs._detener.is_set()

    monkeypatch.setattr(cs._detener, "wait", esperar)
    monkeypatch.setattr(cs.logger, "propagate", True)
    cs._detener.clear()
    with caplog.at_level("ERROR", logger=cs.logger.name):
        cs._bucle(factory, CONFIG, graph.cliente)  # no lanza
    cs._detener.clear()
    assert len(vueltas) == 2
    assert "correo_login" in caplog.text


# --- Remitentes registrados y no registrados (de punta a punta) ---------------


@pytest.fixture
def log_correo(caplog, monkeypatch):
    monkeypatch.setattr(cs.logger, "propagate", True)
    caplog.set_level("INFO", logger=cs.logger.name)
    return caplog


def test_registered_sender_creates_ticket_as_requester_and_gets_confirmation(factory, session, usuario):
    mensaje = crear_correo(remitente="ANA@DATA.CR")  # sin distinguir mayúsculas
    graph = FakeGraph([mensaje])
    assert cs.revisar_buzon(factory, CONFIG, graph.cliente) == {"ticket": 1}

    ticket = session.scalars(select(Ticket)).one()
    assert ticket.created_by_id == usuario.id
    assert session.get(User, ticket.created_by_id).role == "Solicitante"
    [(respondido, enviado)] = graph.respuestas
    assert respondido == mensaje["id"]  # en el mismo hilo
    assert enviado["message"]["subject"] == f"Ticket #{ticket.id} creado: {ticket.title}"
    assert f"/detalle.html?id={ticket.id}" in enviado["message"]["body"]["content"]
    assert graph.no_leidos() == []


def test_unregistered_sender_gets_register_notice_and_no_ticket(factory, session, log_correo):
    mensaje = crear_correo(remitente="Luis@Otro.com", nombre="Luis")
    graph = FakeGraph([mensaje])
    assert cs.revisar_buzon(factory, CONFIG, graph.cliente) == {"registro": 1}

    assert session.scalars(select(Ticket)).first() is None
    [(respondido, enviado)] = graph.respuestas
    assert respondido == mensaje["id"]
    assert enviado["message"]["subject"] == "Registrate para crear tickets"
    texto = enviado["message"]["body"]["content"]
    assert "http://ticketera.data.cr/login.html?registro=1&email=luis@otro.com" in texto
    assert "vuelve a enviarnos tu solicitud" in texto
    # Igual queda procesado: leído y en la carpeta.
    assert graph.no_leidos() == []
    assert "Correo ignorado: remitente no registrado luis@otro.com" in log_correo.text


def test_second_mail_from_unregistered_within_24h_gets_no_notice(factory, session, log_correo):
    graph = FakeGraph([crear_correo(remitente="luis@otro.com", msg_id="<1@x>")])
    cs.revisar_buzon(factory, CONFIG, graph.cliente)
    assert len(graph.respuestas) == 1

    graph.mensajes.update({m["id"]: dict(m, isRead=False, carpeta="inbox") for m in
                           [crear_correo(remitente="luis@otro.com", msg_id="<2@x>")]})
    log_correo.clear()
    assert cs.revisar_buzon(factory, CONFIG, graph.cliente) == {"ignorado": 1}
    assert len(graph.respuestas) == 1  # no hubo otro aviso
    assert graph.no_leidos() == []  # pero se movió igual
    assert session.scalars(select(Ticket)).first() is None
    assert "Correo ignorado: remitente no registrado luis@otro.com" in log_correo.text


def test_unregistered_gets_a_new_notice_after_24h(session):
    procesar(session, crear_correo(remitente="luis@otro.com", msg_id="<1@x>"))
    aviso = session.scalars(select(ProcessedEmail).where(ProcessedEmail.result == "registro")).one()
    aviso.created_at = datetime.now(timezone.utc) - timedelta(hours=25)
    session.commit()
    resultado, respuesta = procesar(session, crear_correo(remitente="luis@otro.com", msg_id="<2@x>"))
    assert resultado == "registro"
    assert respuesta.asunto == "Registrate para crear tickets"


def test_not_a_help_request_is_logged_once(factory, usuario, log_correo):
    graph = FakeGraph([crear_correo(asunto="Reunión del viernes", cuerpo="Nos vemos a las 10.")])
    avisados = set()
    cs.revisar_buzon(factory, CONFIG_FILTRO, graph.cliente, avisados)
    cs.revisar_buzon(factory, CONFIG_FILTRO, graph.cliente, avisados)
    assert log_correo.text.count("Correo ignorado: no parece solicitud de ayuda «Reunión del viernes»") == 1



# --- Avisos de la propia app y texto citado -------------------------------------


@pytest.mark.parametrize("prefijo", ["RE: ", "RV: ", "FW: ", "Fwd: ", "Re: RE: ", "RE[2]: ", ""])
def test_reply_to_register_notice_never_creates_a_ticket(session, usuario, prefijo, log_correo):
    """El caso del ticket #6: el aviso de registro vuelve desde un usuario registrado."""
    mensaje = crear_correo(asunto=f"{prefijo}Registrate para crear tickets",
                           cuerpo="Ya me registré, no funciona la impresora, ayuda")
    assert procesar(session, mensaje, CONFIG_FILTRO) == ("ignorado", None)
    assert session.scalars(select(Ticket)).first() is None
    assert "es una respuesta a un aviso de la app" in log_correo.text


def test_reply_to_inactive_notice_is_ignored(session, usuario):
    mensaje = crear_correo(asunto="RE: No pudimos crear tu ticket", cuerpo="no funciona")
    assert procesar(session, mensaje, CONFIG_FILTRO) == ("ignorado", None)
    assert session.scalars(select(Ticket)).first() is None


def test_ticket_6_case_end_to_end(factory, session, usuario):
    graph = FakeGraph([crear_correo(asunto="RE: Registrate para crear tickets",
                                    cuerpo="Hola\n\nEl lun, 19 oct 2026 a las 10:00, Mesa de ayuda "
                                           "<kcastro@data.cr>\nescribió:\n> Registrate para crear tickets")])
    assert cs.revisar_buzon(factory, CONFIG_FILTRO, graph.cliente) == {"ignorado": 1}
    assert session.scalars(select(Ticket)).first() is None
    assert graph.respuestas == []
    assert graph.no_leidos() == []  # se marca y se mueve igual


def test_owner_reply_to_confirmation_adds_comment_without_keywords(session, usuario):
    procesar(session, crear_correo())
    ticket = session.scalars(select(Ticket)).one()
    mensaje = crear_correo(asunto=f"RE: Ticket #{ticket.id} creado: {ticket.title}",
                           cuerpo="Ya funciona, gracias", msg_id="<r1@x>")
    resultado, respuesta = procesar(session, mensaje, CONFIG_FILTRO)
    assert resultado == "comentario"
    assert session.scalars(select(Comment)).one().content == "Ya funciona, gracias"
    assert len(session.scalars(select(Ticket)).all()) == 1


def test_reply_to_comment_notice_adds_another_comment(session, usuario):
    procesar(session, crear_correo())
    ticket = session.scalars(select(Ticket)).one()
    mensaje = crear_correo(asunto=f"RE: Comentario agregado al ticket #{ticket.id}",
                           cuerpo="Otra cosa: también falla el escáner", msg_id="<r2@x>")
    assert procesar(session, mensaje, CONFIG_FILTRO)[0] == "comentario"


def test_non_owner_reply_to_confirmation_creates_nothing(session, usuario):
    otra = User(name="Otra", email="otra@data.cr", role="Solicitante", password_hash="x")
    session.add(otra)
    session.commit()
    procesar(session, crear_correo())
    ticket = session.scalars(select(Ticket)).one()
    mensaje = crear_correo(remitente="otra@data.cr", msg_id="<r3@x>",
                           asunto=f"FW: Ticket #{ticket.id} creado: {ticket.title}",
                           cuerpo="La impresora no funciona tampoco en mi piso")
    assert procesar(session, mensaje, CONFIG_FILTRO) == ("ignorado", None)
    assert len(session.scalars(select(Ticket)).all()) == 1
    assert session.scalars(select(Comment)).first() is None


def test_unregistered_reply_to_confirmation_gets_no_notice(session):
    mensaje = crear_correo(remitente="x@otro.com", asunto="RE: Ticket #3 creado: algo",
                           cuerpo="no funciona")
    assert procesar(session, mensaje, CONFIG_FILTRO) == ("ignorado", None)


def test_keywords_in_quoted_text_do_not_count(session, usuario):
    # Graph manda uniqueBody (solo lo nuevo) aparte del cuerpo completo.
    mensaje = crear_correo(asunto="Viernes", cuerpo="Perfecto, nos vemos.\n\nDe: Ana\n"
                                                    "La impresora no funciona, ayuda")
    mensaje["uniqueBody"] = {"contentType": "text", "content": "Perfecto, nos vemos."}
    assert procesar(session, mensaje, CONFIG_FILTRO) == ("otro", None)


@pytest.mark.parametrize("cita", [
    "El lun, 19 oct 2026 a las 10:00, Ana Pérez (<ana@data.cr>)\nescribió:\n> no funciona nada",
    "On Mon, Oct 19, 2026 at 10:00 AM Ana <ana@data.cr> wrote:\n> no funciona",
    "---------- Forwarded message ---------\nDe: Ana\nLa impresora no funciona",
    "-----Mensaje original-----\nNo puedo entrar al VPN",
    "________________________________\nFrom: Ana\nerror en el sistema",
    "> no funciona la impresora\n> ayuda",
])
def test_quoted_or_forwarded_text_is_cut(session, usuario, cita):
    mensaje = crear_correo(asunto="Hola", cuerpo=f"Gracias por todo.\n\n{cita}")
    assert cs.correo_desde_graph(mensaje).cuerpo == "Gracias por todo."
    assert procesar(session, mensaje, CONFIG_FILTRO) == ("otro", None)


@pytest.mark.parametrize("asunto,cuerpo", [
    ("Necesito tickets para el concierto", "¿Alguien tiene tickets?"),
    ("Tickets de avión", "Adjunto los tickets del viaje."),
])
def test_ticket_word_alone_is_not_a_help_request(asunto, cuerpo):
    assert not cs.es_de_soporte(asunto, cuerpo, CONFIG_FILTRO)


def test_asunto_base_strips_reply_prefixes():
    assert cs.asunto_base("RE: RV: Fwd: Registrate para crear tickets") == "Registrate para crear tickets"
    assert cs.asunto_base("Re[3]: hola") == "hola"
    assert cs.asunto_base("Reunión") == "Reunión"
