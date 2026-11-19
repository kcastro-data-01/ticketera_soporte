"""El frontend: la app React en la raíz (fallback de SPA), la página
silenciosa de MSAL y las 301 desde las direcciones viejas (index.html,
detalle.html?id=N, /react/…). Con un build falso en una carpeta temporal,
así no hace falta compilar React para correr las pruebas."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.frontend_react import CACHE_ASSETS, montar_react, ruta_nueva

INDEX = "<!DOCTYPE html><html><body><div id=raiz></div></body></html>"
SILENCIOSA = "<!DOCTYPE html><html><body></body></html>"


def build_falso(carpeta):
    (carpeta / "assets").mkdir(parents=True)
    (carpeta / "msal").mkdir()
    (carpeta / "index.html").write_text(INDEX)
    (carpeta / "assets" / "index-abc123.js").write_text("console.log(1)")
    (carpeta / "tema.js").write_text("// tema")
    (carpeta / "robots.txt").write_text("User-agent: *\nDisallow: /\n")
    (carpeta / "msal" / "silencioso.html").write_text(SILENCIOSA)
    return carpeta


@pytest.fixture
def cliente(tmp_path):
    app = FastAPI()

    @app.get("/api/ping")
    def ping():
        return {"ok": True}

    @app.get("/health")
    def salud():
        return {"status": "ok"}

    assert montar_react(app, build_falso(tmp_path / "dist")) is True
    return TestClient(app)


@pytest.mark.parametrize("ruta", ["/", "/login", "/tickets/5", "/crear", "/metricas", "/departamentos", "/historial",
                                  "/usuarios", "/cuenta", "/ayuda", "/sin-permiso", "/cualquier/cosa?x=1"])
def test_las_rutas_de_la_app_devuelven_index_y_se_revalidan(cliente, ruta):
    resp = cliente.get(ruta)
    assert resp.status_code == 200, ruta
    assert resp.text == INDEX
    assert resp.headers["cache-control"] == "no-cache"
    assert resp.headers.get("etag")


def test_assets_con_hash_se_guardan_y_los_que_faltan_dan_404(cliente):
    resp = cliente.get("/assets/index-abc123.js")
    assert resp.status_code == 200
    assert resp.headers["cache-control"] == CACHE_ASSETS
    assert cliente.get("/assets/no-existe.js").status_code == 404
    tema = cliente.get("/tema.js")
    assert tema.headers["cache-control"] == "no-cache"
    otra = cliente.get("/tema.js", headers={"If-None-Match": tema.headers["etag"]})
    assert otra.status_code == 304


def test_la_api_no_cae_en_la_app(cliente):
    assert cliente.get("/api/ping").json() == {"ok": True}
    assert cliente.get("/health").json() == {"status": "ok"}
    for ruta in ("/api/no-existe", "/api", "/healthz"):
        resp = cliente.get(ruta)
        assert resp.status_code == 404, ruta
        assert resp.text != INDEX


def test_metodo_no_permitido_sigue_siendo_405(cliente):
    assert cliente.post("/api/ping").status_code == 405
    assert cliente.delete("/").status_code == 405
    assert cliente.post("/tickets/5").status_code == 405


def test_pagina_silenciosa_sin_html(cliente):
    resp = cliente.get("/msal/silencioso")
    assert resp.status_code == 200
    assert resp.text == SILENCIOSA
    assert resp.headers["content-type"].startswith("text/html")
    vieja = cliente.get("/msal/silencioso.html", follow_redirects=False)
    assert (vieja.status_code, vieja.headers["location"]) == (301, "/msal/silencioso")


@pytest.mark.parametrize("vieja, nueva", [
    ("/index.html", "/"),
    ("/index.html?estado=Nuevo&area=2", "/?estado=Nuevo&area=2"),
    ("/detalle.html?id=12", "/tickets/12"),
    ("/detalle.html?id=12&pestana=ia", "/tickets/12?pestana=ia"),
    ("/detalle.html?id=abc", "/"),
    ("/detalle.html", "/"),
    ("/crear.html", "/crear"),
    ("/login.html", "/login"),
    ("/login.html?volver=%2Ftickets%2F5", "/login?volver=%2Ftickets%2F5"),
    ("/metricas.html", "/metricas"),
    ("/departamentos.html", "/departamentos"),
    ("/historial.html", "/historial"),
    ("/usuarios.html", "/usuarios"),
    ("/cuenta.html", "/cuenta"),
    ("/ayuda.html", "/ayuda"),
    ("/sin-permiso.html", "/sin-permiso"),
    ("/404.html", "/"),
    ("/react", "/"),
    ("/react/", "/"),
    ("/react/tickets/7?pestana=ia", "/tickets/7?pestana=ia"),
    ("/react/ayuda", "/ayuda"),
    ("/react/login?volver=%2Fcrear", "/login?volver=%2Fcrear"),
])
def test_direcciones_viejas_redirigen_con_301(cliente, vieja, nueva):
    resp = cliente.get(vieja, follow_redirects=False)
    assert resp.status_code == 301, vieja
    assert resp.headers["location"] == nueva
    assert cliente.head(vieja, follow_redirects=False).status_code == 301


def test_siguiendo_la_redireccion_se_llega_a_la_app(cliente):
    resp = cliente.get("/detalle.html?id=3")
    assert resp.status_code == 200 and resp.text == INDEX
    assert [r.status_code for r in resp.history] == [301]


def test_sin_build_igual_redirige_y_no_hay_app(tmp_path):
    app = FastAPI()
    assert montar_react(app, tmp_path / "no-existe") is False
    cliente = TestClient(app)
    assert cliente.get("/detalle.html?id=1", follow_redirects=False).headers["location"] == "/tickets/1"
    assert cliente.get("/tickets/1").status_code == 404


@pytest.mark.parametrize("vieja, consulta, nueva", [
    ("/detalle.html", "id=12", "/tickets/12"),
    ("/detalle.html", "id=0", "/"),
    ("/detalle.html", "id=12&pestana=ia", "/tickets/12?pestana=ia"),
    ("/index.html", "", "/"),
    ("/index.html", "estado=Nuevo&area=2", "/?estado=Nuevo&area=2"),
    ("/react/historial", "", "/historial"),
    ("/js/app.js", "", None),
    ("/tickets/5", "", None),
])
def test_ruta_nueva(vieja, consulta, nueva):
    assert ruta_nueva(vieja, consulta) == nueva
