"""Versión de Render: MODO_PRODUCCION (o RENDER) se porta como VERCEL=1, el
contenedor escucha en PORT, FastAPI pone las cabeceras de seguridad y el cron
del correo no baja nada si no hay correos nuevos."""

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import pytest

from backend.tests.test_frontend_react import build_falso
from sqlalchemy.orm import sessionmaker

from backend import cabeceras, database
from backend.entorno import en_produccion, en_vercel
from backend.models import ProcessedEmail
from backend.services import adjuntos_service, asistente_service, cierre_service
from backend.services import correo_service as cs
from backend.tests.test_correo import CONFIG, FakeGraph, crear_correo, usuario  # noqa: F401
from backend.tests.test_correo_enviados import crear_enviado

RAIZ = database.PROJECT_ROOT
VARIABLES_ENTORNO = ("VERCEL", "RENDER", "MODO_PRODUCCION", "JWT_SECRET_KEY", "LOGIN_LOCAL")


@pytest.fixture
def factory(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture
def produccion(monkeypatch):
    for nombre in VARIABLES_ENTORNO:
        monkeypatch.delenv(nombre, raising=False)
    monkeypatch.setenv("MODO_PRODUCCION", "1")
    return monkeypatch


def correr(codigo: str, **env) -> subprocess.CompletedProcess:
    entorno = {k: v for k, v in os.environ.items() if k not in VARIABLES_ENTORNO}
    entorno.update(env)
    return subprocess.run([sys.executable, "-c", codigo], env=entorno, capture_output=True,
                          text=True, cwd=RAIZ)


# --- Modo producción ----------------------------------------------------------


@pytest.mark.parametrize("env, esperado", [
    ({}, False),
    ({"MODO_PRODUCCION": "0"}, False),
    ({"MODO_PRODUCCION": "1"}, True),
    ({"MODO_PRODUCCION": "true"}, True),
    ({"RENDER": "true"}, True),
    ({"VERCEL": "1"}, True),
])
def test_produccion_por_variable(env, esperado):
    assert en_produccion(env) is esperado
    assert en_vercel(env) is ("VERCEL" in env)


def test_en_render_los_valores_por_defecto_son_los_de_vercel():
    env = {"MODO_PRODUCCION": "1"}
    assert cs.modo_desde_entorno(env) == "cron"
    assert cs.modo_desde_entorno({**env, "CORREO_MODO": "hilo"}) == "hilo"
    assert cs.proveedor_desde_entorno({**env, "CORREO_PROVEEDOR": "mailpit"}) == "graph"
    assert cs.avisar_comentarios_desde_entorno(env) is True


def test_en_render_la_ia_queda_apagada_sin_proveedor(produccion):
    produccion.delenv("ASISTENTE_PROVEEDOR", raising=False)
    assert not asistente_service.ia_activa()
    produccion.setenv("ASISTENTE_PROVEEDOR", "groq")
    assert asistente_service.nombre_proveedor() == "groq"


def test_en_render_el_hilo_del_cierre_no_arranca(produccion):
    produccion.setenv("CIERRE_AUTOMATICO", "true")
    produccion.delenv("CORREO_MODO", raising=False)
    assert cierre_service.iniciar_hilo() is False


def test_en_render_sin_blob_no_se_guardan_adjuntos_en_disco(produccion):
    produccion.delenv("BLOB_READ_WRITE_TOKEN", raising=False)
    with pytest.raises(adjuntos_service.AlmacenNoConfiguradoError):
        adjuntos_service.almacen_actual()
    produccion.setenv("BLOB_READ_WRITE_TOKEN", "vercel_blob_rw_falso")
    assert isinstance(adjuntos_service.almacen_actual(), adjuntos_service.AlmacenBlob)


def test_en_render_sin_jwt_secret_no_arranca():
    resultado = correr("import backend.main", MODO_PRODUCCION="1", DATABASE_URL="sqlite:///:memory:")
    assert resultado.returncode != 0
    assert "JWT_SECRET_KEY" in resultado.stderr
    resultado = correr("import backend.main", RENDER="true", DATABASE_URL="sqlite:///:memory:")
    assert resultado.returncode != 0


CODIGO_CLIENTE = (
    "import json\n"
    "from fastapi.testclient import TestClient\n"
    "from backend.main import app\n"
    "with TestClient(app) as c:\n"
    "    salud = c.get('/health')\n"
    "    pagina = c.get('/login')\n"
    "    silenciosa = c.get('/msal/silencioso')\n"
    "    vieja = c.get('/msal/silencioso.html', follow_redirects=False)\n"
    "    print(json.dumps({'salud': [salud.status_code, salud.json(), dict(salud.headers)],\n"
    "                      'docs': c.get('/docs').status_code,\n"
    "                      'local': c.post('/api/auth/login', json={'email': 'a@data.cr', 'password': 'x'}).status_code,\n"
    "                      'pagina': [pagina.status_code, dict(pagina.headers)],\n"
    "                      'silenciosa': [silenciosa.status_code, dict(silenciosa.headers)],\n"
    "                      'vieja': [vieja.status_code, vieja.headers.get('location')]}))\n"
)


def test_render_health_sin_docs_ni_contrasena_y_con_cabeceras(tmp_path):
    resultado = correr(CODIGO_CLIENTE, MODO_PRODUCCION="1", JWT_SECRET_KEY="x" * 40,
                       LOGIN_LOCAL="true", DATABASE_URL="sqlite:///:memory:",
                       FRONTEND_DIST=str(build_falso(tmp_path / "dist")))
    assert resultado.returncode == 0, resultado.stderr
    datos = json.loads(resultado.stdout.strip().splitlines()[-1])
    assert datos["salud"][:2] == [200, {"status": "ok"}]
    assert datos["docs"] == 404
    assert datos["local"] != 200
    assert datos["pagina"][0] == 200 and datos["silenciosa"][0] == 200
    assert datos["vieja"] == [301, "/msal/silencioso"]
    for nombre, valor in cabeceras.CABECERAS.items():
        assert datos["pagina"][1][nombre.lower()] == valor, nombre
        assert datos["salud"][2][nombre.lower()] == valor, nombre
    for nombre, valor in cabeceras.CABECERAS_SILENCIOSA.items():
        assert datos["silenciosa"][1][nombre.lower()] == valor, nombre
    assert "x-frame-options" in datos["silenciosa"][1]
    assert datos["silenciosa"][1]["x-frame-options"] == "SAMEORIGIN"


def test_docker_no_agrega_cabeceras(tmp_path):
    resultado = correr(CODIGO_CLIENTE, DATABASE_URL="sqlite:///:memory:", FRONTEND_DIST=str(build_falso(tmp_path / "dist")))
    assert resultado.returncode == 0, resultado.stderr
    datos = json.loads(resultado.stdout.strip().splitlines()[-1])
    assert "strict-transport-security" not in datos["pagina"][1]


def test_las_cabeceras_son_las_de_vercel_json():
    reglas = json.loads((RAIZ / "vercel.json").read_text())["headers"]
    por_fuente = {r["source"]: {h["key"]: h["value"] for h in r["headers"]} for r in reglas}
    assert por_fuente["/msal/silencioso"] == cabeceras.CABECERAS_SILENCIOSA
    generales = next(v for k, v in por_fuente.items() if k != "/msal/silencioso")
    assert generales == cabeceras.CABECERAS


# --- Contenedor y render.yaml -----------------------------------------------


def test_dockerfile_escucha_en_port():
    dockerfile = (RAIZ / "Dockerfile").read_text()
    assert '${PORT:-8000}' in dockerfile
    assert "--proxy-headers" in dockerfile


def test_render_yaml_sin_secretos():
    texto = (RAIZ / "render.yaml").read_text()
    assert "healthCheckPath: /health" in texto
    assert "runtime: docker" in texto and "plan: free" in texto
    assert "branch: prueba-render" in texto
    lineas = texto.splitlines()
    secretos = ("DATABASE_URL", "JWT_SECRET_KEY", "CRON_SECRET", "GROQ_API_KEY", "BLOB_READ_WRITE_TOKEN",
                "CORREO_M365_TENANT", "CORREO_M365_CLIENT_ID", "CORREO_USUARIO", "APP_URL")
    for nombre in secretos:
        i = lineas.index(f"      - key: {nombre}")
        assert lineas[i + 1].strip() == "sync: false", nombre
    i = lineas.index("      - key: MODO_PRODUCCION")
    assert lineas[i + 1].strip() == 'value: "1"'


# --- Cron del correo liviano -----------------------------------------------


def test_importar_el_correo_no_carga_adjuntos_ni_pillow():
    resultado = correr("import sys, backend.services.correo_service\n"
                       "print('backend.services.correo_adjuntos' in sys.modules, 'PIL' in sys.modules,"
                       " 'anthropic' in sys.modules)",
                       DATABASE_URL="sqlite:///:memory:")
    assert resultado.returncode == 0, resultado.stderr
    assert resultado.stdout.split() == ["False", "False", "False"]


def _pedidos_enteros(graph):
    return [ruta for metodo, ruta in graph.llamadas if metodo == "GET" and ruta.count("/") == 3]


def test_sin_correos_nuevos_solo_se_piden_las_listas(factory):
    graph = FakeGraph([])
    conteo = cs.revisar_buzon(factory, CONFIG, graph.cliente)
    assert conteo == {}
    assert [r for _, r in graph.llamadas] == ["/me/mailFolders/sentitems/messages",
                                              "/me/mailFolders/inbox/messages"]


def test_las_listas_piden_el_resumen_sin_cuerpos(factory):
    vistos = []
    graph = FakeGraph([])
    manejar = graph.manejar

    def anotar(request):
        if request.url.path.endswith("/messages"):
            vistos.append((request.url.params.get("$select"), request.url.params.get("$expand")))
        return manejar(request)

    graph.cliente._http._transport.handler = anotar
    cs.revisar_buzon(factory, CONFIG, graph.cliente)
    assert vistos == [(cs._SELECT_RESUMEN, None)] * 2
    assert "body" not in cs._SELECT_RESUMEN.split(",")


def test_enviados_ya_registrados_no_se_bajan_de_nuevo(factory, session, usuario):
    hace_poco = datetime.now(timezone.utc) + timedelta(minutes=1)
    enviados = [crear_enviado(fecha=hace_poco) for _ in range(3)]
    for e in enviados:
        session.add(ProcessedEmail(message_id=e["internetMessageId"], result="ignorado"))
    session.commit()
    graph = FakeGraph([], enviados=enviados)
    conteo = cs.revisar_enviados(factory, CONFIG, graph.cliente)
    assert conteo == {"repetido": 3}
    assert _pedidos_enteros(graph) == []


def test_no_leidos_descartados_por_la_ia_no_se_bajan(factory, session, usuario):
    correo = crear_correo(msg_id="<descartado@data.cr>")
    session.add(ProcessedEmail(message_id="<descartado@data.cr>", result=cs.NO_SOLICITUD))
    session.commit()
    graph = FakeGraph([correo])
    conteo = cs.revisar_buzon(factory, CONFIG, graph.cliente)
    assert conteo == {"visto": 1}
    assert _pedidos_enteros(graph) == []
    assert graph.mensajes[correo["id"]]["isRead"] is False


def test_un_correo_nuevo_se_baja_entero_y_crea_el_ticket(factory, usuario):
    correo = crear_correo(msg_id="<nuevo-render@data.cr>")
    graph = FakeGraph([correo])
    conteo = cs.revisar_buzon(factory, CONFIG, graph.cliente)
    assert conteo == {"ticket": 1}
    # El correo entero (y después su HTML, para las imágenes web).
    assert _pedidos_enteros(graph)[0] == f"/me/messages/{correo['id']}"
    # La segunda vez ya está movido: no se baja nada.
    graph.llamadas.clear()
    assert cs.revisar_buzon(factory, CONFIG, graph.cliente) == {}
    assert _pedidos_enteros(graph) == []


def test_el_cliente_del_cron_se_reutiliza(monkeypatch, factory):
    creados = []

    def crear(config, session_factory=None):
        creados.append(object())
        return creados[-1]

    monkeypatch.setattr(cs, "crear_cliente", crear)
    monkeypatch.setattr(cs, "_cliente_guardado", None)
    primero = cs._cliente_cron(CONFIG, factory, cs.crear_cliente)
    assert cs._cliente_cron(CONFIG, factory, cs.crear_cliente) is primero
    otra = cs.ConfigCorreo(usuario="otro@data.cr", app_url=CONFIG.app_url, filtro="todos",
                           dominio_empresa="data.cr")
    assert cs._cliente_cron(otra, factory, cs.crear_cliente) is not primero
    assert len(creados) == 2
