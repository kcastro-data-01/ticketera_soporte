"""Aviso por inactividad en un navegador de verdad (Chromium headless con
Playwright), con el reloj del navegador adelantado a mano: «¿Sigue ahí?» a los
30 minutos, «Seguir conectado», «Cerrar sesión», la cuenta que llega a cero y
dos pestañas de la misma ticketera (comparten localStorage). La API es
simulada; MSAL es el de verdad (con hash de integridad no se puede
reemplazar), sin cuenta conectada.

Correr con: scripts/probar_navegador.sh -k sesion   (sin Playwright se salta)
"""

import base64
import functools
import http.server
import json
import re
import threading
from datetime import datetime, timezone
from pathlib import Path

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

FRONTEND = Path(__file__).resolve().parents[2]
USUARIO = {"id": 1, "name": "Karla Sánchez", "email": "ksanchez@data.cr", "role": "Técnico",
           "is_active": True, "area_id": 1, "area_name": "Soporte IT"}
INICIO = datetime(2026, 11, 11, 9, 0, tzinfo=timezone.utc)


def token(emitido, dura=3600):
    """Un token con la forma de los del servidor (la firma no se revisa aquí)."""
    b64 = lambda o: base64.urlsafe_b64encode(json.dumps(o).encode()).decode().rstrip("=")
    s = int(emitido.timestamp())
    datos = {"sub": "1", "role": "Técnico", "iat": s, "exp": s + dura,
             "ini": int(INICIO.timestamp()), "max": int(INICIO.timestamp()) + 10 * 3600}
    return f"{b64({'alg': 'HS256'})}.{b64(datos)}.firma"


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


@pytest.fixture
def ctx(navegador):
    """Un navegador con sesión iniciada y el reloj detenido en INICIO."""
    contexto = navegador.new_context(viewport={"width": 1366, "height": 900})
    contexto.renovaciones = 0

    def api(route):
        url = route.request.url.split("?")[0]
        if url.endswith("/api/auth/renovar"):
            contexto.renovaciones += 1
            # El reloj del navegador es falso: el token nuevo vale una hora más.
            nuevo = token(INICIO, dura=3 * 3600)
            return route.fulfill(status=200, content_type="application/json",
                                 body=json.dumps({"access_token": nuevo, "token_type": "bearer",
                                                  "expires_in": 3600}))
        if url.endswith("/api/auth/config"):
            return route.fulfill(status=200, content_type="application/json",
                                 body=json.dumps({"tenant": "t", "client_id": "c", "login_local": False,
                                                  "sesion_maxima_horas": 10}))
        if url.endswith("/api/auth/me"):
            return route.fulfill(status=200, content_type="application/json", body=json.dumps(USUARIO))
        if url.endswith("/api/tickets/summary"):
            return route.fulfill(status=200, content_type="application/json", body=json.dumps({"mios_abiertos": 0}))
        return route.fulfill(status=200, content_type="application/json", body="[]")

    contexto.route("**/api/**", api)
    contexto.route("https://fonts.googleapis.com/**", lambda r: r.fulfill(status=200, body=""))
    contexto.route("https://cdnjs.cloudflare.com/**", lambda r: r.fulfill(status=200, body=""))
    contexto.clock.install(time=INICIO)
    contexto.add_init_script(
        "if (!sessionStorage.getItem('sembrado')) { sessionStorage.setItem('sembrado', '1');"
        f" if (!localStorage.getItem('sesion_cierre')) {{ localStorage.setItem('access_token', {json.dumps(token(INICIO))});"
        f" localStorage.setItem('user', {json.dumps(json.dumps(USUARIO))}); }} }}")
    yield contexto
    contexto.close()


def abrir(ctx, base, pagina="index.html"):
    pg = ctx.new_page()
    pg.errores = []
    pg.on("pageerror", lambda e: pg.errores.append(str(e)))
    pg.goto(f"{base}/{pagina}", wait_until="load")
    pg.wait_for_selector(".menu-usuario")
    return pg


def aviso(pg):
    return pg.locator(".dialogo-sesion [role=alertdialog]")


