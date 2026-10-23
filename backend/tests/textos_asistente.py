"""Ayudas para probar las respuestas del sistema del asistente.

Cada respuesta se dice de varias formas, elegidas al azar
(``asistente_service.VARIANTES``). Estas ayudas comprueban los datos (números,
nombres y #tickets) y aceptan cualquiera de las formas, con o sin el nombre de
la persona al principio y con o sin un cierre al final.
"""

import itertools
import re

from backend.services import asistente_service as a

CIERRES = sorted((c for cs in a.CIERRES.values() for c in cs), key=len, reverse=True)
_NOMBRE_AL_INICIO = re.compile(r"^[A-ZÁÉÍÓÚÑ][a-záéíóúñü]+, ")


def negrita(valor) -> str:
    return f"**{valor}**"


def sin_cierre(texto: str) -> str:
    for cierre in CIERRES:
        if texto.endswith(cierre):
            return texto[: -len(cierre)].rstrip(" \n")
    return texto


def _misma_frase(uno: str, otro: str) -> bool:
    """Iguales salvo la mayúscula de la primera letra (con el nombre delante
    la frase sigue en minúscula)."""
    return uno[:1].lower() + uno[1:] == otro[:1].lower() + otro[1:]


def formas(tipo: str, **datos) -> list[str]:
    """Todas las formas de ``tipo`` con ``datos``; un dato que es una tupla
    se prueba con cada uno de sus valores."""
    claves = list(datos)
    valores = [v if isinstance(v, tuple) else (v,) for v in datos.values()]
    return [plantilla.format(**dict(zip(claves, combinacion)))
            for plantilla in a.VARIANTES[tipo]
            for combinacion in itertools.product(*valores)]


def es_forma(texto: str, tipo: str, despues: str = "", **datos) -> bool:
    """¿``texto`` es una forma de ``tipo`` con ``datos`` seguida de
    ``despues``? Acepta el nombre de la persona al principio y un cierre."""
    texto = sin_cierre(texto)
    candidatos = [texto]
    nombre = _NOMBRE_AL_INICIO.match(texto)
    if nombre:
        candidatos.append(texto[nombre.end():])
    return any(_misma_frase(c, f + despues) for c in candidatos for f in formas(tipo, **datos))


def cabecera(texto: str) -> str:
    """La primera línea: el texto que va arriba de la lista de tickets."""
    return texto.splitlines()[0]


def lista(texto: str) -> list[str]:
    """Las líneas de la lista de tickets (y el «…y N más»)."""
    return [linea for linea in texto.splitlines()[1:] if linea.startswith(("- ", "…y "))]


def sin_formato(texto: str) -> str:
    """El texto sin la negrita, para buscar los datos dentro."""
    return texto.replace("**", "")


AYUDA_EQUIPO = a.VARIANTES["ayuda_equipo"]
AYUDA_SOLICITANTE = a.VARIANTES["ayuda_solicitante"]
