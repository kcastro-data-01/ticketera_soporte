"""Crea tickets a partir de los correos que llegan al buzón de soporte.

Cada ``CORREO_INTERVALO`` segundos (60 por defecto) un hilo en segundo plano
revisa el buzón por IMAP y, por cada correo nuevo:

* Si el remitente es un usuario activo de la ticketera, se crea un ticket a
  su nombre (asunto = título, cuerpo = descripción, categoría y prioridad
  según palabras clave) y se le responde con el número y el enlace.
  Si el asunto trae «Ticket #N» de un ticket suyo, se agrega como comentario.
* Si el remitente no tiene cuenta, se le responde que debe registrarse, con
  el enlace a la aplicación (una vez por día como máximo).
* Si su cuenta está desactivada, se le avisa.

Los correos automáticos (respuestas automáticas, rebotes, «noreply»...) se
ignoran para no crear bucles. Los correos se leen sin marcarlos como leídos
y se recuerda su ``Message-ID`` para no procesarlos dos veces. Solo se
procesan los que llegan después de activar la función.

Configuración (variables de entorno, ver README):
``CORREO_ACTIVO``, ``CORREO_USUARIO``, ``CORREO_CLAVE``,
``CORREO_IMAP_SERVIDOR``, ``CORREO_IMAP_PUERTO``, ``CORREO_SMTP_SERVIDOR``,
``CORREO_SMTP_PUERTO``, ``CORREO_CARPETA``, ``CORREO_INTERVALO``, ``APP_URL``
y, para Microsoft 365 con OAuth, ``CORREO_M365_TENANT``,
``CORREO_M365_CLIENT_ID`` y ``CORREO_M365_CLIENT_SECRET``.
"""

from __future__ import annotations

import imaplib
import logging
import os
import re
import smtplib
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email import message_from_bytes, policy
from email.message import EmailMessage
from email.utils import make_msgid, parseaddr, parsedate_to_datetime
from html import unescape

from sqlalchemy import func, select

from backend.constants import TicketCategory, TicketPriority
from backend.models import ProcessedEmail, Ticket, User
from backend.schemas import CommentCreate, TicketCreate
from backend.services import ticket_service

logger = logging.getLogger(__name__)

MAX_DESCRIPCION = 5000
MAX_TITULO = 200
TITULO_POR_DEFECTO = "Solicitud recibida por correo"
MARCA_INICIO = "__inicio__"
HORAS_ENTRE_AVISOS = 24

# Palabras clave → categoría / prioridad (se revisan en minúsculas, en el
# asunto y el cuerpo). Si nada coincide: Software y Media.
PALABRAS_CATEGORIA: list[tuple[TicketCategory, tuple[str, ...]]] = [
    (TicketCategory.ACCESS, ("contraseña", "clave", "acceso", "permiso", "usuario bloqueado",
                             "bloqueada", "bloqueado", "login", "iniciar sesión", "mi cuenta")),
    (TicketCategory.NETWORK, ("internet", "red", "wifi", "wi-fi", "vpn", "conexión",
                              "conectar", "cable de red", "router", "lento la red")),
    (TicketCategory.HARDWARE, ("impresora", "monitor", "pantalla", "teclado", "mouse",
                               "ratón", "computadora", "laptop", "portátil", "equipo",
                               "no enciende", "cargador", "disco", "batería")),
    (TicketCategory.SOFTWARE, ("programa", "aplicación", "sistema", "office", "excel",
                               "word", "outlook", "instalar", "actualizar", "licencia", "error")),
]
PALABRAS_PRIORIDAD: list[tuple[TicketPriority, tuple[str, ...]]] = [
    (TicketPriority.CRITICAL, ("urgente", "crítico", "critico", "caído", "caida", "caída",
                               "no funciona nada", "emergencia", "todos sin")),
    (TicketPriority.HIGH, ("importante", "lo antes posible", "asap", "prioridad alta",
                           "no puedo trabajar", "bloqueado")),
    (TicketPriority.LOW, ("cuando puedan", "no es urgente", "consulta", "pregunta",
                          "sin prisa")),
]

PATRON_TICKET = re.compile(r"ticket\s*#\s*(\d+)", re.IGNORECASE)
REMITENTES_AUTOMATICOS = ("noreply", "no-reply", "no_reply", "donotreply", "mailer-daemon",
                          "postmaster", "bounce")


