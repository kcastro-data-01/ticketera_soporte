"""Departamentos en un navegador de verdad (Chromium headless con
Playwright): la lista (filas de 56 px con el nombre arriba y «N abiertos»
debajo, la pastilla a la derecha, barrita de 3 px pegada abajo, «Sin
departamento» último; la tarjeta al alto del detalle), y debajo de 900 px la fila de
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
def test_cada_departamento_con_nombre_arriba_abiertos_abajo_y_la_barrita(navegador, base, tema):
    ctx, pg = abrir(navegador, base, 1280, tema)
    try:
        botones = cajas(pg)
        assert [b["texto"] for b in botones][-1] == "Sin departamento"
        for b in botones:
            assert b["alto"] == pytest.approx(56, abs=0.5), b
            assert b["nombre"][1] <= b["abiertos"][0], "«N abiertos» debajo del nombre"
            assert abs(b["nombre"][2] - b["abiertos"][2]) < 1, "alineados a la izquierda"
            assert b["pastilla"][2] > max(b["nombre"][3], b["abiertos"][3]), "la pastilla a la derecha"
            centro = (b["top"] + b["bottom"] - 3) / 2  # sin la barrita
            assert (b["pastilla"][0] + b["pastilla"][1]) / 2 == pytest.approx(centro, abs=1.5), "pastilla centrada"
            assert (b["nombre"][0] + b["abiertos"][1]) / 2 == pytest.approx(centro, abs=1.5), "texto centrado"
            assert b["barra"][4] == 3, b
            assert abs(b["barra"][1] - b["bottom"]) < 0.5, "pegada al borde de abajo"
        # filas seguidas, sin espacio entre ellas
        for arriba, abajo in zip(botones, botones[1:]):
            assert abs(abajo["top"] - arriba["bottom"]) < 0.5
        separador = pg.evaluate("""[...document.querySelectorAll('.depto-boton')].map(b =>
            [getComputedStyle(b).borderTopWidth, getComputedStyle(b).borderTopColor])""")
        assert separador[-1][0] == "1px" and separador[-1][1] != separador[1][1], separador
        assert pg.errores == []
    finally:
        ctx.close()


@pytest.mark.parametrize("ancho", [1366, 1920])
@pytest.mark.parametrize("tema", ["claro", "oscuro"])
def test_la_tarjeta_llega_hasta_abajo_con_filas_de_56_px(navegador, base, ancho, tema):
    ctx, pg = abrir(navegador, base, ancho, tema)
    try:
        m = pg.evaluate("""(() => {
            const r = (s) => document.querySelector(s).getBoundingClientRect();
            const col = r('.deptos-columna'), det = r('#deptos-detalle'), lista = r('#deptos-lista'),
                  main = r('main'), app = r('.app-principal');
            const filas = [...document.querySelectorAll('.depto-boton')].map(b => {
                const f = b.getBoundingClientRect(), n = b.querySelector('.depto-boton-nombre').getBoundingClientRect(),
                      p = b.querySelector('.depto-pastilla').getBoundingClientRect(), barra = b.querySelector('.depto-barra').getBoundingClientRect();
                return { top: f.top, bottom: f.bottom, alto: f.height, centroFila: (f.top + f.bottom) / 2,
                         centroNombre: (n.top + n.bottom) / 2, centroPastilla: (p.top + p.bottom) / 2, barraBottom: barra.bottom };
            });
            return { col: [col.top, col.bottom], det: [det.top, det.bottom], lista: [lista.top, lista.bottom],
                     filas, alto: window.innerHeight, margenes: [main.left - app.left, app.right - main.right] };
        })()""")
        assert m["col"] == pytest.approx(m["det"], abs=0.5), "mismo alto que el detalle"
        assert m["col"][1] >= m["alto"] - 34, "como mínimo hasta abajo de la pantalla (menos el margen)"
        filas = m["filas"]
        assert filas[0]["top"] == pytest.approx(m["col"][0] + 1, abs=0.5), "los departamentos arriba"
        assert [round(f["alto"]) for f in filas] == [56] * len(filas), "alto fijo, no se estiran"
        assert m["col"][1] - filas[-1]["bottom"] > 100, "lo que sobra queda debajo, dentro de la tarjeta"
        assert m["lista"][1] == pytest.approx(m["col"][1] - 1, abs=0.5), "la lista ocupa la tarjeta (mismo fondo)"
        for f in filas:
            assert f["barraBottom"] == pytest.approx(f["bottom"], abs=0.5), "la barrita pegada abajo"
        fondos = pg.evaluate("""[getComputedStyle(document.querySelector('.deptos-columna')).backgroundColor,
            getComputedStyle(document.querySelector('#deptos-detalle')).backgroundColor,
            getComputedStyle(document.querySelector('#deptos-lista')).backgroundColor]""")
        assert fondos[0] == fondos[1] and fondos[2] == "rgba(0, 0, 0, 0)", fondos
        tamanos = pg.evaluate("""[getComputedStyle(document.body).fontSize,
            getComputedStyle(document.querySelector('.depto-boton-nombre')).fontSize]""")
        assert tamanos[0] == tamanos[1] == "14px", "letra normal de la app"
        assert m["margenes"] == [0, 0], "todo el ancho"
        assert pg.evaluate("document.querySelector('.deptos-resumen')") is None, "sin el resumen"
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
            const r = document.querySelector('.deptos-columna').getBoundingClientRect();
            return { ori: l.getAttribute('aria-orientation'), bottom: r.bottom, width: r.width,
                     scroll: l.scrollWidth, cliente: l.clientWidth, detalleTop: d.top, detalleAncho: d.width,
                     pagina: document.documentElement.scrollWidth, ventana: window.innerWidth }; })()""")
        assert lista["ori"] == "horizontal"
        assert lista["detalleTop"] >= lista["bottom"], "el detalle debajo"
        assert abs(lista["detalleAncho"] - lista["width"]) < 1, "el detalle a todo el ancho"
        assert lista["pagina"] <= lista["ventana"], "sin scroll de costado en la página"
        alto_boton = pg.evaluate("document.querySelector('.depto-boton').getBoundingClientRect().height")
        assert round(alto_boton) == 56, "en el celular, el mismo alto fijo"
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
