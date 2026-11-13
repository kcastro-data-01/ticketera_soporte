"""Historial por persona en un navegador de verdad (Chromium headless con
Playwright): mismas tarjetas y filas de 64 px que Departamentos, el círculo
de iniciales, la tarjeta de la lista al alto del detalle, los cambios
agrupados por día, «Ver más», la persona y el período en la dirección, el
teclado y, en el celular, la lista arriba y el detalle debajo sin scroll de
costado.

Sirve la carpeta frontend tal cual y responde la API con datos de mentira.
Correr con:

    scripts/probar_navegador.sh -k historial

Con ``CAPTURAS=/carpeta`` guarda capturas de pantalla. Sin Playwright
instalado se salta.
"""

import functools
import http.server
import json
import os
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

FRONTEND = Path(__file__).resolve().parents[2]
USUARIO = {"id": 1, "name": "Ana Admin", "email": "ana@data.cr", "role": "Administrador"}

PERSONAS = [
    {"clave": "12", "user_id": 12, "nombre": "Daniel Alejandro Sáenz Maroto", "rol": "Técnico",
     "departamento": "Redes e Infraestructura", "cambios": 60},
    {"clave": "1", "user_id": 1, "nombre": "Ana Admin", "rol": "Administrador", "departamento": None, "cambios": 8},
    {"clave": "30", "user_id": 30, "nombre": "Sofía Solicitante", "rol": "Solicitante", "departamento": None, "cambios": 2},
    {"clave": "sistema", "user_id": None, "nombre": "Sistema", "rol": "Cambios automáticos", "departamento": None, "cambios": 1},
]

AHORA = datetime.now(timezone.utc)
FRASES = [
    ("commented", "comment", None, "Ya revisé el cable de red, sigue sin conexión"),
    ("Cambio de estado", "state", "Nuevo", "En proceso"),
    ("assigned", "assigned_to_id", None, "Daniel Alejandro Sáenz Maroto"),
    ("area_changed", "area", None, "Redes e Infraestructura"),
    ("attachment_added", "adjunto", None, "foto-del-router.jpg"),
]


def _cambios(persona, cantidad):
    autor = next((p for p in PERSONAS if p["clave"] == persona), PERSONAS[0])
    filas = []
    for i in range(cantidad):
        accion, campo, antes, despues = FRASES[i % len(FRASES)]
        filas.append({
            "id": 5000 - i, "ticket_id": 40 + i % 7,
            "ticket_title": "La impresora del segundo piso no imprime en color desde ayer" if i % 2 else "Sin internet",
            "action": accion, "field": campo, "old_value": antes, "new_value": despues,
            "author": autor["nombre"] if persona != "todas" else PERSONAS[i % 3]["nombre"],
            "author_id": autor["user_id"] if persona != "todas" else PERSONAS[i % 3]["user_id"],
            "created_at": (AHORA - timedelta(hours=i * 3)).isoformat().replace("+00:00", "Z"),
        })
    return filas


def _total(persona):
    if persona in ("todas", None):
        return sum(p["cambios"] for p in PERSONAS)
    return next((p["cambios"] for p in PERSONAS if p["clave"] == persona), 0)


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