@dataclass
class ConfigCorreo:
    """Datos para conectarse al buzón (se leen de variables de entorno)."""

    usuario: str
    clave: str = ""
    imap_servidor: str = "outlook.office365.com"
    imap_puerto: int = 993
    smtp_servidor: str = "smtp.office365.com"
    smtp_puerto: int = 587
    carpeta: str = "INBOX"
    # Solo se procesan los correos cuyo asunto contiene alguna de estas
    # palabras (vacío = todos). Los demás se dejan tal cual, sin responder.
    palabras_asunto: tuple[str, ...] = ("soporte", "ticket")
    intervalo: int = 60
    app_url: str = "http://localhost:8000"
    m365_tenant: str = ""
    m365_client_id: str = ""
    m365_client_secret: str = ""

    @property
    def usa_oauth(self) -> bool:
        return bool(self.m365_tenant and self.m365_client_id and self.m365_client_secret)


def _activo(valor: str | None) -> bool:
    return (valor or "").strip().lower() in ("1", "true", "si", "sí", "yes")


def config_desde_entorno(env=None) -> ConfigCorreo | None:
    """Configuración del buzón, o ``None`` si la función está apagada."""
    env = os.environ if env is None else env
    if not _activo(env.get("CORREO_ACTIVO")):
        return None
    usuario = (env.get("CORREO_USUARIO") or "").strip()
    if not usuario:
        logger.warning("CORREO_ACTIVO está encendido pero falta CORREO_USUARIO")
        return None
    return ConfigCorreo(
        usuario=usuario,
        clave=env.get("CORREO_CLAVE") or "",
        imap_servidor=env.get("CORREO_IMAP_SERVIDOR") or "outlook.office365.com",
        imap_puerto=int(env.get("CORREO_IMAP_PUERTO") or 993),
        smtp_servidor=env.get("CORREO_SMTP_SERVIDOR") or "smtp.office365.com",
        smtp_puerto=int(env.get("CORREO_SMTP_PUERTO") or 587),
        carpeta=env.get("CORREO_CARPETA") or "INBOX",
        palabras_asunto=tuple(
            p.strip().lower()
            for p in (env.get("CORREO_PALABRAS_ASUNTO", "soporte,ticket")).split(",")
            if p.strip()
        ),
        intervalo=max(15, int(env.get("CORREO_INTERVALO") or 60)),
        app_url=(env.get("APP_URL") or "http://localhost:8000").rstrip("/"),
        m365_tenant=env.get("CORREO_M365_TENANT") or "",
        m365_client_id=env.get("CORREO_M365_CLIENT_ID") or "",
        m365_client_secret=env.get("CORREO_M365_CLIENT_SECRET") or "",
    )


# --- Lectura del correo ---------------------------------------------------


@dataclass
class CorreoEntrante:
    """Lo que la ticketera necesita de un correo recibido."""

    message_id: str
    remitente: str
    nombre: str
    asunto: str
    cuerpo: str
    fecha: datetime | None
    automatico: bool


def _html_a_texto(html: str) -> str:
    texto = re.sub(r"(?is)<(script|style).*?</\1>", " ", html)
    texto = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>", "\n", texto)
    texto = re.sub(r"<[^>]+>", " ", texto)
    return unescape(texto)


def _limpiar_cuerpo(texto: str) -> str:
    """Quita el historial citado de respuestas y espacios de más."""
    lineas = []
    for linea in texto.replace("\r\n", "\n").split("\n"):
        # Lo que viene después de «El ... escribió:» / «De: ...» es el correo
        # anterior citado: no forma parte de la solicitud.
        if re.match(r"^\s*(el .+ escribió:|on .+ wrote:|de:\s.+|from:\s.+|-----\s*original)",
                    linea, re.IGNORECASE):
            break
        if linea.lstrip().startswith(">"):
            continue
        lineas.append(linea.rstrip())
    texto = "\n".join(lineas)
    texto = re.sub(r"[ \t]+", " ", texto)
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    return texto.strip()


