"""El frontend se sirve con «Cache-Control: no-cache»: el navegador guarda la
copia pero la revalida siempre (ETag → 304), así no usa un .js viejo con el
HTML nuevo (pasó con ayuda.js: los botones de «Temas» no hacían nada)."""

import pytest


@pytest.mark.parametrize("ruta", ["/ayuda.html", "/js/ayuda.js", "/js/ayuda.js?v=20261110-pestanas",
                                  "/css/estilos.css", "/js/auth.js", "/"])
def test_frontend_se_revalida_siempre(client, ruta):
    resp = client.get(ruta)
    assert resp.status_code == 200, ruta
    assert resp.headers["cache-control"] == "no-cache", ruta
    assert resp.headers.get("etag"), ruta


def test_sin_cambios_responde_304_y_tambien_no_cache(client):
    primera = client.get("/js/ayuda.js")
    otra = client.get("/js/ayuda.js", headers={"If-None-Match": primera.headers["etag"]})
    assert otra.status_code == 304
    assert otra.headers["cache-control"] == "no-cache"


def test_la_api_no_cambia(client):
    assert "no-cache" not in client.get("/health").headers.get("cache-control", "")
