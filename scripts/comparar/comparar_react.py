"""Compara la pantalla de Tickets actual (/index.html) con la de React
(/react/) en Chromium headless: capturas en escritorio (1366x768) y celular
(390x844), claro y oscuro, con la misma API simulada; mide las cajas de los
elementos de la estructura y cuenta los píxeles distintos.

Correr con: scripts/comparar_react.sh   (deja las capturas en
scripts/comparar/capturas/, que no se sube a Git)

El chat del asistente (#chat-asistente) todavía no está en React (próxima
etapa): se oculta en la página actual para comparar el resto.
"""

import base64
import functools
import http.server
import json
import sys
import threading
import time
from pathlib import Path

from PIL import Image, ImageChops
from playwright.sync_api import sync_playwright

RAIZ = Path(__file__).resolve().parents[2]
SALIDA = Path(__file__).resolve().parent / "capturas"
VISTAS = {"escritorio": {"width": 1366, "height": 768}, "celular": {"width": 390, "height": 844}}
TEMAS = ["claro", "oscuro"]
ROLES = sys.argv[1:] or ["Administrador"]

USUARIOS = {
    "Administrador": {"id": 1, "name": "Ana Admin", "email": "ana@data.cr", "role": "Administrador", "is_active": True},
    "Técnico": {"id": 2, "name": "Tomás Técnico", "email": "tomas@data.cr", "role": "Técnico", "is_active": True},
    "Solicitante": {"id": 3, "name": "Sara Solicitante", "email": "sara@data.cr", "role": "Solicitante", "is_active": True},
}
TICKETS = [
    {"id": 101 + i, "title": t, "description": "x", "category": c, "priority": p, "state": e,
     "assigned_to_id": a, "created_by_id": 3, "created_at": f"2026-11-{10 + i:02d}T15:30:00Z"}
    for i, (t, c, p, e, a) in enumerate([
        ("Impresora del piso 2 sin tóner", "Hardware", "Alta", "Nuevo", None),
        ("No conecta la VPN desde casa", "Red", "Crítica", "En proceso", 2),
        ("Restablecer clave del correo", "Accesos", "Media", "Resuelto", 1),
        ("Instalar Office en portátil nueva", "Software", "Baja", "Cerrado", 2),
        ("Pantalla parpadea en sala de juntas", "Hardware", "Media", "Nuevo", None),
    ])
]
AREAS = [{"id": 1, "name": "Soporte IT"}, {"id": 2, "name": "Redes"}, {"id": 3, "name": "Desarrollo"}, {"id": 4, "name": "Infraestructura"}]
SELECTORES = ["body", ".barra-lateral", ".marca", ".boton-plegar", ".menu", ".menu-usuario", ".app-principal",
              ".cabecera", ".cabecera h1", ".listado-controles", ".cabecera-acciones", ".boton-tema",
              ".contenido", "#form-filtros", "#total-tickets", "#tabla-tickets", "table.listado thead",
              "#lista-tickets tr", ".pie"]


def token(rol):
    b64 = lambda o: base64.urlsafe_b64encode(json.dumps(o).encode()).decode().rstrip("=")
    ahora = int(time.time())
    datos = {"sub": "1", "role": rol, "iat": ahora, "exp": ahora + 3600, "ini": ahora, "max": ahora + 36000}
    return f"{b64({'alg': 'HS256'})}.{b64(datos)}.firma"


class Servidor(http.server.SimpleHTTPRequestHandler):
    """frontend/ en «/» y frontend-react/dist en «/react/» con index.html
    para cualquier ruta (como backend/frontend_react.py)."""

    def log_message(self, *args):
        pass

    def translate_path(self, path):
        ruta = path.split("?")[0]
        if ruta == "/react" or ruta.startswith("/react/"):
            dist = RAIZ / "frontend-react" / "dist"
            archivo = dist / ruta[len("/react/"):]
            return str(archivo if archivo.is_file() else dist / "index.html")
        return str(RAIZ / "frontend" / ruta.lstrip("/"))


