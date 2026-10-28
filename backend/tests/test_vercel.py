"""Versión de Vercel: Postgres, IA apagada, correo por cron, caché de tokens
en la base y lo que no se puede ver sin sesión."""

import json
import os
import subprocess
import sys
import time

import pytest
from sqlalchemy.orm import sessionmaker

from backend import database
from backend.main import app
from backend.models import MsalCache, Ticket
from backend.routers import cron
from backend.services import asistente_service, correo_service as cs
from backend.services import correo_auth as ca
from backend.services import login_microsoft as lm
from backend.tests.test_asistente import add_ticket, login_as
from backend.tests.test_correo import CONFIG, FakeGraph, crear_correo, usuario  # noqa: F401
from backend.tests.test_correo_auth import fabrica
from backend.tests.test_login_microsoft import entrar, id_token, tenant_simulado  # noqa: F401


@pytest.fixture
def factory(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)


def correr(codigo: str, **env) -> subprocess.CompletedProcess:
    """Importa la app en otro proceso con esas variables (p. ej. VERCEL=1)."""
    entorno = {k: v for k, v in os.environ.items() if k not in ("VERCEL", "JWT_SECRET_KEY", "LOGIN_LOCAL")}
    entorno.update(env)
    return subprocess.run([sys.executable, "-c", codigo], env=entorno, capture_output=True,
                          text=True, cwd=database.PROJECT_ROOT)


# --- Base de datos ----------------------------------------------------------


@pytest.mark.parametrize("url, esperada", [
    ("postgres://u:p@ep-x.neon.tech/db?sslmode=require", "postgresql+psycopg://u:p@ep-x.neon.tech/db?sslmode=require"),
    ("postgresql://u:p@host/db", "postgresql+psycopg://u:p@host/db"),
    ("postgresql+psycopg://u:p@host/db", "postgresql+psycopg://u:p@host/db"),
    ("sqlite:////data/ticketera.db", "sqlite:////data/ticketera.db"),
])
def test_postgres_urls_use_psycopg(url, esperada):
    assert database.resolve_database_url(url) == esperada
    assert database.es_sqlite(esperada) == esperada.startswith("sqlite")


def test_postgres_engine_has_no_local_pool_nor_sqlite_pragma():
    motor = database.build_engine("postgresql+psycopg://u:p@localhost:1/db")
    assert type(motor.pool).__name__ == "NullPool"
    assert motor.dialect.name == "postgresql"


# --- IA apagada -------------------------------------------------------------


@pytest.fixture
def sin_ia(monkeypatch):
    monkeypatch.setenv("ASISTENTE_PROVEEDOR", "ninguno")
    monkeypatch.setenv("ASISTENTE_REDACTAR_CON_IA", "true")
    monkeypatch.setenv("ASISTENTE_INTERPRETAR_CON_IA", "true")


def test_vercel_turns_the_ai_off_by_default(monkeypatch):
    monkeypatch.delenv("ASISTENTE_PROVEEDOR", raising=False)
    assert asistente_service.ia_activa()
    monkeypatch.setenv("VERCEL", "1")
    assert not asistente_service.ia_activa()
    assert isinstance(asistente_service.crear_proveedor(), asistente_service.ProveedorApagado)
    monkeypatch.setenv("ASISTENTE_PROVEEDOR", "qwen")  # se puede volver a encender
    assert asistente_service.ia_activa()


def test_without_ai_redaction_and_interpretation_are_off(sin_ia):
    assert not asistente_service.redactar_con_ia_activo()
    assert not asistente_service.interpretar_con_ia_activo()
    assert asistente_service.iniciar_precarga() is None


