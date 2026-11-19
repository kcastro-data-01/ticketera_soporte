"""Compara las pantallas actuales con las de React en Chromium headless:
Tickets (/index.html ↔ /react/), Detalle (/detalle.html?id=N ↔
/react/tickets/N, también con ?pestana=ia y un ticket Cerrado) y Nuevo
ticket (/crear.html ↔ /react/crear). Capturas en escritorio (1366x768) y
celular (390x844), claro y oscuro, con la misma API simulada; mide las cajas
de los elementos de la estructura y cuenta los píxeles distintos.

Correr con: scripts/comparar_react.sh [roles…] [--paginas tickets,detalle,…]
(deja las capturas en scripts/comparar/capturas/, que no se sube a Git)

El chat del asistente (#chat-asistente) todavía no está en React (próxima
etapa): se oculta en la página actual para comparar el resto.
"""

import base64
import http.server
import json
import re
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
ARGUMENTOS = sys.argv[1:]
PEDIDAS = None
if "--paginas" in ARGUMENTOS:
    i = ARGUMENTOS.index("--paginas")
    PEDIDAS = ARGUMENTOS[i + 1].split(",")
    ARGUMENTOS = ARGUMENTOS[:i] + ARGUMENTOS[i + 2:]
ROLES = ARGUMENTOS or ["Administrador"]

LISTO_DETALLE = """() => {
  const t = document.querySelector('#ver-title');
  const c = document.querySelector('#lista-comentarios:not([hidden]) .comentario');
  const a = document.querySelector('#adj-lista:not([hidden]) .adjunto');
  const imgs = [...document.querySelectorAll('img.adjunto-miniatura')];
  return t && t.textContent !== '—' && c && a && imgs.every((i) => i.src && i.complete);
}"""
PAGINAS = {
    "tickets": ("/index.html", "/react/", "() => document.querySelector('#lista-tickets tr:not(.fila-esqueleto)')"),
    "detalle": ("/detalle.html?id=101", "/react/tickets/101", LISTO_DETALLE),
    "detalle-ia": ("/detalle.html?id=101&pestana=ia", "/react/tickets/101?pestana=ia", LISTO_DETALLE),
    "detalle-cerrado": ("/detalle.html?id=104", "/react/tickets/104", LISTO_DETALLE),
    "crear": ("/crear.html", "/react/crear", "() => document.querySelector('#area option[value=\"2\"]')"),
}


