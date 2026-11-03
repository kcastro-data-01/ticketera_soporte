"""Adjuntos en un ticket ya creado (parte 1): subir, listar, descargar y
eliminar, con tipos validados por contenido, límites, permisos de ver el
ticket, Cerrado de solo lectura, historial, almacén local y Vercel Blob."""

import io
import sys
import types
import zipfile

import pytest
from sqlalchemy import create_engine, inspect, text

from backend.auth import hash_password
from backend.database import Base, enable_sqlite_foreign_keys
from backend.migrate_add_attachments import migrate_add_attachments
from backend.models import Attachment, History, User
from backend.services import adjuntos_service
from backend.tests.conftest import AuthenticatedClient

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + b"\x00" * 20
JPG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00" + b"\x00" * 20
PDF = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n%%EOF\n"
TXT = "Error al imprimir: «sin papel»\r\nLínea 2\n".encode("utf-8")


def _ooxml(parte: str, extra: dict[str, bytes] | None = None) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archivo:
        archivo.writestr("[Content_Types].xml", "<Types/>")
        archivo.writestr(parte, "<x/>")
        for nombre, datos in (extra or {}).items():
            archivo.writestr(nombre, datos)
    return buffer.getvalue()


DOCX = _ooxml("word/document.xml")
XLSX = _ooxml("xl/workbook.xml")
VALIDOS = {
    "foto.jpg": JPG, "foto.JPEG": JPG, "captura.png": PNG, "factura.pdf": PDF,
    "informe.docx": DOCX, "datos.xlsx": XLSX, "log.txt": TXT,
}

TICKET = {
    "title": "Impresora del segundo piso",
    "description": "La impresora no imprime desde esta mañana.",
    "category": "Hardware",
    "priority": "Media",
}


@pytest.fixture(autouse=True)
def carpeta(tmp_path, monkeypatch):
    destino = tmp_path / "adjuntos"
    monkeypatch.setenv("ADJUNTOS_DIR", str(destino))
    monkeypatch.delenv("BLOB_READ_WRITE_TOKEN", raising=False)
    monkeypatch.delenv("VERCEL", raising=False)
    return destino


def _cliente(client, session, nombre, email, rol) -> AuthenticatedClient:
    session.add(User(name=nombre, email=email, role=rol, password_hash=hash_password("clave123")))
    session.commit()
    resp = client.post("/api/auth/login", json={"email": email, "password": "clave123"})
    assert resp.status_code == 200, resp.text
    return AuthenticatedClient(client, resp.json()["access_token"])


@pytest.fixture
def ana(client, session):
    return _cliente(client, session, "Ana Solicitante", "ana@test.com", "Solicitante")


@pytest.fixture
def otro(client, session):
    return _cliente(client, session, "Otro Solicitante", "otro@test.com", "Solicitante")


@pytest.fixture
def tecnico(client, session):
    return _cliente(client, session, "Carlos Técnico", "carlos@test.com", "Técnico")


def _ticket(cliente) -> int:
    resp = cliente.post("/api/tickets", json=TICKET)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _subir(cliente, ticket_id, nombre, contenido):
    return cliente.post(
        f"/api/tickets/{ticket_id}/adjuntos",
        params={"nombre": nombre},
        content=contenido,
        headers={"Content-Type": "application/octet-stream"},
    )


def _historial(session, ticket_id, accion):
    session.expire_all()
    return [h for h in session.query(History).filter_by(ticket_id=ticket_id, action=accion)]


# --- Subir y listar -----------------------------------------------------------


def test_solicitante_sube_y_lista_su_adjunto(ana, session, carpeta):
    ticket_id = _ticket(ana)
    resp = _subir(ana, ticket_id, "captura.png", PNG)
    assert resp.status_code == 201, resp.text
    datos = resp.json()
    assert datos["nombre"] == "captura.png"
    assert datos["tipo"] == "image/png"
    assert datos["tamano"] == len(PNG)
    assert datos["es_imagen"] is True
    assert datos["subido_por"] == "Ana Solicitante"
    assert datos["puede_eliminar"] is True
    assert "storage_key" not in datos and "url" not in datos

    lista = ana.get(f"/api/tickets/{ticket_id}/adjuntos").json()
    assert [a["nombre"] for a in lista["adjuntos"]] == ["captura.png"]
    assert lista["puede_subir"] is True and lista["cerrado"] is False
    assert lista["max_archivos"] == 10 and lista["max_bytes"] == 4 * 1024 * 1024

    guardados = [p for p in carpeta.rglob("*") if p.is_file()]
    assert len(guardados) == 1 and guardados[0].read_bytes() == PNG
    # El nombre en disco no sale del nombre que mandó el usuario.
    assert guardados[0].name != "captura.png"
    assert guardados[0].parent.name == str(ticket_id)

    historial = _historial(session, ticket_id, "attachment_added")
    assert [(h.new_value, h.author) for h in historial] == [("captura.png", "Ana Solicitante")]