def api(route, rol):
    url = route.request.url
    ruta = url.split("://", 1)[1].split("/", 1)[1]
    ruta = "/" + ruta
    json_ = lambda cuerpo, **h: route.fulfill(status=200, content_type="application/json", body=json.dumps(cuerpo), headers=h)
    if ruta.startswith("/api/tickets/summary"):
        return json_({"mios_abiertos": 2})
    if ruta.startswith("/api/tickets?state=Nuevo"):
        return json_([t for t in TICKETS if t["state"] == "Nuevo"])
    if ruta.startswith("/api/tickets"):
        return json_(TICKETS, **{"X-Total-Count": str(len(TICKETS))})
    if ruta.startswith("/api/users"):
        return json_(list(USUARIOS.values()))
    if ruta.startswith("/api/areas"):
        return json_(AREAS)
    if ruta.startswith("/api/auth/me"):
        return json_(USUARIOS[rol])
    return json_({})


def cajas(pagina):
    return pagina.evaluate("""(sels) => Object.fromEntries(sels.map((s) => {
        const el = document.querySelector(s);
        if (!el) return [s, null];
        const r = el.getBoundingClientRect();
        return [s, [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)]];
    }))""", SELECTORES)


def capturar(navegador, puerto, rol, vista, tema, cual):
    contexto = navegador.new_context(viewport=VISTAS[vista], device_scale_factor=1, locale="es-CR",
                                     timezone_id="America/Costa_Rica")
    contexto.add_init_script(f"""
        localStorage.setItem("access_token", {json.dumps(token(rol))});
        localStorage.setItem("user", {json.dumps(json.dumps(USUARIOS[rol]))});
        localStorage.setItem("sesion_actividad", String(Date.now()));
        {'localStorage.setItem("tema", "oscuro");' if tema == "oscuro" else 'localStorage.removeItem("tema");'}
        ["vista_listado", "densidad_listado", "orden_listado", "menu_plegado"].forEach((k) => localStorage.removeItem(k));
    """)
    pagina = contexto.new_page()
    pagina.route("**/api/**", lambda route: api(route, rol))
    pagina.route("https://fonts.googleapis.com/**", lambda route: route.abort())
    pagina.route("https://fonts.gstatic.com/**", lambda route: route.abort())
    pagina.route("https://cdn.jsdelivr.net/**", lambda route: route.abort())
    url = f"http://127.0.0.1:{puerto}" + ("/index.html" if cual == "actual" else "/react/")
    pagina.goto(url)
    pagina.wait_for_selector("#lista-tickets tr:not(.fila-esqueleto)")
    pagina.wait_for_timeout(400)
    pagina.add_style_tag(content="#chat-asistente{display:none!important} *{transition:none!important;animation:none!important;caret-color:transparent!important}")
    pagina.wait_for_timeout(200)
    archivo = SALIDA / f"{rol}-{vista}-{tema}-{cual}.png"
    pagina.screenshot(path=str(archivo), full_page=True)
    medidas = cajas(pagina)
    contexto.close()
    return archivo, medidas


def diferencia(a, b):
    ia, ib = Image.open(a).convert("RGB"), Image.open(b).convert("RGB")
    if ia.size != ib.size:
        return None, ia.size, ib.size
    caja = ImageChops.difference(ia, ib).getbbox()
    if not caja:
        return 0, ia.size, ib.size
    distintos = sum(1 for p in ImageChops.difference(ia, ib).convert("L").getdata() if p > 16)
    return distintos, ia.size, ib.size


def main():
    SALIDA.mkdir(exist_ok=True)
    servidor = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Servidor)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    puerto = servidor.server_address[1]
    todo_igual = True
    with sync_playwright() as p:
        navegador = p.chromium.launch()
        for rol in ROLES:
            for vista in VISTAS:
                for tema in TEMAS:
                    a, ma = capturar(navegador, puerto, rol, vista, tema, "actual")
                    b, mb = capturar(navegador, puerto, rol, vista, tema, "react")
                    distintos, ta, tb = diferencia(a, b)
                    cajas_distintas = {s: (ma[s], mb[s]) for s in SELECTORES if ma[s] != mb[s]}
                    igual = distintos == 0 and not cajas_distintas
                    todo_igual &= igual
                    estado = "IGUAL" if igual else "DISTINTO"
                    print(f"{estado:8} {rol} {vista} {tema}: tamaño {ta} / {tb}, píxeles distintos {distintos}")
                    for s, (x, y) in cajas_distintas.items():
                        print(f"           {s}: actual {x}  react {y}")
        navegador.close()
    servidor.shutdown()
    sys.exit(0 if todo_igual else 1)


if __name__ == "__main__":
    main()
