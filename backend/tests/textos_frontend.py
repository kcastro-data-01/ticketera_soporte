"""Textos del frontend React para las pruebas que los comparan con el chat
(la tabla de permisos de la Ayuda, los departamentos, etc.). El contenido de
la Ayuda está en ``frontend-react/src/ayuda/contenido.jsx`` (generado de la
ayuda.html de antes): se lee con ``class=`` en lugar de ``className=`` y
``<br>`` en lugar de ``<br />``, así las pruebas lo miran como HTML."""

from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
SRC = RAIZ / "frontend-react" / "src"


class Pagina:
    """Un archivo de la app con la misma interfaz que un ``Path`` (``read_text``)."""

    def __init__(self, relativa: str):
        self.ruta = SRC / relativa
        self.name = self.ruta.name

    def exists(self) -> bool:
        return self.ruta.exists()

    def read_text(self, encoding: str = "utf-8") -> str:
        texto = self.ruta.read_text(encoding=encoding)
        return texto.replace('className="', 'class="').replace(" />", ">")


AYUDA = Pagina("ayuda/contenido.jsx")
CREAR = Pagina("paginas/Crear.jsx")
USUARIOS = Pagina("paginas/Usuarios.jsx")


def paginas():
    """Todas las pantallas (los .jsx de src/paginas y el contenido de la Ayuda)."""
    return [AYUDA, *(Pagina(f"paginas/{p.name}") for p in sorted((SRC / "paginas").glob("*.jsx")) if ".test." not in p.name)]