@pytest.mark.parametrize("nombre", sorted(VALIDOS))
def test_acepta_los_tipos_permitidos(auth_client, nombre):
    ticket_id = _ticket(auth_client)
    resp = _subir(auth_client, ticket_id, nombre, VALIDOS[nombre])
    assert resp.status_code == 201, resp.text


def test_txt_en_windows_1252(auth_client):
    ticket_id = _ticket(auth_client)
    assert _subir(auth_client, ticket_id, "viejo.txt", "Configuración".encode("cp1252")).status_code == 201


@pytest.mark.parametrize("nombre, contenido", [
    ("foto.png", b"esto es texto, no una imagen"),
    ("foto.jpg", PNG),
    ("factura.pdf", b"MZ\x90\x00programa"),
    ("informe.docx", _ooxml("otra/cosa.xml")),
    ("informe.docx", XLSX),
    ("datos.xlsx", b"PK\x03\x04roto"),
    ("macro.xlsx", _ooxml("xl/workbook.xml", {"xl/vbaProject.bin": b"\x00"})),
    ("log.txt", b"texto\x00binario"),
    ("log.txt", PDF),
    ("programa.exe", b"MZ\x90\x00"),
    ("pagina.html", b"<script>alert(1)</script>"),
    ("sin_extension", TXT),
    ("vacio.txt", b""),
])
def test_rechaza_tipo_o_contenido_invalido(auth_client, carpeta, nombre, contenido):
    ticket_id = _ticket(auth_client)
    resp = _subir(auth_client, ticket_id, nombre, contenido)
    assert resp.status_code == 422, resp.text
    assert "detail" in resp.json()
    assert not carpeta.exists() or not any(p.is_file() for p in carpeta.rglob("*"))


def test_rechaza_mas_de_4_mb(auth_client, carpeta):
    ticket_id = _ticket(auth_client)
    grande = b"a" * (4 * 1024 * 1024 + 1)
    resp = _subir(auth_client, ticket_id, "grande.txt", grande)
    assert resp.status_code == 413
    assert "4 MB" in resp.json()["detail"]
    justo = b"a" * (4 * 1024 * 1024)
    assert _subir(auth_client, ticket_id, "justo.txt", justo).status_code == 201


def test_maximo_10_por_ticket(auth_client):
    ticket_id = _ticket(auth_client)
    for i in range(10):
        assert _subir(auth_client, ticket_id, f"a{i}.txt", TXT).status_code == 201
    resp = _subir(auth_client, ticket_id, "once.txt", TXT)
    assert resp.status_code == 409
    assert "10 adjuntos" in resp.json()["detail"]
    assert auth_client.get(f"/api/tickets/{ticket_id}/adjuntos").json()["puede_subir"] is False


def test_nombre_se_limpia(auth_client, carpeta):
    ticket_id = _ticket(auth_client)
    resp = _subir(auth_client, ticket_id, "../../etc/\x07clave   final.txt", TXT)
    assert resp.status_code == 201
    assert resp.json()["nombre"] == "clave final.txt"
    for archivo in carpeta.rglob("*"):
        assert carpeta in archivo.parents


def test_sin_sesion_401(client, auth_client):
    ticket_id = _ticket(auth_client)
    assert client.get(f"/api/tickets/{ticket_id}/adjuntos").status_code == 401
    assert client.post(f"/api/tickets/{ticket_id}/adjuntos", params={"nombre": "a.txt"},
                       content=TXT).status_code == 401


# --- Descargar ----------------------------------------------------------------