USUARIOS = {
    "Administrador": {"id": 1, "name": "Ana Admin", "email": "ana@data.cr", "role": "Administrador", "is_active": True, "area_name": "Soporte IT"},
    "Técnico": {"id": 2, "name": "Tomás Técnico", "email": "tomas@data.cr", "role": "Técnico", "is_active": True, "area_name": "Redes"},
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
for t in TICKETS:
    t.update({"updated_at": t["created_at"].replace("T15", "T18"), "area_id": 2, "area_name": "Redes"})
TICKETS[0]["description"] = ("Desde esta mañana la impresora HP del segundo piso muestra «tóner bajo» y no imprime.\n"
                             "Ya probé apagarla y encenderla. <b>no es html</b>")
COMENTARIOS = [
    {"id": 1, "author": "Sara Solicitante", "author_id": 3, "author_es_it": False, "origen": "app",
     "content": "¿Alguien puede revisarla hoy? Tenemos que imprimir contratos.", "created_at": "2026-11-10T15:40:00Z"},
    {"id": 2, "author": "Sara Solicitante", "author_id": 3, "author_es_it": False, "origen": "correo",
     "content": "Adjunto la foto del mensaje.", "created_at": "2026-11-10T15:44:00Z"},
    {"id": 3, "author": "Tomás Técnico", "author_id": 2, "author_es_it": True, "origen": "estado", "estado_nuevo": "En proceso",
     "content": "voy en camino", "created_at": "2026-11-10T16:10:00Z"},
    {"id": 4, "author": "Tomás Técnico", "author_id": 2, "author_es_it": True, "origen": "app",
     "content": "Cambié el cartucho; quedó imprimiendo.", "created_at": "2026-11-10T16:30:00Z"},
]
def _png(lado=64):
    """Una imagen PNG válida (degradado azul) para las miniaturas."""
    import struct
    import zlib
    filas = b"".join(b"\x00" + bytes(c for x in range(lado) for c in (40 + x * 2, 90 + y, 200)) for y in range(lado))
    trozo = lambda tipo, datos: struct.pack(">I", len(datos)) + tipo + datos + struct.pack(">I", zlib.crc32(tipo + datos))
    return (b"\x89PNG\r\n\x1a\n" + trozo(b"IHDR", struct.pack(">IIBBBBB", lado, lado, 8, 2, 0, 0, 0))
            + trozo(b"IDAT", zlib.compress(filas)) + trozo(b"IEND", b""))


PNG = _png()


def adjuntos(ticket_id, rol):
    cerrado = next(t for t in TICKETS if t["id"] == ticket_id)["state"] == "Cerrado"
    lista = [
        {"id": 7, "ticket_id": ticket_id, "nombre": "mensaje-impresora.png", "tamano": 183_500, "subido_por": "Sara Solicitante",
         "creado": "2026-11-10T15:44:00Z", "es_imagen": True, "por_correo": True, "puede_eliminar": rol == "Administrador" and not cerrado},
        {"id": 8, "ticket_id": ticket_id, "nombre": "factura-toner.pdf", "tamano": 912, "subido_por": "Tomás Técnico",
         "creado": "2026-11-10T16:31:00Z", "es_imagen": False, "por_correo": False, "puede_eliminar": rol != "Solicitante" and not cerrado},
    ]
    return {"adjuntos": lista, "puede_subir": not cerrado, "cerrado": cerrado, "max_archivos": 10, "max_bytes": 4194304}


EXPLICACION = {
    "explicacion": {
        "explicacion": "La impresora no imprime porque el tóner llegó al mínimo.",
        "certeza": "alta",
        "posibles_causas": ["Cartucho de tóner agotado", "Sensor de tóner sucio"],
        "que_revisar_primero": ["Cambiar el cartucho", "Limpiar el sensor"],
        "categoria_sugerida": {"valor": "Hardware", "razon": "es un equipo físico"},
        "prioridad_sugerida": {"valor": "Media", "razon": ""},
    },
    "vigente": False, "claridad": "clara", "motivo_claridad": "La descripción dice qué pasa y desde cuándo.",
    "modelo": "qwen3:0.6b", "generada_en": "2026-11-10T17:00:00Z", "ia_disponible": True,
}

AREAS = [{"id": 1, "name": "Soporte IT"}, {"id": 2, "name": "Redes"}, {"id": 3, "name": "Desarrollo"}, {"id": 4, "name": "Infraestructura"}]
SELECTORES = ["body", ".barra-lateral", ".marca", ".boton-plegar", ".menu", ".menu-usuario", ".app-principal",
              ".cabecera", ".cabecera h1", ".listado-controles", ".cabecera-acciones", ".boton-tema",
              ".contenido", "#form-filtros", "#total-tickets", "#tabla-tickets", "table.listado thead",
              "#lista-tickets tr", ".pie", ".migas", ".acciones-principales", "#panel-ticket", "#pasos-estado",
              "#seccion-adjuntos", "#adj-lista", "#pestanas-detalle", "#lista-comentarios", "#form-comentario",
              ".detalle-lateral", "#panel-datos", "#seccion-asignacion", "#seccion-area", "#seccion-ia", "#ia-panel",
              "#form-crear", ".crear-lateral", ".opciones-prioridad", ".acciones-crear"]


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
    ruta = "/" + url.split("://", 1)[1].split("/", 1)[1]
    json_ = lambda cuerpo, **h: route.fulfill(status=200, content_type="application/json", body=json.dumps(cuerpo), headers=h)
    m = re.match(r"^/api/tickets/(\d+)(/[a-z]+)?(/\d+/archivo)?", ruta)
    if m and not ruta.startswith("/api/tickets/summary"):
        tid, sub, archivo = int(m.group(1)), m.group(2), m.group(3)
        if sub == "/comments":
            return json_(COMENTARIOS)
        if sub == "/adjuntos" and archivo:
            return route.fulfill(status=200, content_type="image/png", body=PNG)
        if sub == "/adjuntos":
            return json_(adjuntos(tid, rol))
        if sub == "/explicacion":
            return json_(EXPLICACION)
        if sub == "/history":
            return json_([])
        return json_(next(t for t in TICKETS if t["id"] == tid))
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


def capturar(navegador, puerto, rol, vista, tema, cual, pagina_nombre):
    contexto = navegador.new_context(viewport=VISTAS[vista], device_scale_factor=1, locale="es-CR",
                                     timezone_id="America/Costa_Rica")
    contexto.add_init_script(f"""
        localStorage.setItem("access_token", {json.dumps(token(rol))});
        localStorage.setItem("user", {json.dumps(json.dumps(USUARIOS[rol]))});
        localStorage.setItem("sesion_actividad", String(Date.now()));
        {'localStorage.setItem("tema", "oscuro");' if tema == "oscuro" else 'localStorage.removeItem("tema");'}
        ["vista_listado", "densidad_listado", "orden_listado", "menu_plegado", "detalle_pestana"].forEach((k) => localStorage.removeItem(k));
    """)
    pagina = contexto.new_page()
    pagina.route("**/api/**", lambda route: api(route, rol))
    pagina.route("https://fonts.googleapis.com/**", lambda route: route.abort())
    pagina.route("https://fonts.gstatic.com/**", lambda route: route.abort())
    pagina.route("https://cdn.jsdelivr.net/**", lambda route: route.abort())
    vieja, nueva, listo = PAGINAS[pagina_nombre]
    pagina.goto(f"http://127.0.0.1:{puerto}" + (vieja if cual == "actual" else nueva))
    pagina.wait_for_function(listo, timeout=15000)
    pagina.wait_for_timeout(400)
    pagina.add_style_tag(content="#chat-asistente{display:none!important} *{transition:none!important;animation:none!important;caret-color:transparent!important}")
    pagina.wait_for_timeout(200)
    archivo = SALIDA / f"{pagina_nombre}-{rol}-{vista}-{tema}-{cual}.png"
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
        for nombre in PEDIDAS or list(PAGINAS):
          for rol in ROLES:
            for vista in VISTAS:
                for tema in TEMAS:
                    a, ma = capturar(navegador, puerto, rol, vista, tema, "actual", nombre)
                    b, mb = capturar(navegador, puerto, rol, vista, tema, "react", nombre)
                    distintos, ta, tb = diferencia(a, b)
                    cajas_distintas = {s: (ma[s], mb[s]) for s in SELECTORES if ma[s] != mb[s]}
                    igual = distintos == 0 and not cajas_distintas
                    todo_igual &= igual
                    estado = "IGUAL" if igual else "DISTINTO"
                    print(f"{estado:8} {nombre} {rol} {vista} {tema}: tamaño {ta} / {tb}, píxeles distintos {distintos}")
                    for s, (x, y) in cajas_distintas.items():
                        print(f"           {s}: actual {x}  react {y}")
        navegador.close()
    servidor.shutdown()
    sys.exit(0 if todo_igual else 1)


if __name__ == "__main__":
    main()
