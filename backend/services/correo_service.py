"""Crea tickets a partir de los correos que llegan al buzón de soporte.

Cada ``CORREO_INTERVALO`` segundos (60 por defecto) un hilo en segundo plano
revisa los correos **no leídos** de la bandeja de entrada con Microsoft Graph
y, por cada correo nuevo que pide ayuda:

* Si el remitente es un usuario activo de la ticketera, se crea un ticket a
  su nombre (asunto = título, cuerpo = descripción, categoría y prioridad
  según palabras clave) y se le responde con el número y el enlace.
  Si el asunto trae «Ticket #N» de un ticket suyo, se agrega como comentario.
* Si el remitente no tiene cuenta y es del dominio de la empresa
  (``DOMINIO_EMPRESA``), se crea como Solicitante y se crea el ticket igual.
  Si es de otro dominio, el correo se ignora y queda en el log.
* Si su cuenta está desactivada, se le avisa.

Las respuestas se envían en el mismo hilo (``/reply``). Cada correo
procesado se marca como leído y se mueve a la carpeta
``CORREO_CARPETA_PROCESADOS``. Los que no piden ayuda se dejan sin tocar.
Los correos automáticos (respuestas automáticas, rebotes, «noreply»...) se
ignoran para no crear bucles, y se recuerda el ``Message-ID`` de cada correo
para no procesarlo dos veces. Solo se procesan los que llegan después de
activar la función.

El inicio de sesión (msal, device code) está en ``correo_auth``; la primera
vez se ejecuta ``python -m backend.correo_login``.

Configuración (variables de entorno, ver README): ``CORREO_ACTIVO``,
``CORREO_USUARIO``, ``CORREO_M365_TENANT``, ``CORREO_M365_CLIENT_ID``,
``CORREO_M365_CACHE``, ``CORREO_CARPETA_PROCESADOS``, ``CORREO_FILTRO``,
``CORREO_INTERVALO``, ``DOMINIO_EMPRESA`` y ``APP_URL``.
"""

from __future__ import annotations

import logging
import os
import re
import threading
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html import unescape
from pathlib import Path

import httpx
from sqlalchemy import func, select

from backend.constants import TicketCategory, TicketPriority
from backend.models import ProcessedEmail, Ticket, User
from backend.schemas import CommentCreate, TicketCreate
from backend.services import ticket_service
from backend.services.correo_auth import ProveedorToken, SinSesionError, ruta_cache
from backend.services.login_microsoft import asignar_rol_inicial

logger = logging.getLogger(__name__)
# Los mensajes salen en «docker compose logs ticketera» (uvicorn no muestra
# los INFO de la aplicación por su cuenta).
if not logger.handlers:
    _salida = logging.StreamHandler()
    _salida.setFormatter(logging.Formatter("CORREO: %(message)s"))
    logger.addHandler(_salida)
    logger.setLevel(logging.INFO)
    logger.propagate = False

MAX_DESCRIPCION = 5000
MAX_TITULO = 200
TITULO_POR_DEFECTO = "Solicitud recibida por correo"
MARCA_INICIO = "__inicio__"
GRAPH_URL = "https://graph.microsoft.com/v1.0"
CARPETA_PROCESADOS = "Tickets-Procesados"
MAX_PAGINAS = 10  # hasta 500 no leídos por revisión (50 por página)

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

# Frases que indican una solicitud de ayuda (en minúsculas y sin tildes).
# Se buscan en el asunto y el texto del correo.
SEÑALES_SOPORTE: tuple[str, ...] = (
    # «ticket» no está: aparece en los propios correos de la app.
    r"\bsoporte\b", r"\bayuda\b", r"\bayudar(me|nos)?\b",
    r"\bno (me |nos |le )?(funciona|sirve|enciende|prende|arranca|abre|carga|imprime|"
    r"conecta|deja|responde|aparece|llega|reconoce|suena)",
    r"\bno (puedo|podemos|logro) (entrar|ingresar|abrir|imprimir|conectar|acceder|enviar|"
    r"iniciar|trabajar|instalar|usar|ver)",
    r"\bse (me |nos |le )?(dano|danaron|quebro|cayo|cayeron|trabo|pego|congelo|apago|reinicia|"
    r"desconecta|bloqueo)",
    r"\bdanad[oa]s?\b", r"\bfall(a|o|ando)\b", r"\berror(es)?\b", r"\bproblemas? con\b",
    r"\barregl", r"\brepar", r"\bimpresora", r"\bcontrasena", r"\bclave\b",
    r"\bbloquead", r"\binternet\b", r"\bwi-?fi\b", r"\bvpn\b", r"\bsin (red|conexion|internet|sistema)",
    r"\blent[oa] (la|el|mi)", r"\bcomputadora\b", r"\blaptop\b", r"\bmonitor\b",
    r"\bteclado\b", r"\bmouse\b", r"\binstalar\b", r"\blicencia\b", r"\bacceso\b",
)