def test_a_los_30_minutos_avisa_y_cuenta_hacia_atras(ctx, base):
    pg = abrir(ctx, base)
    pg.clock.run_for("29:00")
    sync_api.expect(aviso(pg)).to_have_count(0)
    pg.clock.run_for("01:01")
    sync_api.expect(aviso(pg)).to_be_visible()
    sync_api.expect(aviso(pg).locator(".dialogo-titulo")).to_have_text("¿Sigue ahí?")
    sync_api.expect(aviso(pg).locator(".dialogo-mensaje")).to_have_text(
        "Su sesión se cerrará por inactividad. ¿Desea seguir conectado?")
    tiempo = aviso(pg).locator(".dialogo-cuenta-tiempo")
    sync_api.expect(tiempo).to_have_text(re.compile(r"^1:[45]\d$"))
    assert pg.evaluate("document.activeElement.textContent") == "Seguir conectado"
    segundos = lambda: (lambda m, s: int(m) * 60 + int(s))(*tiempo.inner_text().split(":"))
    antes = segundos()
    pg.clock.run_for("00:30")
    pg.wait_for_function(f"() => {{ const [m, s] = document.querySelector('.dialogo-cuenta-tiempo')"
                         f".textContent.split(':'); return m * 60 + +s <= {antes - 30}; }}")
    assert pg.errores == []


def test_seguir_conectado_renueva_y_vuelve_a_contar(ctx, base):
    pg = abrir(ctx, base)
    pg.clock.run_for("30:01")
    aviso(pg).get_by_role("button", name="Seguir conectado").click()
    sync_api.expect(aviso(pg)).to_have_count(0)
    assert ctx.renovaciones >= 1
    pg.clock.run_for("29:00")
    sync_api.expect(aviso(pg)).to_have_count(0)
    assert pg.errores == []


def test_la_actividad_vuelve_a_empezar_los_30_minutos(ctx, base):
    pg = abrir(ctx, base)
    pg.clock.run_for("20:00")
    pg.mouse.move(300, 300)
    pg.mouse.move(320, 340)
    pg.clock.run_for("20:00")
    sync_api.expect(aviso(pg)).to_have_count(0)
    pg.keyboard.press("Shift")
    pg.clock.run_for("29:00")
    sync_api.expect(aviso(pg)).to_have_count(0)


def test_si_llega_a_cero_va_al_login_por_inactividad(ctx, base):
    pg = abrir(ctx, base)
    pg.clock.run_for("32:02")
    pg.wait_for_url("**/login.html")
    sync_api.expect(pg.locator("#auth-success")).to_have_text("Su sesión se cerró por inactividad.")
    assert pg.evaluate("localStorage.getItem('access_token')") is None


def test_dos_pestanas_seguir_conectado_en_una_cierra_el_aviso_en_la_otra(ctx, base):
    a = abrir(ctx, base, "index.html")
    b = abrir(ctx, base, "ayuda.html")
    a.clock.run_for("30:01")
    sync_api.expect(aviso(a)).to_be_visible()
    sync_api.expect(aviso(b)).to_be_visible()
    aviso(a).get_by_role("button", name="Seguir conectado").click()
    sync_api.expect(aviso(a)).to_have_count(0)
    sync_api.expect(aviso(b)).to_have_count(0)


def test_dos_pestanas_la_actividad_en_una_cuenta_para_la_otra(ctx, base):
    a = abrir(ctx, base, "index.html")
    b = abrir(ctx, base, "ayuda.html")
    a.clock.run_for("25:00")
    b.mouse.move(200, 200)
    b.mouse.move(260, 240)
    a.clock.run_for("25:00")
    sync_api.expect(aviso(a)).to_have_count(0)


def test_dos_pestanas_cerrar_sesion_en_una_cierra_en_las_dos(ctx, base):
    a = abrir(ctx, base, "index.html")
    b = abrir(ctx, base, "ayuda.html")
    a.clock.run_for("30:01")
    aviso(a).get_by_role("button", name="Cerrar sesión").click()
    a.wait_for_url("**/login.html")
    b.wait_for_url("**/login.html")


def test_ventana_formal_en_claro_y_en_oscuro(ctx, base):
    pg = abrir(ctx, base)
    pg.clock.run_for("30:01")
    caja = aviso(pg)
    sync_api.expect(caja).to_be_visible()
    claro = caja.evaluate("e => getComputedStyle(e).backgroundColor")
    pg.evaluate("document.documentElement.setAttribute('data-tema', 'oscuro')")
    oscuro = caja.evaluate("e => getComputedStyle(e).backgroundColor")
    assert claro != oscuro
    assert caja.evaluate("e => getComputedStyle(e).borderRadius") != "0px"
