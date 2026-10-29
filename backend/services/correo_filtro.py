"""¿Un correo es una solicitud de soporte? Lo decide la IA (``CORREO_FILTRO=ia``).

Las reglas fijas (respuestas automáticas, avisos de ticketeras, boletines,
destinatarios, dominio, «Ticket:» y respuestas en el hilo de un ticket) van
antes, en ``correo_service``; aquí llega solo lo que queda en duda.

A la IA se le manda solo el asunto y los primeros :data:`MAX_TEXTO_IA`
caracteres del cuerpo, y responde ``{"es_solicitud": bool, "motivo": "…"}``.
Si la IA falla (sin configurar, caída, 429 de Groq, JSON inválido) se usa el
filtro de respaldo :data:`SEÑALES_ESTRICTAS`, que solo acepta frases de un
problema real, y queda en el log. Después de una falla la IA se deja de
llamar por :data:`PAUSA_TRAS_FALLA` segundos (así un 429 no frena cada correo
de la revisión).
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
import unicodedata
from dataclasses import dataclass

logger = logging.getLogger("backend.services.correo_service")

MAX_TEXTO_IA = 800
TIMEOUT_IA = 8.0
PAUSA_TRAS_FALLA = 60.0

ESQUEMA = {
    "type": "object",
    "properties": {
        "es_solicitud": {"type": "boolean"},
        "motivo": {"type": "string"},
    },
    "required": ["es_solicitud", "motivo"],
}

SISTEMA = (
    "Clasificás correos que llegan al buzón de soporte técnico de una empresa. "
    "Decidí si el correo es una SOLICITUD DE SOPORTE.\n"
    "Es solicitud si la persona reporta un problema técnico (algo no funciona, se dañó, da error, "
    "no puede entrar) o pide ayuda, un acceso, un permiso, una instalación o soporte.\n"
    "NO es solicitud si es un resumen, un informe o un reporte; la presentación de un proyecto "
    "(aunque hable de tickets, ticketeras o soporte); un aviso automático de un sistema; un "
    "saludo; un agradecimiento; una invitación o reunión; un envío de archivos; publicidad o "
    "cualquier otra conversación.\n"
    "Si el correo lista tickets o problemas de otras personas para informar, NO es solicitud.\n"
    'Respondé solo JSON: {"es_solicitud": true|false, "motivo": "frase corta en español"}.'
)

# Ejemplos (asunto, cuerpo, es_solicitud, motivo).
EJEMPLOS: tuple[tuple[str, str, bool, str], ...] = (
    ("Se dañó mi computadora", "Buenos días, mi computadora no enciende desde esta mañana.",
     True, "reporta un equipo dañado"),
    ("Acceso a carpeta compartida", "Hola, necesito acceso a la carpeta de Contabilidad, gracias.",
     True, "pide un acceso"),
    ("Outlook", "Me sale un error cada vez que intento enviar un correo.", True,
     "reporta un error en un programa"),
    ("Resumen de la ticketera",
     "Les comparto el resumen de nuestra ticketera: 12 tickets abiertos, #4 La impresora no "
     "imprime (crítico), #7 Sin red en el piso 2 (alto).",
     False, "es un resumen de tickets, no pide ayuda"),
    ("Proyecto ticketera de soporte",
     "Les presento el proyecto: una ticketera para registrar los problemas de soporte con "
     "prioridades y estados. Adjunto la presentación.",
     False, "presenta un proyecto"),
    ("Gracias", "Muchas gracias por la ayuda de ayer, ya quedó funcionando.", False,
     "es un agradecimiento"),
    ("Reunión del viernes", "Les recuerdo la reunión de seguimiento a las 10 am.", False,
     "es una invitación a reunión"),
    ("Archivos del informe", "Adjunto los archivos que me pidieron.", False, "es un envío de archivos"),
)

# Respaldo estricto (minúsculas, sin tildes): solo frases de un problema o de
# un pedido real. «ticket», «ticketera», «soporte», «estado» o «prioridad»
# sueltas no cuentan.
SEÑALES_ESTRICTAS = tuple(re.compile(p) for p in (
    r"\bno (me |nos |le |te )?(funciona|funcionan|sirve|sirven|enciende|prende|arranca|abre|"
    r"carga|imprime|conecta|responde|reconoce)\b",
    r"\bno (puedo|podemos|logro|puede) (entrar|ingresar|abrir|imprimir|conectar(me)?|acceder|"
    r"enviar|iniciar sesion|trabajar|instalar|usar|descargar)\b",
    r"\bse (me |nos |le )?(dano|danaron|quebro|cayo|cayeron|trabo|pego|congelo|apaga|reinicia|"
    r"desconecta|bloqueo)\b",
    r"\b(esta|estan) (danad|caid|bloquead|trabad|congelad)",
    r"\b(olvide|perdi) (mi |la )?(contrasena|clave)\b",
    r"\b(me sale|aparece|me da|da|tira) (un )?error\b",
    r"\b(estoy|estamos|quede|quedamos) sin (internet|red|conexion|acceso|sistema)\b",
    r"\bno tengo (acceso|internet|red|conexion|permisos?)\b",
    r"\bnecesito (ayuda|acceso|soporte|permisos?|que me (ayuden|instalen|den acceso|habiliten))\b",
    r"\b(me|nos) (pueden|podrian|puede|podria) ayudar\b",
    r"\b(ayudenme|ayudame|ayudenos)\b",
    r"\b(solicito|requiero|ocupo) (acceso|permisos?|ayuda|soporte|instalar|la instalacion)\b",
))
# Aunque traiga una frase de problema, esto es un informe (p. ej. un resumen
# que lista tickets ajenos), no una solicitud.
NEGATIVOS_ESTRICTOS = tuple(re.compile(p) for p in (
    r"\b(resumen|informe|boletin|minuta)\b",
    r"(?s)#\d+.*#\d+",
))


@dataclass
class Decision:
    es_solicitud: bool
    motivo: str
    # «ia» o «respaldo» (la IA falló y se usó SEÑALES_ESTRICTAS).
    fuente: str


def _sin_tildes(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()


def es_solicitud_estricta(asunto: str, cuerpo: str) -> tuple[bool, str]:
    """El filtro de respaldo: (¿es solicitud?, motivo)."""
    texto = _sin_tildes(f"{asunto}\n{cuerpo}".lower())
    if any(p.search(texto) for p in NEGATIVOS_ESTRICTOS):
        return False, "parece un informe o resumen"
    for patron in SEÑALES_ESTRICTAS:
        if (encontrado := patron.search(texto)):
            return True, f"frase de problema «{encontrado.group(0)}»"
    return False, "sin frases de problema"


def _texto(asunto: str, cuerpo: str) -> str:
    return f"Asunto: {asunto}\n\n{(cuerpo or '')[:MAX_TEXTO_IA]}"


def mensajes(asunto: str, cuerpo: str) -> list[dict]:
    """System, los ejemplos (usuario/asistente) y el correo a clasificar."""
    lista = [{"role": "system", "content": SISTEMA}]
    for e_asunto, e_cuerpo, es, motivo in EJEMPLOS:
        lista.append({"role": "user", "content": _texto(e_asunto, e_cuerpo)})
        lista.append({"role": "assistant",
                      "content": json.dumps({"es_solicitud": es, "motivo": motivo}, ensure_ascii=False)})
    lista.append({"role": "user", "content": _texto(asunto, cuerpo)})
    return lista


def leer_respuesta(texto: str) -> tuple[bool, str]:
    """Valida el JSON de la IA; ``ValueError`` si no sirve."""
    datos = json.loads(texto)
    if not isinstance(datos, dict) or not isinstance(datos.get("es_solicitud"), bool):
        raise ValueError("falta es_solicitud (bool)")
    motivo = datos.get("motivo")
    motivo = " ".join(motivo.split())[:120] if isinstance(motivo, str) else ""
    return datos["es_solicitud"], motivo or "sin motivo"


_proveedor = None
_pausa_hasta = 0.0
_candado = threading.Lock()


def _crear_proveedor():
    """El proveedor de IA del asistente (``ASISTENTE_PROVEEDOR``), uno solo."""
    global _proveedor
    with _candado:
        if _proveedor is None:
            from backend.services import asistente_service

            _proveedor = asistente_service.crear_proveedor()
        return _proveedor


def ia_disponible() -> bool:
    """¿Hay IA configurada? (decide el ``CORREO_FILTRO`` por defecto)."""
    from backend.services import asistente_service

    return asistente_service.ia_activa()


def _respaldo(asunto: str, cuerpo: str, por: str) -> Decision:
    es, motivo = es_solicitud_estricta(asunto, cuerpo)
    logger.warning("Filtro de correo: se usó el filtro de respaldo (IA: %s)", por)
    return Decision(es, motivo, "respaldo")


def clasificar(asunto: str, cuerpo: str) -> Decision:
    """La decisión de la IA o, si falla, la del respaldo estricto."""
    global _pausa_hasta
    if time.monotonic() < _pausa_hasta:
        return _respaldo(asunto, cuerpo, "en pausa tras una falla reciente")
    try:
        texto = _crear_proveedor().generar_json(mensajes(asunto, cuerpo), ESQUEMA, 0.0,
                                                 timeout=TIMEOUT_IA)
        es, motivo = leer_respuesta(texto)
    except ValueError as error:
        return _respaldo(asunto, cuerpo, f"JSON inválido: {error}")
    except Exception as error:  # noqa: BLE001 — cualquier falla usa el respaldo
        _pausa_hasta = time.monotonic() + PAUSA_TRAS_FALLA
        return _respaldo(asunto, cuerpo, f"{type(error).__name__}: {error}")
    return Decision(es, motivo, "ia")


def reiniciar() -> None:
    """Olvida el proveedor y la pausa (pruebas, o cambio de configuración)."""
    global _proveedor, _pausa_hasta
    with _candado:
        _proveedor = None
        _pausa_hasta = 0.0