PATRON_TICKET = re.compile(r"ticket\s*#\s*(\d+)", re.IGNORECASE)
# «RE:», «RV:», «FW:», «Fwd:», «RE[2]:»… (también repetidos) al inicio del asunto.
PREFIJOS_RESPUESTA = re.compile(r"^\s*((re|rv|fw|fwd|aw|tr|reenviar)\s*(\[\d+\])?\s*:\s*)+", re.IGNORECASE)
ASUNTO_INACTIVO = "No pudimos crear tu ticket"
# Asuntos que envía la app. Los avisos nunca se procesan; las confirmaciones
# solo sirven para agregar un comentario al ticket de quien responde.
# «Registrate para crear tickets» ya no se envía, pero quedan avisos viejos en
# los buzones: sus respuestas tampoco son solicitudes.
AVISOS_APP = (re.compile(r"^registrate para crear tickets$", re.IGNORECASE),
              re.compile(r"^no pudimos crear tu ticket$", re.IGNORECASE))
CONFIRMACIONES_APP = (re.compile(r"^ticket\s*#\d+ creado:", re.IGNORECASE),
                      re.compile(r"^comentario agregado al ticket\s*#\d+$", re.IGNORECASE))
REMITENTES_AUTOMATICOS = ("noreply", "no-reply", "no_reply", "donotreply", "mailer-daemon",
                          "postmaster", "bounce")


@dataclass
class ConfigCorreo:
    """Datos del buzón (se leen de variables de entorno)."""

    usuario: str
    m365_tenant: str = ""
    m365_client_id: str = ""
    cache_path: Path = field(default_factory=ruta_cache)
    carpeta_procesados: str = CARPETA_PROCESADOS
    # «auto»: solo los correos que parecen una solicitud de ayuda (ver
    # SEÑALES_SOPORTE); «todos»: cada correo es un ticket (buzón exclusivo
    # de soporte). Los demás se dejan tal cual, sin guardar ni responder.
    filtro: str = "auto"
    intervalo: int = 60
    app_url: str = "http://localhost:8000"
    # Los remitentes de este dominio sin cuenta se crean como Solicitante;
    # los de otros dominios se ignoran.
    dominio_empresa: str = ""


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
        m365_tenant=(env.get("CORREO_M365_TENANT") or "").strip(),
        m365_client_id=(env.get("CORREO_M365_CLIENT_ID") or "").strip(),
        cache_path=ruta_cache(env.get("CORREO_M365_CACHE")),
        carpeta_procesados=(env.get("CORREO_CARPETA_PROCESADOS") or CARPETA_PROCESADOS).strip(),
        filtro="todos" if (env.get("CORREO_FILTRO") or "").strip().lower() == "todos" else "auto",
        intervalo=max(15, int(env.get("CORREO_INTERVALO") or 60)),
        app_url=(env.get("APP_URL") or "http://localhost:8000").rstrip("/"),
        dominio_empresa=(env.get("DOMINIO_EMPRESA") or "").strip().lower().lstrip("@"),
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


# Dónde empieza el correo anterior citado o reenviado: desde ahí no es parte
# de la solicitud. «El lun, 19 oct … escribió:» puede venir en dos líneas.
CORTES_CITA = (
    r"^\s*(el|on)\b[^\n]{0,200}(\n[^\n]{0,200})?\b(escribió|escribio|wrote):\s*$",
    r"^\s*(de|from):\s.+",
    r"^\s*-{3,}\s*(original message|mensaje original|forwarded message|mensaje reenviado)",
    r"^\s*(begin forwarded message|inicio del mensaje reenviado)",
    r"^\s*_{10,}",
)