def abrir(navegador, base, ancho, tema="claro", hash_="", alto=900):
    ctx = navegador.new_context(viewport={"width": ancho, "height": alto})
    ctx.add_init_script(
        "localStorage.setItem('access_token', 'token-de-prueba');"
        f"localStorage.setItem('user', {json.dumps(json.dumps(USUARIO))});"
        + ("localStorage.setItem('tema', 'oscuro');" if tema == "oscuro" else ""))

    def api(route):
        url = urlparse(route.request.url)
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        persona = q.get("persona", "todas")
        if url.path.endswith("/api/auth/me"):
            cuerpo = USUARIO
        elif url.path.endswith("/api/history/resumen"):
            total = _total(persona)
            cuerpo = {"periodo": q.get("periodo", "7"), "desde": "2026-11-07T06:00:00Z",
                      "total": _total("todas"), "personas": PERSONAS,
                      "cajas": {"cambios": total, "tickets": min(total, 7), "comentarios": total // 5,
                                "cambios_estado": total // 5}}
        elif url.path.endswith("/api/history"):
            desde = int(q.get("offset", 0))
            limite = int(q.get("limit", 50))
            cuerpo = _cambios(persona, _total(persona))[desde:desde + limite]
        else:
            cuerpo = []
        route.fulfill(status=200, content_type="application/json", body=json.dumps(cuerpo))

    ctx.route("**/api/**", api)
    pg = ctx.new_page()
    pg.errores = []
    pg.on("pageerror", lambda e: pg.errores.append(str(e)))
    pg.on("console", lambda m: pg.errores.append(m.text) if m.type == "error" else None)
    pg.goto(f"{base}/historial.html{hash_}", wait_until="networkidle")
    pg.wait_for_selector(".hist-linea")
    carpeta = os.environ.get("CAPTURAS")
    if carpeta:
        pg.screenshot(path=f"{carpeta}/historial-{ancho}-{tema}.png", full_page=True)
    return ctx, pg


@pytest.mark.parametrize("ancho", [1366, 1920])
@pytest.mark.parametrize("tema", ["claro", "oscuro"])
def test_dos_tarjetas_como_departamentos(navegador, base, ancho, tema):
    ctx, pg = abrir(navegador, base, ancho, tema)
    try:
        m = pg.evaluate("""(() => {
            const r = (s) => document.querySelector(s).getBoundingClientRect();
            const col = r('.deptos-columna'), det = r('#hist-detalle');
            const filas = [...document.querySelectorAll('.hist-persona')].map(b => {
                const f = b.getBoundingClientRect(), a = b.querySelector('.hist-avatar').getBoundingClientRect(),
                      n = b.querySelector('.depto-boton-nombre').getBoundingClientRect(),
                      c = b.querySelector('.depto-boton-abiertos').getBoundingClientRect(),
                      p = b.querySelector('.depto-pastilla').getBoundingClientRect();
                return { alto: f.height, top: f.top, bottom: f.bottom, avatar: [a.left, a.right, a.width, a.height],
                         nombre: [n.left, n.right, n.bottom], cambios: [c.left, c.top], pastilla: p.left,
                         texto: b.querySelector('.depto-boton-nombre').textContent,
                         sub: b.querySelector('.depto-boton-abiertos').textContent };
            });
            return { col: [col.top, col.bottom], det: [det.top, det.bottom], filas, alto: window.innerHeight,
                     radio: getComputedStyle(document.querySelector('.deptos-columna')).borderRadius,
                     pagina: document.documentElement.scrollWidth, ventana: window.innerWidth };
        })()""")
        assert m["col"] == pytest.approx(m["det"], abs=0.5), "la lista al mismo alto que el detalle"
        assert m["col"][1] >= m["alto"] - 34 or m["det"][1] > m["alto"], "llega hasta abajo"
        assert m["radio"] == "10px"
        filas = m["filas"]
        assert [f["texto"] for f in filas] == ["Todas las personas", "Daniel Alejandro Sáenz Maroto",
                                               "Ana Admin", "Sofía Solicitante", "Sistema"]
        assert filas[1]["sub"] == "60 cambios" and filas[4]["sub"] == "1 cambio"
        for f in filas:
            assert round(f["alto"]) == 64, f
            assert f["avatar"][1] < f["nombre"][0], "el círculo a la izquierda del nombre"
            assert f["avatar"][2] == f["avatar"][3], "círculo"
            assert f["nombre"][2] <= f["cambios"][1] + 0.5, "«N cambios» debajo del nombre"
            assert f["pastilla"] > f["nombre"][1], "la pastilla a la derecha"
        assert m["pagina"] <= m["ventana"]
        elegido = pg.evaluate("""(() => { const b = document.querySelector('.hist-persona.elegido');
            return [b.textContent.startsWith('Todas'), getComputedStyle(b).borderLeftWidth,
                    getComputedStyle(b).borderLeftColor !== 'rgba(0, 0, 0, 0)']; })()""")
        assert elegido == [True, "3px", True], "marcada igual que en Departamentos"
        assert pg.text_content("#hist-nombre") == "Todas las personas"
        cajas = pg.eval_on_selector_all(".hist-cajas .depto-caja-etiqueta", "e => e.map(x => x.textContent)")
        assert cajas == ["Cambios", "Tickets tocados", "Comentarios", "Cambios de estado"]
        dia = pg.eval_on_selector(".hist-dia-titulo", "t => [t.textContent, getComputedStyle(t).textTransform]")
        assert dia[0].startswith("Hoy · ") and dia[1] == "uppercase"
        linea = pg.evaluate("""(() => { const l = document.querySelector('.hist-linea');
            const r = (s) => l.querySelector(s).getBoundingClientRect();
            return { una: new Set(['.hist-hora', '.hist-autor', '.hist-ticket', '.hist-frase'].map(s => Math.round(r(s).top + r(s).height / 2))).size,
                     orden: ['.hist-hora', '.hist-autor', '.hist-ticket', '.hist-frase'].map(s => r(s).left),
                     iniciales: l.querySelector('.hist-autor').dataset.iniciales }; })()""")
        assert linea["una"] <= 2, "una línea por cambio"
        assert linea["orden"] == sorted(linea["orden"]), "hora, quién, ticket y qué hizo"
        assert linea["iniciales"]
        assert len(pg.query_selector_all(".hist-linea")) == 50
        assert pg.is_visible("#hist-ver-mas")
        assert pg.errores == []
    finally:
        ctx.close()


def test_elegir_persona_ver_mas_y_recargar(navegador, base):
    ctx, pg = abrir(navegador, base, 1366)
    try:
        pg.click(".hist-persona:has-text('Daniel')")
        pg.wait_for_function("document.getElementById('hist-nombre').textContent.startsWith('Daniel')")
        pg.wait_for_function("location.hash === '#persona=12&periodo=7'")
        assert pg.text_content("#hist-rol") == "Técnico · Redes e Infraestructura"
        assert pg.text_content("#hist-total") == "60 cambios en el período"
        assert pg.query_selector(".hist-linea.con-autor") is None, "sin el nombre en cada línea"
        pg.click("#hist-ver-mas")
        pg.wait_for_function("document.querySelectorAll('.hist-linea').length === 60")
        assert not pg.is_visible("#hist-ver-mas")
        dias = pg.eval_on_selector_all(".hist-dia-titulo", "t => t.map(x => x.textContent)")
        assert len(dias) == len(set(dias)), "cada día una sola vez, también después de «Ver más»"

        pg.select_option("#hist-periodo", "30")
        pg.wait_for_function("location.hash === '#persona=12&periodo=30'")
        pg.reload(wait_until="networkidle")
        pg.wait_for_selector(".hist-linea")
        assert pg.text_content("#hist-nombre").startswith("Daniel")
        assert pg.eval_on_selector("#hist-periodo", "s => s.value") == "30"
        assert pg.get_attribute(".hist-persona.elegido", "aria-selected") == "true"

        with pg.expect_request(lambda r: "buscar=impresora" in r.url):
            pg.fill("#hist-buscar", "impresora")
        assert pg.errores == []
    finally:
        ctx.close()


def test_con_teclado(navegador, base):
    ctx, pg = abrir(navegador, base, 1366)
    try:
        pg.focus(".hist-persona.elegido")
        pg.keyboard.press("ArrowDown")
        pg.wait_for_function("document.getElementById('hist-nombre').textContent.startsWith('Daniel')")
        assert pg.evaluate("document.activeElement.id") == "tab-persona-12"
        pg.keyboard.press("End")
        pg.wait_for_function("document.getElementById('hist-nombre').textContent === 'Sistema'")
        assert pg.evaluate("document.activeElement.id") == "tab-persona-sistema"
        pg.keyboard.press("Tab")
        assert pg.evaluate("document.activeElement.id") == "hist-detalle", "del tab al panel"
        assert pg.errores == []
    finally:
        ctx.close()


@pytest.mark.parametrize("tema", ["claro", "oscuro"])
def test_celular_lista_arriba_detalle_debajo_sin_scroll_de_costado(navegador, base, tema):
    ctx, pg = abrir(navegador, base, 375, tema, hash_="#persona=todas&periodo=7")
    try:
        m = pg.evaluate("""(() => { const l = document.getElementById('hist-lista').getBoundingClientRect(),
                d = document.getElementById('hist-detalle').getBoundingClientRect(),
                lista = document.getElementById('hist-lista');
            return { ori: lista.getAttribute('aria-orientation'), listaBottom: l.bottom, detTop: d.top,
                     pagina: document.documentElement.scrollWidth, ventana: window.innerWidth,
                     anchos: [...document.querySelectorAll('.hist-linea')].every(x => x.getBoundingClientRect().right <= d.right + 0.5) }; })()""")
        assert m["ori"] == "horizontal"
        assert m["detTop"] >= m["listaBottom"], "el detalle debajo de la lista"
        assert m["pagina"] <= m["ventana"], "sin scroll de costado"
        assert m["anchos"], "las líneas dentro de la tarjeta"
        assert pg.errores == []
    finally:
        ctx.close()