def leer_correo(crudo: bytes) -> CorreoEntrante:
    """Convierte los bytes de un correo en un :class:`CorreoEntrante`."""
    msg = message_from_bytes(crudo, policy=policy.default)
    nombre, remitente = parseaddr(str(msg.get("From", "")))
    asunto = " ".join(str(msg.get("Subject", "")).split())

    cuerpo = ""
    # Texto plano primero; si viene vacío, la versión HTML.
    for tipo in ("plain", "html"):
        parte = msg.get_body(preferencelist=(tipo,))
        if parte is None:
            continue
        try:
            contenido = parte.get_content()
        except (LookupError, UnicodeDecodeError):
            contenido = parte.get_payload(decode=True).decode("utf-8", "replace")
        if tipo == "html":
            contenido = _html_a_texto(contenido)
        cuerpo = _limpiar_cuerpo(contenido)
        if cuerpo:
            break

    fecha = None
    if msg.get("Date"):
        try:
            fecha = parsedate_to_datetime(str(msg["Date"]))
            if fecha.tzinfo is None:
                fecha = fecha.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            fecha = None

    auto_submitted = str(msg.get("Auto-Submitted", "no")).strip().lower()
    precedencia = str(msg.get("Precedence", "")).strip().lower()
    automatico = (
        auto_submitted not in ("", "no")
        or precedencia in ("bulk", "junk", "list", "auto_reply")
        or msg.get("X-Autoreply") is not None
        or msg.get("X-Autorespond") is not None
        or any(p in remitente.lower() for p in REMITENTES_AUTOMATICOS)
    )

    message_id = str(msg.get("Message-ID", "")).strip()
    if not message_id:
        # Sin Message-ID: se arma uno estable con remitente, fecha y asunto.
        message_id = f"<sin-id:{remitente}:{msg.get('Date', '')}:{asunto}>"

    return CorreoEntrante(
        message_id=message_id[:500],
        remitente=remitente.strip().lower(),
        nombre=(nombre or "").strip(),
        asunto=asunto,
        cuerpo=cuerpo,
        fecha=fecha,
        automatico=automatico,
    )


# --- Clasificación ---------------------------------------------------------


def _buscar(texto: str, opciones):
    for valor, palabras in opciones:
        for palabra in palabras:
            if re.search(r"(?<!\w)" + re.escape(palabra) + r"(?!\w)", texto):
                return valor
    return None


def clasificar(asunto: str, cuerpo: str) -> tuple[TicketCategory, TicketPriority]:
    """Categoría y prioridad según palabras clave (asunto pesa más)."""
    asunto_l, cuerpo_l = asunto.lower(), cuerpo.lower()
    categoria = (_buscar(asunto_l, PALABRAS_CATEGORIA)
                 or _buscar(cuerpo_l, PALABRAS_CATEGORIA)
                 or TicketCategory.SOFTWARE)
    prioridad = (_buscar(asunto_l, PALABRAS_PRIORIDAD)
                 or _buscar(cuerpo_l, PALABRAS_PRIORIDAD)
                 or TicketPriority.MEDIUM)
    return categoria, prioridad


def _titulo(asunto: str) -> str:
    titulo = re.sub(r"^\s*((re|rv|fw|fwd)\s*:\s*)+", "", asunto, flags=re.IGNORECASE).strip()
    if len(titulo) < 3:
        return TITULO_POR_DEFECTO
    return titulo[:MAX_TITULO].strip()


# --- Respuestas ------------------------------------------------------------


@dataclass
class Respuesta:
    """Correo que la ticketera envía de vuelta al remitente."""

    para: str
    asunto: str
    texto: str
    en_respuesta_a: str | None = None


def _saludo(nombre: str) -> str:
    return f"Hola {nombre}," if nombre else "Hola,"


def _respuesta_ticket(correo, usuario, ticket, config) -> Respuesta:
    enlace = f"{config.app_url}/detalle.html?id={ticket.id}"
    return Respuesta(
        para=correo.remitente,
        asunto=f"Ticket #{ticket.id} creado: {ticket.title}",
        texto=(
            f"{_saludo(usuario.name)}\n\n"
            f"Recibimos tu solicitud y creamos el ticket #{ticket.id}.\n\n"
            f"Título: {ticket.title}\n"
            f"Categoría: {ticket.category}\n"
            f"Prioridad: {ticket.priority}\n"
            f"Estado: {ticket.state}\n\n"
            f"Puedes ver el avance aquí: {enlace}\n\n"
            f"Si quieres agregar información, responde a este correo sin cambiar "
            f"el asunto (debe mantener «Ticket #{ticket.id}»).\n\n"
            "Mesa de ayuda"
        ),
        en_respuesta_a=correo.message_id,
    )


