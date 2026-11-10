"""Ayuda en un navegador de verdad (Chromium headless con Playwright): clic
en cada botón de «Temas», ayuda.html#correo, un enlace a un tema estando en
la ayuda (como uno del chat), el teclado y cómo se carga ayuda.js.

Sirve la carpeta frontend tal cual (los mismos HTML, CSS y JS que la app) y
responde la API con datos de mentira. Correr con:

    scripts/probar_navegador.sh

(usa la imagen mcr.microsoft.com/playwright/python). Sin Playwright instalado
se salta.
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
TEMAS = [
    ("crear", "Crear un ticket"),
    ("lista", "La lista de tickets"),
    ("seguimiento", "Seguimiento"),
    ("areas", "Departamentos"),
    ("roles", "Roles y permisos"),
    ("adjuntos", "Adjuntos"),
    ("correo", "Tickets por correo"),
    ("avisos", "Avisos por correo"),
    ("asistente", "Asistente virtual"),
    ("faq", "Preguntas frecuentes"),
]
USUARIO = {"id": 1, "name": "Ana Admin", "email": "ana@data.cr", "role": "Administrador"}


class _Silencioso(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def base():
    handler = functools.partial(_Silencioso, directory=str(FRONTEND))
    servidor = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()
    yield f"http://127.0.0.1:{servidor.server_address[1]}"
    servidor.shutdown()


@pytest.fixture(scope="module")
def navegador():
    with sync_api.sync_playwright() as p:
        b = p.chromium.launch(args=["--disable-dev-shm-usage"])
        yield b
        b.close()


@pytest.fixture
def pagina(navegador, base):
    ctx = navegador.new_context(viewport={"width": 1280, "height": 900})
    ctx.add_init_script(
        f"localStorage.setItem('access_token', 'token-de-prueba');"
        f"localStorage.setItem('user', {json.dumps(json.dumps(USUARIO))});")

    def api(route):
        cuerpo = USUARIO if route.request.url.endswith("/api/auth/me") else []
        route.fulfill(status=200, content_type="application/json", body=json.dumps(cuerpo))

    ctx.route("**/api/**", api)
    pg = ctx.new_page()
    pg.errores = []
    pg.on("pageerror", lambda e: pg.errores.append(str(e)))
    pg.scripts = {}
    pg.on("response", lambda r: "/js/" in r.url and pg.scripts.__setitem__(r.url.split("/js/")[1], r.status))
    pg.base = base
    yield pg
    ctx.close()


def visibles(pg):
    return pg.evaluate("[...document.querySelectorAll('.ayuda-tema')].filter(p => !p.hidden).map(p => p.id)")


def elegidas(pg):
    return pg.evaluate("[...document.querySelectorAll('.ayuda-temas [aria-selected=true]')].map(t => t.textContent)")


def abrir(pg, sufijo=""):
    pg.goto(f"{pg.base}/ayuda.html{sufijo}", wait_until="networkidle")


def test_ayuda_js_se_carga_diferido_con_version_y_sin_errores(pagina):
    abrir(pagina)
    src = pagina.evaluate("document.querySelector('script[src*=\"js/ayuda.js\"]').getAttribute('src')")
    assert re.fullmatch(r"js/ayuda\.js\?v=[\w-]+", src), src
    assert pagina.evaluate("document.querySelector('script[src*=\"js/ayuda.js\"]').defer") is True
    assert pagina.scripts.get(src.split("js/")[1]) == 200
    orden = pagina.evaluate("[...document.scripts].map(s => s.getAttribute('src'))")
    assert orden.index("js/auth.js") < orden.index(src), "auth.js antes que ayuda.js"
    assert pagina.evaluate("typeof iniciarAyuda") == "function"
    assert pagina.errores == []


def test_al_entrar_se_ve_crear_un_ticket(pagina):
    abrir(pagina)
    assert visibles(pagina) == ["tema-crear"]
    assert elegidas(pagina) == ["Crear un ticket"]


def test_clic_en_cada_boton_muestra_su_tema_lo_marca_y_cambia_la_direccion(pagina):
    abrir(pagina)
    fondo_normal = pagina.get_by_role("tab", name="Seguimiento").evaluate("b => getComputedStyle(b).backgroundColor")
    for id_, nombre in [*TEMAS[1:], TEMAS[0]]:
        boton = pagina.get_by_role("tab", name=nombre, exact=True)
        boton.click()
        assert visibles(pagina) == [f"tema-{id_}"], nombre
        assert elegidas(pagina) == [nombre]
        assert boton.get_attribute("aria-selected") == "true"
        assert boton.get_attribute("tabindex") == "0"
        assert pagina.url.endswith(f"#{id_}"), pagina.url
        fondo = boton.evaluate("b => getComputedStyle(b).backgroundColor")
        assert fondo != fondo_normal, f"«{nombre}» marcado con otro fondo"
        texto = pagina.locator(f"#tema-{id_}").inner_text()
        assert len(texto) > 40, f"«{nombre}» con contenido visible"
    assert pagina.errores == []


def test_direccion_con_tema_abre_ese_y_las_pestanas_quedan_a_la_vista(pagina):
    abrir(pagina, "#correo")
    assert visibles(pagina) == ["tema-correo"]
    assert elegidas(pagina) == ["Tickets por correo"]
    assert pagina.evaluate("window.scrollY") == 0, "no salta hasta el panel"
    assert pagina.get_by_role("tab", name="Tickets por correo").is_visible()


def test_enlace_a_un_tema_estando_en_la_ayuda_como_uno_del_chat(pagina):
    abrir(pagina)
    pagina.evaluate("""() => {
        const a = document.createElement('a');
        a.className = 'chat-enlace';
        a.id = 'enlace-de-prueba';
        a.href = 'ayuda.html#faq';
        a.textContent = 'Preguntas frecuentes';
        document.body.appendChild(a);
    }""")
    pagina.click("#enlace-de-prueba")
    pagina.wait_for_function("!document.getElementById('tema-faq').hidden")
    assert visibles(pagina) == ["tema-faq"]
    assert elegidas(pagina) == ["Preguntas frecuentes"]


def test_desde_otra_pagina_un_enlace_a_un_tema_lo_abre(pagina):
    pagina.goto(f"{pagina.base}/index.html", wait_until="networkidle")
    pagina.evaluate("""() => {
        const a = document.createElement('a');
        a.id = 'enlace-de-prueba';
        a.href = 'ayuda.html#adjuntos';
        a.textContent = 'Adjuntos';
        document.body.appendChild(a);
    }""")
    pagina.click("#enlace-de-prueba")
    pagina.wait_for_load_state("networkidle")
    assert visibles(pagina) == ["tema-adjuntos"]


def test_teclado_flechas_inicio_y_fin(pagina):
    abrir(pagina)
    pagina.get_by_role("tab", name="Crear un ticket").focus()
    pagina.keyboard.press("ArrowRight")
    assert visibles(pagina) == ["tema-lista"]
    assert pagina.evaluate("document.activeElement.textContent") == "La lista de tickets"
    pagina.keyboard.press("End")
    assert visibles(pagina) == ["tema-faq"]
    pagina.keyboard.press("Home")
    assert visibles(pagina) == ["tema-crear"]
    pagina.keyboard.press("ArrowLeft")
    assert visibles(pagina) == ["tema-faq"]
    assert pagina.url.endswith("#faq")


def test_celular_dos_columnas_y_el_tema_debajo(navegador, base):
    ctx = navegador.new_context(viewport={"width": 390, "height": 844})
    ctx.add_init_script(f"localStorage.setItem('access_token', 'x'); localStorage.setItem('user', {json.dumps(json.dumps(USUARIO))});")
    ctx.route("**/api/**", lambda r: r.fulfill(status=200, content_type="application/json", body="[]"))
    pg = ctx.new_page()
    pg.goto(f"{base}/ayuda.html", wait_until="networkidle")
    cajas = [b.bounding_box() for b in pg.locator(".ayuda-temas [role=tab]").all()]
    assert len({round(c["x"]) for c in cajas}) == 2, "2 columnas"
    pg.get_by_role("tab", name="Adjuntos").click()
    panel = pg.locator("#tema-adjuntos").bounding_box()
    assert panel["y"] > max(c["y"] + c["height"] for c in cajas), "el tema queda debajo"
    ctx.close()
