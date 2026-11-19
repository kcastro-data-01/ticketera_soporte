"""La app React bajo /react/: archivos del build, index.html para cualquier
ruta de React (fallback de SPA) y el frontend actual sin cambios."""

import pytest
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient

from backend.frontend_react import CACHE_ASSETS, montar_react, ruta_nueva

INDEX = "<!DOCTYPE html><html><body><div id=raiz></div></body></html>"


@pytest.fixture
def cliente(tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(INDEX)
    (dist / "assets" / "index-abc123.js").write_text("console.log(1)")
    (dist / "tema.js").write_text("// tema")
    viejo = tmp_path / "frontend"
    viejo.mkdir()
    (viejo / "index.html").write_text("viejo")
    (viejo / "404.html").write_text("no existe")

    app = FastAPI()

    @app.get("/api/ping")
    def ping():
        return {"ok": True}

    assert montar_react(app, dist) is True
    app.mount("/", StaticFiles(directory=str(viejo), html=True), name="frontend")
    return TestClient(app)


@pytest.mark.parametrize("ruta", ["/react/", "/react/login", "/react/tickets/5", "/react/crear",
                                  "/react/sin-permiso", "/react/cualquier/cosa?x=1"])
def test_rutas_de_react_devuelven_index(cliente, ruta):
    resp = cliente.get(ruta)
    assert resp.status_code == 200, ruta
    assert resp.text == INDEX
    assert resp.headers["cache-control"] == "no-cache"


def test_sin_barra_redirige(cliente):
    resp = cliente.get("/react", follow_redirects=False)
    assert resp.status_code == 307
    assert resp.headers["location"] == "/react/"


def test_assets_con_hash_se_guardan_y_los_que_faltan_dan_404(cliente):
    resp = cliente.get("/react/assets/index-abc123.js")
    assert resp.status_code == 200
    assert resp.headers["cache-control"] == CACHE_ASSETS
    assert cliente.get("/react/assets/no-existe.js").status_code == 404
    assert cliente.get("/react/tema.js").headers["cache-control"] == "no-cache"


def test_api_y_frontend_actual_sin_cambios(cliente):
    assert cliente.get("/api/ping").json() == {"ok": True}
    assert cliente.get("/index.html").text == "viejo"
    assert cliente.get("/reactor.html").status_code == 404


def test_sin_build_no_se_monta(tmp_path):
    app = FastAPI()
    assert montar_react(app, tmp_path / "no-existe") is False
    assert not [r for r in app.routes if getattr(r, "path", "") == "/react"]


@pytest.mark.parametrize("vieja, consulta, nueva", [
    ("/detalle.html", "id=12", "/tickets/12"),
    ("/detalle.html", "id=x", "/"),
    ("/index.html", "", "/"),
    ("/index.html", "estado=Nuevo&area=2", "/?estado=Nuevo&area=2"),
    ("/login.html", "volver=detalle.html%3Fid%3D5", "/login?volver=detalle.html%3Fid%3D5"),
    ("/metricas.html", "", "/metricas"),
    ("/js/app.js", "", None),
])
def test_ruta_nueva_para_la_etapa_final(vieja, consulta, nueva):
    assert ruta_nueva(vieja, consulta) == nueva