def _respuesta_comentario(correo, usuario, ticket, config) -> Respuesta:
    enlace = f"{config.app_url}/detalle.html?id={ticket.id}"
    return Respuesta(
        para=correo.remitente,
        asunto=f"Comentario agregado al ticket #{ticket.id}",
        texto=(
            f"{_saludo(usuario.name)}\n\n"
            f"Agregamos tu mensaje como comentario del ticket #{ticket.id} "
            f"({ticket.title}).\n\nPuedes verlo aquí: {enlace}\n\nMesa de ayuda"
        ),
        en_respuesta_a=correo.message_id,
    )


def _respuesta_registro(correo, config) -> Respuesta:
    enlace = f"{config.app_url}/login.html?registro=1&email={correo.remitente}"
    return Respuesta(
        para=correo.remitente,
        asunto="Regístrate para crear tu ticket de soporte",
        texto=(
            f"{_saludo(correo.nombre)}\n\n"
            "Recibimos tu correo, pero todavía no tienes una cuenta en la "
            "ticketera de soporte, por eso no pudimos crear tu ticket.\n\n"
            f"Regístrate aquí con este mismo correo ({correo.remitente}):\n"
            f"{enlace}\n\n"
            "Cuando tengas tu cuenta, vuelve a enviarnos tu solicitud por "
            "correo o créala directamente en la aplicación.\n\n"
            "Mesa de ayuda"
        ),
        en_respuesta_a=correo.message_id,
    )


def _respuesta_inactivo(correo, usuario) -> Respuesta:
    return Respuesta(
        para=correo.remitente,
        asunto="No pudimos crear tu ticket",
        texto=(
            f"{_saludo(usuario.name)}\n\n"
            "Tu cuenta en la ticketera de soporte está desactivada, por eso no "
            "pudimos crear tu ticket. Comunícate con un administrador para "
            "reactivarla.\n\nMesa de ayuda"
        ),
        en_respuesta_a=correo.message_id,
    )


# --- Procesamiento ---------------------------------------------------------


def _registrar(session, correo, resultado, ticket_id=None) -> None:
    session.add(ProcessedEmail(
        message_id=correo.message_id,
        sender=correo.remitente or None,
        result=resultado,
        ticket_id=ticket_id,
    ))
    session.commit()


def _ya_avisado(session, remitente: str) -> bool:
    """¿Ya se le pidió registrarse a este remitente en las últimas 24 h?"""
    limite = datetime.now(timezone.utc) - timedelta(hours=HORAS_ENTRE_AVISOS)
    return session.scalar(
        select(func.count()).select_from(ProcessedEmail).where(
            ProcessedEmail.sender == remitente,
            ProcessedEmail.result == "registro",
            ProcessedEmail.created_at >= limite,
        )
    ) > 0


def es_de_soporte(asunto: str, config: ConfigCorreo) -> bool:
    """¿El asunto trae alguna de las palabras de soporte?"""
    if not config.palabras_asunto:
        return True
    asunto = asunto.lower()
    return any(palabra in asunto for palabra in config.palabras_asunto)


def criterio_busqueda(desde: str, config: ConfigCorreo) -> list[str]:
    """Criterio IMAP: desde la fecha y, si hay palabras, con ellas en el asunto.

    Así el servidor solo devuelve los correos de soporte y no se descargan
    los demás.
    """
    criterio = ["SINCE", desde]
    palabras = list(config.palabras_asunto)
    if palabras:
        asuntos = ["SUBJECT", f'"{palabras[-1]}"']
        for palabra in reversed(palabras[:-1]):
            asuntos = ["OR", "SUBJECT", f'"{palabra}"'] + asuntos
        criterio += asuntos
    return criterio


