"""Sesión deslizante: POST /api/auth/renovar con el token vigente, el mismo
inicio de sesión y nunca más de SESION_MAXIMA_HORAS (10) desde el inicio.
El aviso por inactividad es del navegador (frontend/js/sesion.js)."""

from datetime import datetime, timedelta, timezone

import jwt
import pytest

from backend import auth
from backend.models import User
from backend.tests.test_login_microsoft import entrar, id_token, tenant_simulado  # noqa: F401


@pytest.fixture
def usuario(session):
    user = User(name="Karla Sánchez", email="ksanchez@data.cr", role="Técnico")
    session.add(user)
    session.commit()
    return user


def datos(token):
    return jwt.decode(token, auth.JWT_SECRET_KEY, algorithms=[auth.JWT_ALGORITHM])


def renovar(client, token):
    return client.post("/api/auth/renovar", headers={"Authorization": f"Bearer {token}"})


def token_con(usuario, inicio, emitido=None, dura=timedelta(hours=1)):
    """Un token como los de la app, con fechas a elección."""
    emitido = emitido or datetime.now(timezone.utc)
    maximo = inicio + timedelta(hours=auth.SESION_MAXIMA_HORAS)
    payload = {"sub": str(usuario.id), "role": usuario.role, "iat": emitido,
               "exp": min(emitido + dura, maximo), "ini": int(inicio.timestamp()),
               "max": int(maximo.timestamp())}
    return jwt.encode(payload, auth.JWT_SECRET_KEY, algorithm=auth.JWT_ALGORITHM)


def test_el_token_trae_inicio_y_maximo_de_10_horas(usuario):
    token, dura = auth.create_access_token(usuario.id, usuario.role)
    d = datos(token)
    assert d["max"] - d["ini"] == 10 * 3600
    assert abs(d["ini"] - d["iat"]) <= 1
    assert dura == auth.JWT_EXPIRATION_MINUTES * 60


def test_renovar_entrega_un_token_nuevo_con_el_mismo_inicio(client, usuario):
    inicio = datetime.now(timezone.utc) - timedelta(hours=3)
    viejo = token_con(usuario, inicio, emitido=datetime.now(timezone.utc) - timedelta(minutes=20))
    resp = renovar(client, viejo)
    assert resp.status_code == 200, resp.text
    nuevo = datos(resp.json()["access_token"])
    assert nuevo["ini"] == int(inicio.timestamp())
    assert nuevo["exp"] > datos(viejo)["exp"], "se alarga"
    assert resp.json()["expires_in"] > 50 * 60
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {resp.json()['access_token']}"})
    assert me.json()["email"] == "ksanchez@data.cr"


def test_cerca_del_maximo_la_renovacion_no_pasa_de_10_horas(client, usuario):
    inicio = datetime.now(timezone.utc) - timedelta(hours=9, minutes=45)
    resp = renovar(client, token_con(usuario, inicio))
    assert resp.status_code == 200
    nuevo = datos(resp.json()["access_token"])
    assert nuevo["exp"] <= int((inicio + timedelta(hours=10)).timestamp())
    assert resp.json()["expires_in"] <= 15 * 60 + 1


def test_pasadas_10_horas_no_se_renueva(client, usuario):
    inicio = datetime.now(timezone.utc) - timedelta(hours=10, seconds=1)
    # Aunque alguien fabricara un exp más largo con la clave, el max manda.
    token = token_con(usuario, inicio, dura=timedelta(hours=12))
    payload = jwt.decode(token, auth.JWT_SECRET_KEY, algorithms=[auth.JWT_ALGORITHM],
                         options={"verify_exp": False}) | {"exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp())}
    token = jwt.encode(payload, auth.JWT_SECRET_KEY, algorithm=auth.JWT_ALGORITHM)
    resp = renovar(client, token)
    assert resp.status_code == 401
    assert "máximo" in resp.json()["detail"]


@pytest.mark.parametrize("cabecera", [None, "Bearer basura"])
def test_renovar_sin_token_o_invalido_es_401(client, cabecera):
    headers = {"Authorization": cabecera} if cabecera else {}
    assert client.post("/api/auth/renovar", headers=headers).status_code == 401


def test_renovar_con_token_vencido_es_401(client, usuario):
    hace = datetime.now(timezone.utc) - timedelta(hours=2)
    assert renovar(client, token_con(usuario, hace, emitido=hace)).status_code == 401


def test_usuario_desactivado_no_renueva(client, session, usuario):
    token, _ = auth.create_access_token(usuario.id, usuario.role)
    usuario.is_active = False
    session.commit()
    assert renovar(client, token).status_code == 401


def test_token_de_antes_sin_ini_usa_iat(client, usuario):
    emitido = datetime.now(timezone.utc) - timedelta(minutes=10)
    token = jwt.encode({"sub": str(usuario.id), "role": usuario.role, "iat": emitido,
                        "exp": emitido + timedelta(hours=1)}, auth.JWT_SECRET_KEY, algorithm="HS256")
    resp = renovar(client, token)
    assert resp.status_code == 200
    assert datos(resp.json()["access_token"])["ini"] == int(emitido.timestamp())


def test_renovar_conserva_el_rol_actual(client, session, usuario):
    token, _ = auth.create_access_token(usuario.id, usuario.role)
    usuario.role = "Administrador"
    session.commit()
    assert datos(renovar(client, token).json()["access_token"])["role"] == "Administrador"


# --- Volver a entrar en silencio con Microsoft ------------------------------------


def test_entrar_en_silencio_conserva_el_inicio_anterior(client):
    inicio = datetime.now(timezone.utc) - timedelta(hours=4)
    resp = client.post("/api/auth/microsoft", json={"id_token": id_token(), "inicio": int(inicio.timestamp())})
    assert resp.status_code == 200, resp.text
    assert datos(resp.json()["access_token"])["ini"] == int(inicio.timestamp())


@pytest.mark.parametrize("corrimiento", [timedelta(hours=11), timedelta(hours=-1)])
def test_un_inicio_vencido_o_futuro_no_sirve_y_la_sesion_empieza_ahora(client, corrimiento):
    inicio = datetime.now(timezone.utc) - corrimiento
    resp = client.post("/api/auth/microsoft", json={"id_token": id_token(), "inicio": int(inicio.timestamp())})
    assert resp.status_code == 200
    d = datos(resp.json()["access_token"])
    assert abs(d["ini"] - d["iat"]) <= 1


def test_sin_inicio_la_sesion_empieza_ahora(client):
    d = datos(entrar(client, id_token()).json()["access_token"])
    assert abs(d["ini"] - d["iat"]) <= 1


@pytest.mark.parametrize("valor,esperado", [("", 10.0), ("8", 8.0), ("0,1", 0.1), ("x", 10.0), ("-2", 10.0)])
def test_sesion_maxima_horas_desde_el_entorno(monkeypatch, valor, esperado):
    monkeypatch.setenv("SESION_MAXIMA_HORAS", valor)
    assert auth._sesion_maxima_horas() == esperado