def test_descarga_con_cabeceras_seguras(auth_client):
    ticket_id = _ticket(auth_client)
    adjunto = _subir(auth_client, ticket_id, "Informe año.txt", TXT).json()
    resp = auth_client.get(f"/api/tickets/{ticket_id}/adjuntos/{adjunto['id']}/archivo")
    assert resp.status_code == 200
    assert resp.content == TXT
    assert resp.headers["content-type"] == "text/plain; charset=utf-8"
    assert resp.headers["content-disposition"] == "attachment; filename*=UTF-8''Informe%20a%C3%B1o.txt"
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert "no-store" in resp.headers["cache-control"]


def test_adjunto_de_otro_ticket_es_404(auth_client):
    uno, dos = _ticket(auth_client), _ticket(auth_client)
    adjunto = _subir(auth_client, uno, "a.pdf", PDF).json()
    assert auth_client.get(f"/api/tickets/{dos}/adjuntos/{adjunto['id']}/archivo").status_code == 404
    assert auth_client.delete(f"/api/tickets/{dos}/adjuntos/{adjunto['id']}").status_code == 404


# --- Permisos -----------------------------------------------------------------


def test_solicitante_ajeno_no_ve_ni_sube(ana, otro):
    ticket_id = _ticket(ana)
    adjunto = _subir(ana, ticket_id, "a.pdf", PDF).json()
    assert otro.get(f"/api/tickets/{ticket_id}/adjuntos").status_code == 404
    assert _subir(otro, ticket_id, "b.pdf", PDF).status_code == 404
    assert otro.get(f"/api/tickets/{ticket_id}/adjuntos/{adjunto['id']}/archivo").status_code == 404
    assert otro.delete(f"/api/tickets/{ticket_id}/adjuntos/{adjunto['id']}").status_code == 404


def test_borra_quien_lo_subio_o_el_administrador(ana, tecnico, auth_client, session, carpeta):
    ticket_id = _ticket(ana)
    de_ana = _subir(ana, ticket_id, "ana.pdf", PDF).json()
    de_carlos = _subir(tecnico, ticket_id, "carlos.png", PNG).json()

    vista_carlos = {a["nombre"]: a["puede_eliminar"]
                    for a in tecnico.get(f"/api/tickets/{ticket_id}/adjuntos").json()["adjuntos"]}
    assert vista_carlos == {"ana.pdf": False, "carlos.png": True}

    resp = tecnico.delete(f"/api/tickets/{ticket_id}/adjuntos/{de_ana['id']}")
    assert resp.status_code == 403
    assert "quien subió" in resp.json()["detail"]
    assert ana.delete(f"/api/tickets/{ticket_id}/adjuntos/{de_carlos['id']}").status_code == 403

    assert ana.delete(f"/api/tickets/{ticket_id}/adjuntos/{de_ana['id']}").status_code == 204
    assert auth_client.delete(f"/api/tickets/{ticket_id}/adjuntos/{de_carlos['id']}").status_code == 204

    assert auth_client.get(f"/api/tickets/{ticket_id}/adjuntos").json()["adjuntos"] == []
    assert not any(p.is_file() for p in carpeta.rglob("*"))
    borrados = _historial(session, ticket_id, "attachment_deleted")
    assert sorted((h.old_value, h.author) for h in borrados) == [
        ("ana.pdf", "Ana Solicitante"), ("carlos.png", "Test Admin")]


# --- Cerrado ------------------------------------------------------------------


def test_cerrado_no_sube_ni_borra_pero_se_descarga(auth_client):
    ticket_id = _ticket(auth_client)
    adjunto = _subir(auth_client, ticket_id, "a.pdf", PDF).json()
    assert auth_client.patch(f"/api/tickets/{ticket_id}/state",
                             json={"state": "Cerrado"}).status_code == 200

    lista = auth_client.get(f"/api/tickets/{ticket_id}/adjuntos").json()
    assert lista["cerrado"] is True and lista["puede_subir"] is False
    assert lista["adjuntos"][0]["puede_eliminar"] is False

    resp = _subir(auth_client, ticket_id, "b.pdf", PDF)
    assert resp.status_code == 409 and "Cerrado" in resp.json()["detail"]
    resp = auth_client.delete(f"/api/tickets/{ticket_id}/adjuntos/{adjunto['id']}")
    assert resp.status_code == 409
    assert auth_client.get(f"/api/tickets/{ticket_id}/adjuntos/{adjunto['id']}/archivo").status_code == 200