def procesar_correo(session, correo: CorreoEntrante, config: ConfigCorreo) -> tuple[str, Respuesta | None]:
    """Decide qué hacer con un correo; devuelve (resultado, respuesta a enviar).

    El correo queda registrado como procesado; la respuesta (si hay) la envía
    quien llama.
    """
    if session.scalar(select(ProcessedEmail.id).where(
            ProcessedEmail.message_id == correo.message_id)) is not None:
        return "repetido", None

    if not es_de_soporte(correo.asunto, config):
        # Correo normal de la empresa: no se toca ni se guarda.
        return "otro", None

    propio = correo.remitente == config.usuario.strip().lower()
    if correo.automatico or propio or "@" not in correo.remitente:
        _registrar(session, correo, "ignorado")
        return "ignorado", None

    usuario = session.scalar(select(User).where(func.lower(User.email) == correo.remitente))

    if usuario is None:
        if _ya_avisado(session, correo.remitente):
            _registrar(session, correo, "ignorado")
            return "ignorado", None
        _registrar(session, correo, "registro")
        return "registro", _respuesta_registro(correo, config)

    if not usuario.is_active:
        _registrar(session, correo, "inactivo")
        return "inactivo", _respuesta_inactivo(correo, usuario)

    # ¿Responde a un ticket suyo? → comentario en vez de ticket nuevo.
    coincidencia = PATRON_TICKET.search(correo.asunto)
    if coincidencia:
        ticket = session.get(Ticket, int(coincidencia.group(1)))
        if ticket is not None and ticket.created_by_id == usuario.id and correo.cuerpo:
            ticket_service.create_comment(
                session, ticket.id,
                CommentCreate(content=correo.cuerpo[:MAX_DESCRIPCION]), usuario,
            )
            _registrar(session, correo, "comentario", ticket.id)
            return "comentario", _respuesta_comentario(correo, usuario, ticket, config)

    categoria, prioridad = clasificar(correo.asunto, correo.cuerpo)
    descripcion = correo.cuerpo or "(El correo no traía texto.)"
    descripcion = descripcion[:MAX_DESCRIPCION] + f"\n\n— Recibido por correo de {correo.remitente}"
    ticket = ticket_service.create_ticket(
        session,
        TicketCreate(
            title=_titulo(correo.asunto),
            description=descripcion,
            category=categoria,
            priority=prioridad,
        ),
        usuario,
    )
    _registrar(session, correo, "ticket", ticket.id)
    return "ticket", _respuesta_ticket(correo, usuario, ticket, config)


def fecha_de_inicio(session) -> datetime:
    """Momento en que se activó la lectura del buzón (se crea la primera vez)."""
    marca = session.scalar(select(ProcessedEmail).where(ProcessedEmail.message_id == MARCA_INICIO))
    if marca is None:
        marca = ProcessedEmail(message_id=MARCA_INICIO, result="inicio")
        session.add(marca)
        session.commit()
        session.refresh(marca)
    inicio = marca.created_at
    return inicio if inicio.tzinfo else inicio.replace(tzinfo=timezone.utc)


# --- Conexión con el servidor ---------------------------------------------