def _limpiar_cuerpo(texto: str) -> str:
    """Quita el historial citado/reenviado y espacios de más."""
    texto = texto.replace("\r\n", "\n")
    cortes = [m.start() for patron in CORTES_CITA
              if (m := re.search(patron, texto, re.IGNORECASE | re.MULTILINE))]
    if cortes:
        texto = texto[:min(cortes)]
    lineas = [linea.rstrip() for linea in texto.split("\n") if not linea.lstrip().startswith(">")]
    texto = "\n".join(lineas)
    texto = re.sub(r"[ \t]+", " ", texto)
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    return texto.strip()


def asunto_base(asunto: str) -> str:
    """El asunto sin «RE:», «RV:», «FW:», «Fwd:»…"""
    return PREFIJOS_RESPUESTA.sub("", asunto).strip()


def _texto_graph(parte: dict | None) -> str:
    parte = parte or {}
    contenido = parte.get("content") or ""
    if (parte.get("contentType") or "").lower() == "html":
        contenido = _html_a_texto(contenido)
    return _limpiar_cuerpo(contenido)


def _es_automatico(cabeceras: dict[str, str], remitente: str) -> bool:
    """¿Es una respuesta automática, un rebote o un envío masivo?"""
    auto_submitted = cabeceras.get("auto-submitted", "no").strip().lower()
    precedencia = cabeceras.get("precedence", "").strip().lower()
    return (
        auto_submitted not in ("", "no")
        or precedencia in ("bulk", "junk", "list", "auto_reply")
        or "x-autoreply" in cabeceras
        or "x-autorespond" in cabeceras
        or any(p in remitente for p in REMITENTES_AUTOMATICOS)
    )


def _fecha_iso(valor: str | None) -> datetime | None:
    if not valor:
        return None
    try:
        fecha = datetime.fromisoformat(valor.replace("Z", "+00:00"))
    except ValueError:
        return None
    return fecha if fecha.tzinfo else fecha.replace(tzinfo=timezone.utc)


def correo_desde_graph(mensaje: dict) -> CorreoEntrante:
    """Convierte un mensaje de Graph (``/me/messages``) en un :class:`CorreoEntrante`."""
    direccion = ((mensaje.get("from") or {}).get("emailAddress") or {})
    remitente = (direccion.get("address") or "").strip().lower()
    asunto = " ".join((mensaje.get("subject") or "").split())

    # uniqueBody es solo lo nuevo de este correo (sin lo citado de antes).
    cuerpo = _texto_graph(mensaje.get("uniqueBody")) or _texto_graph(mensaje.get("body"))

    cabeceras = {
        (c.get("name") or "").lower(): c.get("value") or ""
        for c in mensaje.get("internetMessageHeaders") or []
    }
    message_id = (mensaje.get("internetMessageId") or "").strip() or f"<graph:{mensaje.get('id')}>"

    return CorreoEntrante(
        message_id=message_id[:500],
        remitente=remitente,
        nombre=(direccion.get("name") or "").strip(),
        asunto=asunto,
        cuerpo=cuerpo,
        fecha=_fecha_iso(mensaje.get("receivedDateTime")),
        automatico=_es_automatico(cabeceras, remitente),
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
    titulo = asunto_base(asunto)
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
    )