# --- Eliminar el ticket -------------------------------------------------------


def test_eliminar_ticket_borra_sus_archivos(auth_client, session, carpeta):
    ticket_id = _ticket(auth_client)
    _subir(auth_client, ticket_id, "a.pdf", PDF)
    _subir(auth_client, ticket_id, "b.png", PNG)
    assert auth_client.delete(f"/api/tickets/{ticket_id}").status_code == 204
    session.expire_all()
    assert session.query(Attachment).count() == 0
    assert not any(p.is_file() for p in carpeta.rglob("*"))


# --- Migración ----------------------------------------------------------------


def test_migracion_crea_la_tabla_en_una_base_vieja(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'vieja.db'}")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE adjuntos"))
    assert not inspect(engine).has_table("adjuntos")

    assert migrate_add_attachments(engine) is True
    assert inspect(engine).has_table("adjuntos")
    assert migrate_add_attachments(engine) is False  # idempotente
    engine.dispose()


# --- Almacén ------------------------------------------------------------------


@pytest.fixture
def blob_falso(monkeypatch):
    """``vercel.blob.sync`` falso: guarda en memoria y anota las llamadas."""
    guardado, llamadas = {}, []

    def put_blob(pathname, body, *, access, content_type=None, **_):
        llamadas.append(("put", pathname, access, content_type))
        url = f"https://store.private.blob.vercel-storage.com/{pathname}"
        guardado[url] = bytes(body)
        return types.SimpleNamespace(url=url, pathname=pathname)

    def get_blob(url, *, access):
        llamadas.append(("get", url, access))
        return types.SimpleNamespace(body=guardado[url])

    def delete_blob(url, **_):
        llamadas.append(("delete", url))
        guardado.pop(url, None)

    sync = types.ModuleType("vercel.blob.sync")
    sync.put_blob, sync.get_blob, sync.delete_blob = put_blob, get_blob, delete_blob
    blob = types.ModuleType("vercel.blob")
    blob.sync = sync
    vercel = types.ModuleType("vercel")
    vercel.blob = blob
    monkeypatch.setitem(sys.modules, "vercel", vercel)
    monkeypatch.setitem(sys.modules, "vercel.blob", blob)
    monkeypatch.setitem(sys.modules, "vercel.blob.sync", sync)
    monkeypatch.setenv("BLOB_READ_WRITE_TOKEN", "vercel_blob_rw_prueba")
    monkeypatch.setenv("VERCEL", "1")
    return guardado, llamadas


def test_con_token_usa_vercel_blob_privado(auth_client, session, carpeta, blob_falso):
    guardado, llamadas = blob_falso
    ticket_id = _ticket(auth_client)
    adjunto = _subir(auth_client, ticket_id, "a.pdf", PDF).json()

    accion, pathname, access, tipo = llamadas[0]
    assert (accion, access, tipo) == ("put", "private", "application/pdf")
    assert pathname.startswith(f"adjuntos/tickets/{ticket_id}/") and pathname.endswith(".pdf")
    fila = session.get(Attachment, adjunto["id"])
    assert fila.storage == "blob" and fila.storage_key in guardado
    assert not carpeta.exists()

    resp = auth_client.get(f"/api/tickets/{ticket_id}/adjuntos/{adjunto['id']}/archivo")
    assert resp.content == PDF
    assert llamadas[-1] == ("get", fila.storage_key, "private")

    url = fila.storage_key
    assert auth_client.delete(f"/api/tickets/{ticket_id}/adjuntos/{adjunto['id']}").status_code == 204
    assert llamadas[-1] == ("delete", url) and guardado == {}


def test_en_vercel_sin_token_responde_503(auth_client, monkeypatch, carpeta):
    monkeypatch.setenv("VERCEL", "1")
    ticket_id = _ticket(auth_client)
    resp = _subir(auth_client, ticket_id, "a.pdf", PDF)
    assert resp.status_code == 503
    assert not carpeta.exists()


def test_carpeta_local_por_defecto(monkeypatch):
    monkeypatch.delenv("ADJUNTOS_DIR")
    carpeta = adjuntos_service.carpeta_local()
    assert carpeta.name == "adjuntos"