def obtener_token_m365(config: ConfigCorreo) -> str:
    """Token OAuth (client credentials) para IMAP/SMTP de Microsoft 365."""
    import httpx

    resp = httpx.post(
        f"https://login.microsoftonline.com/{config.m365_tenant}/oauth2/v2.0/token",
        data={
            "grant_type": "client_credentials",
            "client_id": config.m365_client_id,
            "client_secret": config.m365_client_secret,
            "scope": "https://outlook.office365.com/.default",
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def _xoauth2(usuario: str, token: str) -> str:
    return f"user={usuario}\x01auth=Bearer {token}\x01\x01"


def conectar_imap(config: ConfigCorreo):
    imap = imaplib.IMAP4_SSL(config.imap_servidor, config.imap_puerto, timeout=60)
    if config.usa_oauth:
        token = obtener_token_m365(config)
        imap.authenticate("XOAUTH2", lambda _: _xoauth2(config.usuario, token).encode())
    else:
        imap.login(config.usuario, config.clave)
    return imap


def enviar_respuesta(config: ConfigCorreo, respuesta: Respuesta) -> None:
    """Envía la respuesta por SMTP (STARTTLS en 587, SSL en 465)."""
    msg = EmailMessage()
    msg["From"] = config.usuario
    msg["To"] = respuesta.para
    msg["Subject"] = respuesta.asunto
    msg["Message-ID"] = make_msgid(domain=config.usuario.split("@")[-1])
    # Marcan el correo como automático: evita respuestas automáticas en bucle.
    msg["Auto-Submitted"] = "auto-replied"
    msg["X-Auto-Response-Suppress"] = "All"
    if respuesta.en_respuesta_a:
        msg["In-Reply-To"] = respuesta.en_respuesta_a
        msg["References"] = respuesta.en_respuesta_a
    msg.set_content(respuesta.texto)

    if config.smtp_puerto == 465:
        smtp = smtplib.SMTP_SSL(config.smtp_servidor, config.smtp_puerto, timeout=60)
    else:
        smtp = smtplib.SMTP(config.smtp_servidor, config.smtp_puerto, timeout=60)
        smtp.starttls()
    try:
        if config.usa_oauth:
            token = obtener_token_m365(config)
            smtp.ehlo()
            smtp.auth("XOAUTH2", lambda challenge=None: _xoauth2(config.usuario, token),
                      initial_response_ok=True)
        else:
            smtp.login(config.usuario, config.clave)
        smtp.send_message(msg)
    finally:
        try:
            smtp.quit()
        except smtplib.SMTPException:
            pass


_MESES = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def revisar_buzon(session_factory, config: ConfigCorreo, conectar=conectar_imap,
                  enviar=enviar_respuesta) -> dict[str, int]:
    """Revisa el buzón una vez y procesa los correos nuevos.

    Devuelve cuántos correos terminaron en cada resultado.
    """
    conteo: dict[str, int] = {}
    with session_factory() as session:
        inicio = fecha_de_inicio(session)

    imap = conectar(config)
    try:
        estado, _ = imap.select(config.carpeta, readonly=True)
        if estado != "OK":
            raise RuntimeError(f"No se pudo abrir la carpeta {config.carpeta!r}")
        desde = f"{inicio.day:02d}-{_MESES[inicio.month - 1]}-{inicio.year}"
        estado, datos = imap.uid("SEARCH", None, *criterio_busqueda(desde, config))
        uids = (datos[0] or b"").split() if estado == "OK" else []
        for uid in uids:
            # BODY.PEEK: se lee sin marcar el correo como leído.
            estado, partes = imap.uid("FETCH", uid, "(BODY.PEEK[])")
            if estado != "OK":
                continue
            crudo = next((p[1] for p in partes if isinstance(p, tuple)), None)
            if not crudo:
                continue
            correo = leer_correo(crudo)
            if correo.fecha is not None and correo.fecha < inicio:
                continue  # Llegó antes de activar la función.
            with session_factory() as session:
                try:
                    resultado, respuesta = procesar_correo(session, correo, config)
                except Exception:
                    session.rollback()
                    logger.exception("No se pudo procesar el correo %s", correo.message_id)
                    continue
            conteo[resultado] = conteo.get(resultado, 0) + 1
            if respuesta is not None:
                try:
                    enviar(config, respuesta)
                except Exception:
                    logger.exception("No se pudo enviar la respuesta a %s", respuesta.para)
    finally:
        try:
            imap.logout()
        except Exception:
            pass
    return conteo


# --- Hilo en segundo plano -------------------------------------------------

_detener = threading.Event()
_hilo: threading.Thread | None = None


def _bucle(session_factory, config: ConfigCorreo) -> None:
    logger.info("Leyendo el buzón %s cada %s s", config.usuario, config.intervalo)
    while not _detener.is_set():
        try:
            conteo = revisar_buzon(session_factory, config)
            if any(k != "repetido" for k in conteo):
                logger.info("Correos procesados: %s", conteo)
        except Exception:
            logger.exception("Error al revisar el buzón %s", config.usuario)
        _detener.wait(config.intervalo)


def iniciar_lector(session_factory=None) -> bool:
    """Arranca el hilo que revisa el buzón si ``CORREO_ACTIVO`` está encendido."""
    global _hilo
    config = config_desde_entorno()
    if config is None or (_hilo is not None and _hilo.is_alive()):
        return False
    if session_factory is None:
        from backend.database import SessionLocal

        session_factory = SessionLocal
    _detener.clear()
    _hilo = threading.Thread(target=_bucle, args=(session_factory, config),
                             name="lector-correo", daemon=True)
    _hilo.start()
    return True


def detener_lector() -> None:
    _detener.set()
