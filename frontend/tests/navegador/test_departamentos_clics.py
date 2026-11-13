"""Departamentos en un navegador de verdad (Chromium headless con
Playwright): la lista compacta (una línea por departamento, barrita de 3 px
pegada abajo, «Sin departamento» último), y debajo de 900 px la fila de
botones horizontal con scroll propio sin scroll de costado en la página.

Sirve la carpeta frontend tal cual y responde la API con datos de mentira.
Correr con:

    scripts/probar_navegador.sh -k departamentos

Con ``CAPTURAS=/carpeta`` guarda capturas de pantalla. Sin Playwright
instalado se salta.
"""

import functools
import http.server
import json
import os
import threading
from pathlib import Path

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

FRONTEND = Path(__file__).resolve().parents[2]
USUARIO = {"id": 1, "name": "Ana Admin", "email": "ana@data.cr", "role": "Administrador"}


def _fila(area_id, nombre, estados, atiende="", tecnicos=(), tickets=()):
    return {
        "area_id": area_id, "nombre": nombre, "atiende": atiende,
        "total": sum(estados), "abiertos": estados[0] + estados[1],
        "por_estado": dict(zip(["Nuevo", "En proceso", "Resuelto", "Cerrado"], estados)),
        "tecnicos": list(tecnicos), "tickets_abiertos": list(tickets),
    }


RESUMEN = {
    "total_abiertos": 9,
    "mas_abiertos": {"area_id": 1, "nombre": "Soporte IT", "abiertos": 5},
    "departamentos": [
        _fila(1, "Soporte IT", [3, 2, 4, 6], "computadoras, impresoras, programas",
              [{"id": 7, "name": "Ana Mora", "abiertos": 3, "resueltos_mes": 4}],
              [{"id": 21, "title": "Impresora trabada en el segundo piso", "state": "En proceso",
                "priority": "Crítica", "assigned_to_name": "Ana Mora", "created_at": "2026-11-01T10:00:00Z"}]),
        _fila(2, "Redes e Infraestructura", [1, 1, 0, 2], "internet, wifi, servidores, VPN"),
        _fila(3, "Ciberseguridad", [0, 0, 0, 0], "accesos, contraseñas"),
        _fila(4, "Programación", [2, 0, 1, 0], "sistemas internos, Odoo"),
        _fila(None, "Sin departamento", [0, 0, 0, 3], "tickets que todavía no tienen departamento"),
    ],
}


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


def abrir(navegador, base, ancho, tema="claro"):
    ctx = navegador.new_context(viewport={"width": ancho, "height": 900})
    ctx.add_init_script(
        "localStorage.setItem('access_token', 'token-de-prueba');"
        f"localStorage.setItem('user', {json.dumps(json.dumps(USUARIO))});"
        + ("localStorage.setItem('tema', 'oscuro');" if tema == "oscuro" else ""))

    def api(route):
        url = route.request.url
        cuerpo = USUARIO if url.endswith("/api/auth/me") else RESUMEN if "/api/departamentos/resumen" in url else []
        route.fulfill(status=200, content_type="application/json", body=json.dumps(cuerpo))

    ctx.route("**/api/**", api)
    pg = ctx.new_page()
    pg.errores = []
    pg.on("pageerror", lambda e: pg.errores.append(str(e)))
    pg.goto(f"{base}/departamentos.html", wait_until="networkidle")
    pg.wait_for_selector(".depto-boton")
    carpeta = os.environ.get("CAPTURAS")
    if carpeta:
        pg.screenshot(path=f"{carpeta}/departamentos-{ancho}-{tema}.png", full_page=True)
    return ctx, pg


def cajas(pg):
    return pg.evaluate("""[...document.querySelectorAll('.depto-boton')].map(b => {
        const r = b.getBoundingClientRect();
        const caja = (s) => { const e = b.querySelector(s).getBoundingClientRect(); return [e.top, e.bottom, e.left, e.right, e.height]; };
        return { alto: r.height, top: r.top, bottom: r.bottom, left: r.left,
                 nombre: caja('.depto-boton-nombre'), abiertos: caja('.depto-boton-abiertos'),
                 pastilla: caja('.depto-pastilla'), barra: caja('.depto-barra'),
                 texto: b.querySelector('.depto-boton-nombre').textContent };
    })""")


@pytest.mark.parametrize("tema", ["claro", "oscuro"])
def test_cada_departamento_en_una_linea_con_la_barrita_abajo(navegador, base, tema):
    ctx, pg = abrir(navegador, base, 1280, tema)
    try:
        botones = cajas(pg)
        assert [b["texto"] for b in botones][-1] == "Sin departamento"
        for b in botones:
            assert b["alto"] < 44, b  # una sola línea, 9 px arriba y abajo
            # nombre, «N abiertos» y pastilla en la misma línea, en ese orden
            assert b["nombre"][3] <= b["abiertos"][2] < b["pastilla"][2], b
            assert abs(b["nombre"][0] - b["abiertos"][0]) < 8 and abs(b["abiertos"][1] - b["pastilla"][1]) < 8, b
            assert b["barra"][4] == 3, b
            assert abs(b["barra"][1] - b["bottom"]) < 0.5, "pegada al borde de abajo"
        # filas seguidas, sin espacio extra entre ellas
        for arriba, abajo in zip(botones, botones[1:]):
            assert abs(abajo["top"] - arriba["bottom"]) < 0.5
        separador = pg.evaluate("""[...document.querySelectorAll('.depto-boton')].map(b =>
            [getComputedStyle(b).borderTopWidth, getComputedStyle(b).borderTopColor])""")
        assert separador[-1][0] == "1px" and separador[-1][1] != separador[1][1], separador
        assert pg.errores == []
    finally:
        ctx.close()


@pytest.mark.parametrize("ancho", [880, 375])
def test_angosto_la_lista_es_una_fila_horizontal_con_scroll_propio(navegador, base, ancho):
    ctx, pg = abrir(navegador, base, ancho)
    try:
        botones = cajas(pg)
        assert len({round(b["top"]) for b in botones}) == 1, "todos en una fila"
        lista = pg.evaluate("""(() => { const l = document.getElementById('deptos-lista');
            const d = document.getElementById('deptos-detalle').getBoundingClientRect();
            const r = l.getBoundingClientRect();
            return { ori: l.getAttribute('aria-orientation'), bottom: r.bottom, width: r.width,
                     scroll: l.scrollWidth, cliente: l.clientWidth, detalleTop: d.top, detalleAncho: d.width,
                     pagina: document.documentElement.scrollWidth, ventana: window.innerWidth }; })()""")
        assert lista["ori"] == "horizontal"
        assert lista["detalleTop"] >= lista["bottom"], "el detalle debajo"
        assert abs(lista["detalleAncho"] - lista["width"]) < 1, "el detalle a todo el ancho"
        assert lista["pagina"] <= lista["ventana"], "sin scroll de costado en la página"
        if ancho == 375:
            assert lista["scroll"] > lista["cliente"], "los botones no entran: scroll dentro de la fila"
        # Con el teclado, el elegido se ve dentro de la fila.
        pg.focus(".depto-boton.elegido")
        pg.keyboard.press("End")
        assert pg.evaluate("document.activeElement.textContent").startswith("Sin departamento")
        visible = pg.evaluate("""(() => { const l = document.getElementById('deptos-lista').getBoundingClientRect();
            const b = document.activeElement.getBoundingClientRect(); return b.right <= l.right + 1; })()""")
        assert visible
        assert pg.errores == []
    finally:
        ctx.close()
