"""Usuarios en un navegador de verdad (Chromium headless con Playwright): clic
en «Agregar usuario», «Editar», «Desactivar» y «Reactivar» de usuarios.html
tal cual, con la API simulada en memoria (con estado: lo que se guarda
aparece en la lista). Revisa que la ventana abra, guarde y cierre, que
Escape, «Cancelar» y la ✕ la cierren, y que no haya errores en la consola.

Correr con: scripts/probar_navegador.sh   (sin Playwright se salta)
"""

import functools
import http.server
import json
import re
import threading
from pathlib import Path

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

FRONTEND = Path(__file__).resolve().parents[2]
ADMIN = {"id": 1, "name": "Ana Admin", "email": "ana@data.cr", "role": "Administrador",
         "is_active": True, "area_id": 1, "area_name": "Soporte IT"}
AREAS = [{"id": 1, "name": "Soporte IT", "is_active": True, "tecnicos": 1},
         {"id": 2, "name": "Redes e Infraestructura", "is_active": True, "tecnicos": 0}]


class _Silencioso(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def base():
    handler = functools.partial(_Silencioso, directory=str(FRONTEND))
    servidor = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{servidor.server_address[1]}"
    servidor.shutdown()


@pytest.fixture(scope="module")
def navegador():
    with sync_api.sync_playwright() as p:
        b = p.chromium.launch(args=["--disable-dev-shm-usage"])
        yield b
        b.close()


class ApiFalsa:
    """/api/users con estado; el resto responde lo mínimo."""

    def __init__(self):
        self.usuarios = [dict(ADMIN), {"id": 2, "name": "Beto Técnico", "email": "beto@data.cr",
                                       "role": "Técnico", "is_active": True, "area_id": 2,
                                       "area_name": "Redes e Infraestructura"}]
        self.pedidos = []

    def __call__(self, route):
        req = route.request
        url = req.url.split("?")[0]
        cuerpo = json.loads(req.post_data) if req.post_data else None
        self.pedidos.append((req.method, url.split("/api/")[1], cuerpo))
        responder = lambda datos, estado=200: route.fulfill(
            status=estado, content_type="application/json", body=json.dumps(datos))
        if url.endswith("/api/auth/config"):
            return responder({"tenant": "t", "client_id": "c", "login_local": False})
        if url.endswith("/api/auth/me"):
            return responder(ADMIN)
        if url.endswith("/api/areas"):
            return responder(AREAS)
        if url.endswith("/api/users") and req.method == "POST":
            if any(u["email"] == cuerpo["email"] for u in self.usuarios):
                return responder({"detail": "Ese correo electrónico ya está registrado."}, 409)
            nuevo = {"id": len(self.usuarios) + 1, "is_active": True, "area_id": cuerpo.get("area_id"),
                     "area_name": next((a["name"] for a in AREAS if a["id"] == cuerpo.get("area_id")), None),
                     **{k: cuerpo[k] for k in ("name", "email", "role")}}
            self.usuarios.append(nuevo)
            return responder(nuevo, 201)
        if url.endswith("/api/users"):
            return responder(self.usuarios)
        m = re.search(r"/api/users/(\d+)$", url)
        if m and req.method == "PATCH":
            usuario = next(u for u in self.usuarios if u["id"] == int(m.group(1)))
            usuario.update({k: v for k, v in cuerpo.items() if k in ("name", "email", "role", "is_active", "area_id")})
            if "area_id" in cuerpo:
                usuario["area_name"] = next((a["name"] for a in AREAS if a["id"] == cuerpo["area_id"]), None)
            return responder(usuario)
        return responder([])


@pytest.fixture
def pagina(navegador, base):
    ctx = navegador.new_context(viewport={"width": 1366, "height": 900})
    ctx.add_init_script(
        "localStorage.setItem('access_token', 'token-de-prueba');"
        f"localStorage.setItem('user', {json.dumps(json.dumps(ADMIN))});")
    api = ApiFalsa()
    ctx.route("**/api/**", api)
    pg = ctx.new_page()
    pg.errores = []
    pg.on("pageerror", lambda e: pg.errores.append(str(e)))
    # Los errores HTTP esperados (409) Chromium los anota como «Failed to load
    # resource»: no son errores de JavaScript.
    pg.on("console", lambda m: m.type == "error" and not m.text.startswith("Failed to load resource")
          and pg.errores.append(m.text))
    pg.api = api
    pg.goto(f"{base}/usuarios.html", wait_until="networkidle")
    pg.wait_for_selector("#tabla-usuarios:not([hidden])")
    yield pg
    assert pg.errores == [], pg.errores
    ctx.close()


def abierta(pg):
    return pg.evaluate("document.getElementById('dialogo-usuario').open")


def fila(pg, nombre):
    return pg.locator("#cuerpo-usuarios tr", has_text=nombre)


def test_agregar_abre_guarda_y_cierra(pagina):
    pagina.get_by_role("button", name="Agregar usuario").click()
    assert abierta(pagina)
    assert pagina.inner_text("#dialogo-usuario-titulo") == "Agregar usuario"
    assert pagina.is_visible("#form-usuario") and not pagina.is_visible("#form-editar-usuario")
    assert pagina.evaluate("document.activeElement.id") == "nombre"
    assert pagina.get_attribute("#email", "placeholder") == "nombre@data.cr"
    pagina.fill("#nombre", "Carla Nueva")
    pagina.fill("#email", "carla@data.cr")
    pagina.select_option("#rol", "Técnico")
    pagina.select_option("#area", "2")
    pagina.locator("#form-usuario").get_by_role("button", name="Agregar usuario").click()
    pagina.wait_for_function("!document.getElementById('dialogo-usuario').open")
    assert ("POST", "users", {"name": "Carla Nueva", "email": "carla@data.cr", "role": "Técnico", "area_id": 2}) in pagina.api.pedidos
    sync_api.expect(fila(pagina, "Carla Nueva")).to_have_count(1)
    sync_api.expect(pagina.locator("#avisos .aviso.exito .aviso-texto")).to_have_text("Usuario agregado correctamente.")


def test_agregar_con_error_queda_abierta_y_lo_muestra(pagina):
    pagina.click("#abrir-agregar-usuario")
    pagina.fill("#nombre", "Otra Ana")
    pagina.fill("#email", "ana@data.cr")
    pagina.locator("#form-usuario").get_by_role("button", name="Agregar usuario").click()
    pagina.wait_for_selector("#error-email:not([hidden])")
    assert abierta(pagina)
    assert pagina.inner_text("#error-email") == "Ese correo electrónico ya está registrado."


def test_escape_cancelar_y_la_x_cierran(pagina):
    for cerrar in (lambda: pagina.keyboard.press("Escape"),
                   lambda: pagina.locator("#form-usuario").get_by_role("button", name="Cancelar").click(),
                   lambda: pagina.get_by_role("button", name="Cerrar").click()):
        pagina.click("#abrir-agregar-usuario")
        assert abierta(pagina)
        cerrar()
        assert not abierta(pagina)
    fila(pagina, "Beto Técnico").get_by_role("button", name="Editar").click()
    assert abierta(pagina)
    pagina.locator("#form-editar-usuario").get_by_role("button", name="Cancelar").click()
    assert not abierta(pagina)
    assert not any(m == "POST" or m == "PATCH" for m, _, _ in pagina.api.pedidos), "cerrar no guarda"


def test_editar_abre_con_los_datos_guarda_y_cierra(pagina):
    fila(pagina, "Beto Técnico").get_by_role("button", name="Editar").click()
    assert abierta(pagina)
    assert pagina.inner_text("#dialogo-usuario-titulo") == "Editar usuario"
    assert pagina.is_visible("#form-editar-usuario") and not pagina.is_visible("#form-usuario")
    assert pagina.input_value("#editar-nombre") == "Beto Técnico"
    assert pagina.input_value("#editar-email") == "beto@data.cr"
    assert pagina.input_value("#editar-rol") == "Técnico"
    assert pagina.input_value("#editar-area") == "2"
    pagina.fill("#editar-nombre", "Beto Técnico Mora")
    pagina.select_option("#editar-area", "1")
    pagina.get_by_role("button", name="Guardar cambios").click()
    pagina.wait_for_function("!document.getElementById('dialogo-usuario').open")
    assert ("PATCH", "users/2", {"name": "Beto Técnico Mora", "email": "beto@data.cr", "role": "Técnico", "area_id": 1}) in pagina.api.pedidos
    sync_api.expect(fila(pagina, "Beto Técnico Mora")).to_contain_text("Soporte IT")
    sync_api.expect(pagina.locator("#avisos .aviso.exito .aviso-texto")).to_have_text("Usuario actualizado correctamente.")


def test_desactivar_con_confirmacion_y_reactivar(pagina):
    fila(pagina, "Beto Técnico").get_by_role("button", name="Desactivar").click()
    pagina.locator(".dialogo").get_by_role("button", name="Desactivar").click()
    sync_api.expect(pagina.locator("#avisos .aviso-texto").last).to_have_text("Beto Técnico fue desactivado.")
    assert ("PATCH", "users/2", {"is_active": False}) in pagina.api.pedidos
    sync_api.expect(fila(pagina, "Beto Técnico")).to_contain_text("Inactivo")
    fila(pagina, "Beto Técnico").get_by_role("button", name="Reactivar").click()
    sync_api.expect(pagina.locator("#avisos .aviso-texto").last).to_have_text("Beto Técnico fue reactivado.")
    assert ("PATCH", "users/2", {"is_active": True}) in pagina.api.pedidos
    sync_api.expect(fila(pagina, "Beto Técnico").locator(".badge-activo")).to_have_text("Activo")


def test_nadie_se_desactiva_a_si_mismo(pagina):
    assert fila(pagina, "Ana Admin").get_by_role("button", name="Desactivar").count() == 0


def test_scripts_con_version_y_en_orden(pagina):
    orden = pagina.evaluate("[...document.scripts].map(s => s.getAttribute('src'))")
    propios = [s for s in orden if s and s.startswith("js/")]
    assert all(re.fullmatch(r"js/[a-z]+\.js\?v=[\w-]+", s) for s in propios), propios
    nombres = [s.split("?")[0] for s in propios]
    assert nombres.index("js/auth.js") < nombres.index("js/usuarios.js")
    assert pagina.evaluate("typeof abrirAgregarUsuario") == "function"