def test_without_ai_counts_still_answer(client, session, sin_ia):
    headers = login_as(client, session, "Administrador", "admin@data.cr", "Admin")
    add_ticket(session, "Impresora")
    resp = client.post("/api/asistente", json={"messages": [
        {"role": "user", "content": "¿Cuántos tickets nuevos hay?"}]}, headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["fuente"] == "directa"
    assert "1" in resp.json()["respuesta"]


def test_without_ai_the_free_chat_says_it_is_not_available(session, monkeypatch, sin_ia):
    proveedor = asistente_service.crear_proveedor()
    monkeypatch.setattr(asistente_service, "_preparar", lambda *a: (None, "prompt", "¿y la vida?"))
    usuario = object()
    assert asistente_service.responder_completo(proveedor, session, usuario, []) == (
        asistente_service.MENSAJE_SIN_IA, "directa")
    eventos = list(asistente_service.responder_stream(proveedor, session, usuario, []))
    assert eventos == [{"t": asistente_service.MENSAJE_SIN_IA}, {"fin": True, "fuente": "directa"}]
    with pytest.raises(asistente_service.AsistenteNoDisponible):
        proveedor.responder("x", [])


def test_without_ai_explain_is_503_and_the_page_knows(client, session, sin_ia):
    headers = login_as(client, session, "Técnico", "tec@data.cr", "José")
    ticket = Ticket(title="No sirve", description="no sirve", category="Software", priority="Media")
    session.add(ticket)
    session.commit()
    resp = client.post(f"/api/tickets/{ticket.id}/explicacion", headers=headers)
    assert resp.status_code == 503
    assert resp.json()["detail"] == "La IA no está disponible en esta versión"
    guardada = client.get(f"/api/tickets/{ticket.id}/explicacion", headers=headers)
    assert guardada.status_code == 200 and guardada.json()["ia_disponible"] is False
    assert client.get("/api/config").json()["ia_disponible"] is False


def test_with_ai_the_page_offers_explain(client, session):
    headers = login_as(client, session, "Técnico", "tec@data.cr", "José")
    ticket = Ticket(title="No sirve", description="no sirve", category="Software", priority="Media")
    session.add(ticket)
    session.commit()
    assert client.get(f"/api/tickets/{ticket.id}/explicacion", headers=headers).json()["ia_disponible"] is True
    assert client.get("/api/config").json()["ia_disponible"] is True


# --- Correo por cron --------------------------------------------------------


def test_cron_mode_by_env(monkeypatch):
    assert cs.modo_desde_entorno({}) == "hilo"
    assert cs.modo_desde_entorno({"VERCEL": "1"}) == "cron"
    assert cs.modo_desde_entorno({"VERCEL": "1", "CORREO_MODO": "hilo"}) == "hilo"
    assert cs.modo_desde_entorno({"CORREO_MODO": "cron"}) == "cron"


def test_cron_mode_does_not_start_the_thread(monkeypatch):
    monkeypatch.setenv("CORREO_ACTIVO", "1")
    monkeypatch.setenv("CORREO_USUARIO", "soporte@data.cr")
    monkeypatch.setenv("CORREO_MODO", "cron")
    assert cs.iniciar_lector() is False
    assert cs._hilo is None or not cs._hilo.is_alive()


@pytest.mark.parametrize("secreto, cabecera, estado", [
    ("", "Bearer x", 404),
    ("s3creto-largo", None, 401),
    ("s3creto-largo", "Bearer otro", 401),
    ("s3creto-largo", "s3creto-largo", 401),
])
def test_cron_requires_the_secret(client, monkeypatch, secreto, cabecera, estado):
    llamado = []
    monkeypatch.setattr(cs, "revisar_una_vez", lambda: llamado.append(1) or {})
    monkeypatch.setenv("CRON_SECRET", secreto)
    headers = {"Authorization": cabecera} if cabecera else {}
    assert client.post("/api/cron/correo", headers=headers).status_code == estado
    assert llamado == []


def test_cron_runs_one_cycle(client, monkeypatch):
    monkeypatch.setenv("CRON_SECRET", "s3creto-largo")
    monkeypatch.setattr(cs, "revisar_una_vez", lambda: {"ticket": 2})
    resp = client.post("/api/cron/correo", headers={"Authorization": "Bearer s3creto-largo"})
    assert resp.status_code == 200
    assert resp.json() == {"estado": "ok", "conteo": {"ticket": 2}}


@pytest.mark.parametrize("error, detalle", [
    (cs.CorreoApagado("apagada"), "apagada"),
    (ca.SinSesionError("venció"), "La sesión del buzón no está iniciada o venció"),
])
def test_cron_errors_are_503(client, monkeypatch, error, detalle):
    monkeypatch.setenv("CRON_SECRET", "s3creto-largo")

    def falla():
        raise error

    monkeypatch.setattr(cs, "revisar_una_vez", falla)
    resp = client.post("/api/cron/correo", headers={"Authorization": "Bearer s3creto-largo"})
    assert resp.status_code == 503 and resp.json()["detail"] == detalle


def test_revisar_una_vez_requires_mail_on(monkeypatch):
    monkeypatch.delenv("CORREO_ACTIVO", raising=False)
    with pytest.raises(cs.CorreoApagado):
        cs.revisar_una_vez()


def test_revisar_una_vez_uses_the_env_config_and_cron_timeout(factory, monkeypatch):
    monkeypatch.setenv("CORREO_ACTIVO", "1")
    monkeypatch.setenv("CORREO_USUARIO", "soporte@data.cr")
    monkeypatch.setenv("CORREO_MODO", "cron")
    graph = FakeGraph([])
    usados = []

    def crear(config, session_factory):
        usados.append((config.modo, session_factory))
        return graph.cliente

    assert cs.revisar_una_vez(factory, crear=crear) == {}
    assert usados == [("cron", factory)]
    cliente = cs.crear_cliente(cs.config_desde_entorno(), factory)
    assert cliente._http.timeout.read == cs.TIMEOUT_GRAPH_CRON
    assert isinstance(cliente._token.almacen, ca.AlmacenBD)


def test_time_limit_leaves_the_rest_for_the_next_call(factory, usuario):
    graph = FakeGraph([crear_correo(msg_id="<a@x>"), crear_correo(msg_id="<b@x>")])
    # Sin tiempo: no se toca ningún correo (quedan sin leer para la próxima).
    conteo = cs.revisar_buzon(factory, CONFIG, graph.cliente, hasta=time.monotonic() - 1)
    assert conteo == {}
    assert len(graph.no_leidos()) == 2
    assert graph.respuestas == []
    # Con tiempo, la próxima llamada los procesa.
    conteo = cs.revisar_buzon(factory, CONFIG, graph.cliente, hasta=time.monotonic() + 60)
    assert conteo == {"ticket": 2}
    assert graph.no_leidos() == []


def test_time_limit_in_the_middle_counts_the_pending(factory, usuario, monkeypatch):
    graph = FakeGraph([crear_correo(msg_id=f"<{n}@x>") for n in range(3)])
    # Consultas al reloj: antes de leer la bandeja y antes de cada correo; se
    # acaba después del primero.
    consultas = []
    monkeypatch.setattr(cs, "_sin_tiempo", lambda hasta: consultas.append(1) or len(consultas) > 2)
    conteo = cs.revisar_buzon(factory, CONFIG, graph.cliente, hasta=50)
    assert conteo == {"ticket": 1, "pendientes": 2}
    assert len(graph.no_leidos()) == 2


def test_lock_is_a_no_op_on_sqlite():
    with cron.candado(cron.CANDADO_CORREO) as obtenido:
        assert obtenido is True


# --- Caché de tokens en la base ----------------------------------------------


def test_db_cache_round_trip_and_version(factory):
    almacen = ca.AlmacenBD(factory)
    assert almacen.leer() is None and almacen.version() is None
    almacen.guardar('{"a": 1}')
    v1 = almacen.version()
    assert almacen.leer() == '{"a": 1}' and v1 is not None
    almacen.guardar('{"a": 2}')
    assert almacen.leer() == '{"a": 2}'
    with factory() as s:
        assert s.query(MsalCache).count() == 1


def test_db_cache_imports_the_old_file_once(factory, tmp_path):
    archivo = tmp_path / "msal_cache.json"
    archivo.write_text('{"sesion": "vieja"}')
    almacen = ca.AlmacenBD(factory, importar_de=archivo)
    assert almacen.leer() == '{"sesion": "vieja"}'
    archivo.write_text('{"sesion": "otra"}')  # ya está en la base: no se vuelve a importar
    assert almacen.leer() == '{"sesion": "vieja"}'
    assert archivo.exists()  # queda de respaldo


def test_token_from_db_cache_and_refresh_is_saved(factory):
    almacen = ca.AlmacenBD(factory)
    almacen.guardar("{}")
    crear, creadas = fabrica(cuentas=[{"username": "kcastro@data.cr"}], silencioso={"access_token": "abc"})
    token = ca.ProveedorToken("t", "c", "kcastro@data.cr", almacen, crear=crear)
    assert token.obtener() == "abc"
    app_msal = creadas[0][2]
    app_msal.cache.deserialize(json.dumps({"AccessToken": {"x": {"secret": "nuevo"}}}))
    app_msal.cache.has_state_changed = True
    assert token.obtener() == "abc"
    assert "nuevo" in almacen.leer()
    assert len(creadas) == 1


def test_token_without_db_cache_asks_to_log_in(factory):
    token = ca.ProveedorToken("t", "c", "x@data.cr", ca.AlmacenBD(factory))
    with pytest.raises(ca.SinSesionError, match="no existe la caché de tokens en la base"):
        token.obtener()


def test_login_command_saves_the_tokens_in_the_db(factory, tmp_path):
    from backend import correo_login

    crear, _ = fabrica(dispositivo={"access_token": "x", "id_token_claims": {"preferred_username": "k@data.cr"}})
    salida = []
    env = {"CORREO_M365_TENANT": "t", "CORREO_M365_CLIENT_ID": "c",
           "CORREO_M365_CACHE": str(tmp_path / "no-existe.json")}

    def iniciar(tenant, client_id, almacen, imprimir):
        return ca.iniciar_sesion(tenant, client_id, almacen, imprimir=imprimir, crear=crear)

    assert correo_login.main(env=env, imprimir=salida.append, iniciar=iniciar, session_factory=factory) == 0
    assert "AccessToken" in ca.AlmacenBD(factory).leer()
    assert "base de datos" in salida[-1]


# --- Sin sesión ninguna ruta devuelve datos ----------------------------------

PUBLICAS = {
    ("GET", "/health"),
    ("GET", "/api/config"),
    ("GET", "/api/auth/config"),
    ("POST", "/api/auth/microsoft"),  # valida el token de Microsoft
    ("POST", "/api/auth/login"),  # solo con LOGIN_LOCAL (desarrollo)
    ("POST", "/api/cron/correo"),  # pide CRON_SECRET (pruebas de arriba)
}


def _rutas():
    """Todas las rutas de la API (del esquema OpenAPI: con routers anidados
    ``app.routes`` no las muestra todas)."""
    for ruta, operaciones in app.openapi()["paths"].items():
        for metodo in operaciones:
            yield metodo.upper(), ruta


def test_the_route_sweep_sees_every_router():
    rutas = set(_rutas())
    assert len(rutas) > 25
    assert ("GET", "/api/tickets") in rutas and ("PATCH", "/api/users/{user_id}") in rutas


@pytest.mark.parametrize("metodo, ruta", sorted(set(_rutas())))
def test_every_private_route_answers_401_without_session(client, metodo, ruta):
    if (metodo, ruta) in PUBLICAS:
        pytest.skip("pública, sin datos de tickets ni usuarios")
    url = ruta.replace("{ticket_id}", "1").replace("{user_id}", "1").replace("{id}", "1")
    resp = client.request(metodo, url, json={})
    assert resp.status_code == 401, f"{metodo} {ruta} → {resp.status_code}: {resp.text[:200]}"


def test_public_routes_list_is_complete():
    """Si se agrega una ruta pública nueva, hay que revisarla aquí."""
    assert PUBLICAS <= set(_rutas())


# --- Inicio de sesión: solo cuentas de la empresa ------------------------------


def test_guest_account_of_the_tenant_is_rejected(client, monkeypatch):
    monkeypatch.setenv("DOMINIO_EMPRESA", "data.cr")
    assert entrar(client, id_token()).status_code == 200
    invitado = id_token(email="alguien@gmail.com", preferred_username="alguien@gmail.com",
                        idp="https://sts.windows.net/9188040d-6c67-4c5b-b112-36a304b66dad/")
    assert entrar(client, invitado).status_code == 401
    # Aunque no traiga idp, el correo tiene que ser del dominio.
    assert entrar(client, id_token(email="alguien@gmail.com")).status_code == 401
    assert entrar(client, id_token(email="ana@data.cr.otro.com")).status_code == 401


def test_idp_of_the_same_tenant_is_accepted(client):
    resp = entrar(client, id_token(idp=f"https://sts.windows.net/{lm_tid()}/"))
    assert resp.status_code == 200


def lm_tid():
    from backend.tests.test_login_microsoft import TID

    return TID


# --- Arranque en Vercel --------------------------------------------------------


def test_vercel_refuses_to_start_without_jwt_secret():
    resultado = correr("import backend.main", VERCEL="1", DATABASE_URL="sqlite:///:memory:")
    assert resultado.returncode != 0
    assert "JWT_SECRET_KEY" in resultado.stderr


def test_vercel_hides_docs_and_password_login():
    codigo = (
        "from fastapi.testclient import TestClient\n"
        "from backend.main import app\n"
        "from backend.auth import login_local_activo\n"
        "c = TestClient(app)\n"
        "print(c.get('/docs').status_code, c.get('/openapi.json').status_code, login_local_activo())\n"
    )
    resultado = correr(codigo, VERCEL="1", JWT_SECRET_KEY="x" * 40, LOGIN_LOCAL="true",
                       DATABASE_URL="sqlite:///:memory:")
    assert resultado.returncode == 0, resultado.stderr
    assert resultado.stdout.split() == ["404", "404", "False"]


def test_docker_keeps_docs():
    resultado = correr("from backend.main import app; print(app.docs_url)", DATABASE_URL="sqlite:///:memory:")
    assert resultado.stdout.strip() == "/docs"


def test_robots_and_noindex_on_every_page():
    frontend = database.PROJECT_ROOT / "frontend"
    assert (frontend / "robots.txt").read_text().splitlines() == ["User-agent: *", "Disallow: /"]
    for pagina in frontend.glob("*.html"):
        assert '<meta name="robots" content="noindex, nofollow">' in pagina.read_text(), pagina.name
    config = json.loads((database.PROJECT_ROOT / "vercel.json").read_text())
    encabezados = {h["key"]: h["value"] for regla in config["headers"] for h in regla["headers"]}
    assert encabezados["X-Robots-Tag"].startswith("noindex")


def test_no_secrets_in_the_repository_files():
    raiz = database.PROJECT_ROOT
    gitignore = (raiz / ".gitignore").read_text()
    assert ".env\n" in gitignore and ".env.*" in gitignore
    for nombre in ("vercel.json", ".env.example", "docker-compose.yml"):
        texto = (raiz / nombre).read_text()
        for marca in ("postgres://", "postgresql://", "neon.tech"):
            assert marca not in texto, f"{nombre} tiene {marca}"