def _respuesta_inactivo(correo, usuario) -> Respuesta:
    return Respuesta(
        para=correo.remitente,
        asunto=ASUNTO_INACTIVO,
        texto=(
            f"{_saludo(usuario.name)}\n\n"
            "Tu cuenta en la ticketera de soporte está desactivada, por eso no "
            "pudimos crear tu ticket. Comunícate con un administrador para "
            "reactivarla.\n\nMesa de ayuda"
        ),
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


def es_de_la_empresa(remitente: str, config: ConfigCorreo) -> bool:
    """¿El remitente es del dominio de la empresa (``DOMINIO_EMPRESA``)?"""
    return bool(config.dominio_empresa) and remitente.rsplit("@", 1)[-1] == config.dominio_empresa


def _crear_solicitante(session, correo: CorreoEntrante) -> User:
    """Remitente interno sin cuenta: se crea con su nombre del correo (o lo
    que va antes de @) y el rol de ``asignar_rol_inicial``."""
    nombre = (correo.nombre or "").strip() or correo.remitente.split("@")[0]
    usuario = User(name=nombre[:120], email=correo.remitente,
                   role=asignar_rol_inicial(correo.remitente).value)
    session.add(usuario)
    session.commit()
    session.refresh(usuario)
    logger.info("Usuario creado desde el correo: %s (%s)", correo.remitente, usuario.role)
    return usuario


def _sin_tildes(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()


def es_de_soporte(asunto: str, cuerpo: str, config: ConfigCorreo) -> bool:
    """¿El correo parece una solicitud de ayuda? (asunto y texto, sin tildes)."""
    if config.filtro == "todos":
        return True
    texto = _sin_tildes(f"{asunto}\n{cuerpo}".lower())
    return any(re.search(senal, texto) for senal in SEÑALES_SOPORTE)


def procesar_correo(session, correo: CorreoEntrante, config: ConfigCorreo) -> tuple[str, Respuesta | None]:
    """Decide qué hacer con un correo; devuelve (resultado, respuesta a enviar).

    El correo queda registrado como procesado; la respuesta (si hay) la envía
    quien llama.
    """
    if session.scalar(select(ProcessedEmail.id).where(
            ProcessedEmail.message_id == correo.message_id)) is not None:
        return "repetido", None

    base = asunto_base(correo.asunto)
    es_aviso = any(p.search(base) for p in AVISOS_APP)
    es_confirmacion = any(p.search(base) for p in CONFIRMACIONES_APP)
    numero = PATRON_TICKET.search(correo.asunto)
    if not (es_aviso or numero or es_de_soporte(correo.asunto, correo.cuerpo, config)):
        # Correo normal de la empresa: no se toca ni se guarda.
        return "otro", None

    propio = correo.remitente == config.usuario.strip().lower()
    if correo.automatico or propio or "@" not in correo.remitente:
        _registrar(session, correo, "ignorado")
        return "ignorado", None

    if es_aviso:
        # Respuesta o reenvío de un aviso de la app: nunca es una solicitud.
        logger.info("Correo ignorado: es una respuesta a un aviso de la app «%s»", correo.asunto)
        _registrar(session, correo, "ignorado")
        return "ignorado", None

    usuario = session.scalar(select(User).where(func.lower(User.email) == correo.remitente))

    if usuario is None:
        if es_confirmacion:
            logger.info("Correo ignorado: respuesta a una confirmación de un remitente no "
                        "registrado %s", correo.remitente)
            _registrar(session, correo, "ignorado")
            return "ignorado", None
        if not es_de_la_empresa(correo.remitente, config):
            logger.info("Correo ignorado: remitente externo sin cuenta %s", correo.remitente)
            _registrar(session, correo, "ignorado")
            return "ignorado", None
        usuario = _crear_solicitante(session, correo)

    if not usuario.is_active:
        _registrar(session, correo, "inactivo")
        return "inactivo", _respuesta_inactivo(correo, usuario)

    # ¿Responde a un ticket suyo? → comentario en vez de ticket nuevo.
    if numero:
        ticket = session.get(Ticket, int(numero.group(1)))
        if ticket is not None and ticket.created_by_id == usuario.id and correo.cuerpo:
            ticket_service.create_comment(
                session, ticket.id,
                CommentCreate(content=correo.cuerpo[:MAX_DESCRIPCION]), usuario,
            )
            _registrar(session, correo, "comentario", ticket.id)
            return "comentario", _respuesta_comentario(correo, usuario, ticket, config)

    if es_confirmacion or not es_de_soporte(correo.asunto, correo.cuerpo, config):
        # Responde a una confirmación de un ticket ajeno (o sin texto nuevo), o
        # nombra un ticket sin pedir ayuda: nunca crea un ticket nuevo.
        logger.info("Correo ignorado: «%s» de %s no es un comentario válido ni una solicitud nueva",
                    correo.asunto, correo.remitente)
        _registrar(session, correo, "ignorado")
        return "ignorado", None

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


# --- Microsoft Graph -------------------------------------------------------


class ErrorGraph(Exception):
    """Graph respondió con un error."""


class ClienteGraph:
    """Lo mínimo de Microsoft Graph que usa la ticketera (permisos delegados)."""

    def __init__(self, token: ProveedorToken, http: httpx.Client | None = None):
        self._token = token
        self._http = http or httpx.Client(timeout=60)
        self._carpetas: dict[str, str] = {}

    def _pedir(self, metodo: str, url: str, **kwargs) -> dict:
        if not url.startswith("http"):
            url = GRAPH_URL + url
        cabeceras = kwargs.pop("headers", {})
        cabeceras["Authorization"] = f"Bearer {self._token.obtener()}"
        resp = self._http.request(metodo, url, headers=cabeceras, **kwargs)
        if resp.status_code == 401:
            raise SinSesionError("Graph rechazó el token (401)")
        if resp.status_code >= 400:
            try:
                detalle = resp.json().get("error", {}).get("message", resp.text)
            except ValueError:
                detalle = resp.text
            raise ErrorGraph(f"{metodo} {url} → {resp.status_code}: {detalle}")
        return resp.json() if resp.content else {}

    def no_leidos(self) -> list[dict]:
        """Correos no leídos de la bandeja de entrada (todas las páginas)."""
        mensajes: list[dict] = []
        url = "/me/mailFolders/inbox/messages"
        params = {
            "$filter": "isRead eq false",
            "$top": "50",
            "$select": "id,internetMessageId,subject,from,body,uniqueBody,receivedDateTime,"
                       "internetMessageHeaders",
        }
        for _ in range(MAX_PAGINAS):
            datos = self._pedir("GET", url, params=params,
                                headers={"Prefer": 'outlook.body-content-type="text"'})
            mensajes.extend(datos.get("value", []))
            url = datos.get("@odata.nextLink")
            if not url:
                break
            params = None  # el nextLink ya trae los parámetros
        return mensajes

    def id_carpeta(self, nombre: str) -> str:
        """Id de la carpeta (en la raíz del buzón); la crea si no existe."""
        if nombre in self._carpetas:
            return self._carpetas[nombre]
        filtro = "displayName eq '{}'".format(nombre.replace("'", "''"))
        datos = self._pedir("GET", "/me/mailFolders", params={"$filter": filtro})
        if datos.get("value"):
            carpeta_id = datos["value"][0]["id"]
        else:
            carpeta_id = self._pedir("POST", "/me/mailFolders", json={"displayName": nombre})["id"]
            logger.info("se creó la carpeta «%s» en el buzón", nombre)
        self._carpetas[nombre] = carpeta_id
        return carpeta_id

    def marcar_y_mover(self, mensaje_id: str, carpeta_id: str) -> None:
        self._pedir("PATCH", f"/me/messages/{mensaje_id}", json={"isRead": True})
        self._pedir("POST", f"/me/messages/{mensaje_id}/move", json={"destinationId": carpeta_id})

    def responder(self, mensaje_id: str, respuesta: Respuesta) -> None:
        """Responde en el mismo hilo del correo recibido."""
        mensaje = {
            "subject": respuesta.asunto,
            "body": {"contentType": "Text", "content": respuesta.texto},
            # Pide a los servidores no contestar con respuestas automáticas.
            "internetMessageHeaders": [{"name": "X-Auto-Response-Suppress", "value": "All"}],
        }
        try:
            self._pedir("POST", f"/me/messages/{mensaje_id}/reply", json={"message": mensaje})
        except ErrorGraph as error:
            if "→ 400" not in str(error):
                raise
            # Si Graph no acepta la cabecera en /reply, se responde sin ella.
            logger.info("Graph no aceptó X-Auto-Response-Suppress en la respuesta; se envía sin ella")
            del mensaje["internetMessageHeaders"]
            self._pedir("POST", f"/me/messages/{mensaje_id}/reply", json={"message": mensaje})


def crear_cliente(config: ConfigCorreo) -> ClienteGraph:
    token = ProveedorToken(config.m365_tenant, config.m365_client_id, config.usuario,
                           config.cache_path)
    return ClienteGraph(token)


def revisar_buzon(session_factory, config: ConfigCorreo, cliente: ClienteGraph,
                  avisados: set | None = None) -> dict[str, int]:
    """Revisa los no leídos una vez y procesa los que piden ayuda.

    ``avisados`` (opcional) recuerda entre revisiones los correos que ya se
    anotaron en el registro como «no parece solicitud de ayuda»: como quedan
    sin leer, si no se anotarían de nuevo cada minuto.

    Devuelve cuántos correos terminaron en cada resultado. Un error de token
    (``SinSesionError``) sube a quien llama; los errores de un correo
    puntual se registran y se sigue con el siguiente.
    """
    conteo: dict[str, int] = {}
    with session_factory() as session:
        inicio = fecha_de_inicio(session)

    mensajes = cliente.no_leidos()
    carpeta_id = None
    for mensaje in mensajes:
        correo = correo_desde_graph(mensaje)
        if correo.fecha is not None and correo.fecha < inicio:
            continue  # Llegó antes de activar la función: no se toca.
        with session_factory() as session:
            try:
                resultado, respuesta = procesar_correo(session, correo, config)
            except Exception:
                session.rollback()
                logger.exception("No se pudo procesar el correo %s", correo.message_id)
                continue
        conteo[resultado] = conteo.get(resultado, 0) + 1
        if resultado == "otro":
            # No pide ayuda: queda sin leer y en la bandeja.
            if avisados is None or correo.message_id not in avisados:
                logger.info("Correo ignorado: no parece solicitud de ayuda «%s»", correo.asunto)
                if avisados is not None:
                    avisados.add(correo.message_id)
            continue
        if resultado != "repetido":
            logger.info("%s «%s» → %s", correo.remitente, correo.asunto, resultado)
        # Primero se responde (al mover, Graph le cambia el id al correo).
        if respuesta is not None:
            try:
                cliente.responder(mensaje["id"], respuesta)
            except SinSesionError:
                raise
            except Exception:
                logger.exception("No se pudo enviar la respuesta a %s", respuesta.para)
        try:
            if carpeta_id is None:
                carpeta_id = cliente.id_carpeta(config.carpeta_procesados)
            cliente.marcar_y_mover(mensaje["id"], carpeta_id)
        except SinSesionError:
            raise
        except Exception:
            # Queda en la bandeja: la próxima vez sale como «repetido» y se
            # vuelve a intentar mover, sin responder otra vez.
            logger.exception("No se pudo mover el correo «%s»", correo.asunto)
    return conteo


# --- Hilo en segundo plano -------------------------------------------------

_detener = threading.Event()
_hilo: threading.Thread | None = None


def _bucle(session_factory, config: ConfigCorreo, cliente: ClienteGraph) -> None:
    logger.info("leyendo el buzón %s cada %s s (correos: %s)", config.usuario, config.intervalo,
                "todos" if config.filtro == "todos" else "solo los que piden ayuda")
    conectado = False
    avisados: set = set()
    while not _detener.is_set():
        try:
            revisar_buzon(session_factory, config, cliente, avisados)
            if not conectado:
                logger.info("conexión con el buzón correcta")
                conectado = True
        except SinSesionError as error:
            logger.error("sesión de Microsoft no iniciada o vencida (%s). Ejecuta: "
                         "docker compose exec ticketera python -m backend.correo_login", error)
            conectado = False
        except Exception:
            logger.exception("error al revisar el buzón %s", config.usuario)
            conectado = False
        _detener.wait(config.intervalo)


def iniciar_lector(session_factory=None) -> bool:
    """Arranca el hilo que revisa el buzón si ``CORREO_ACTIVO`` está encendido."""
    global _hilo
    config = config_desde_entorno()
    if config is None:
        logger.info("lectura del buzón apagada (CORREO_ACTIVO no está en 1)")
        return False
    if _hilo is not None and _hilo.is_alive():
        return False
    if not (config.m365_tenant and config.m365_client_id):
        logger.warning("faltan CORREO_M365_TENANT o CORREO_M365_CLIENT_ID: no se puede entrar al buzón")
    if session_factory is None:
        from backend.database import SessionLocal

        session_factory = SessionLocal
    _detener.clear()
    _hilo = threading.Thread(target=_bucle, args=(session_factory, config, crear_cliente(config)),
                             name="lector-correo", daemon=True)
    _hilo.start()
    return True


def detener_lector() -> None:
    _detener.set()
