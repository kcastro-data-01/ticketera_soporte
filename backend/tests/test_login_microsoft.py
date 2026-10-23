"""Inicio de sesión con Microsoft (Entra ID): el backend valida el id_token
(firma, audiencia, emisor y tenant) y entrega la sesión de la app.

Las claves son simuladas: se genera un par RSA en la prueba y se reemplaza la
lectura de la configuración pública del tenant (sin red)."""

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import select

from backend.models import User
from backend.services import login_microsoft as lm

TID = "11111111-2222-3333-4444-555555555555"
OTRO_TID = "99999999-8888-7777-6666-555555555555"
CLIENT_ID = "app-de-la-ticketera"
EMISOR = f"https://login.microsoftonline.com/{TID}/v2.0"

CLAVE = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTRA_CLAVE = rsa.generate_private_key(public_exponent=65537, key_size=2048)
# La de verdad (la fixture la reemplaza para no ir a la red).
CONFIG_OPENID = lm.config_openid


@pytest.fixture(autouse=True)
def tenant_simulado(monkeypatch):
    monkeypatch.setenv("CORREO_M365_TENANT", "data.cr")
    monkeypatch.setenv("CORREO_M365_CLIENT_ID", CLIENT_ID)
    monkeypatch.setenv("ADMIN_INICIAL", "kcastro@data.cr")
    monkeypatch.setattr(lm, "config_openid", lambda: {"issuer": EMISOR, "jwks_uri": "https://claves"})
    monkeypatch.setattr(lm, "clave_publica", lambda token, uri: CLAVE.public_key())


def id_token(clave=CLAVE, **cambios):
    ahora = datetime.now(timezone.utc)
    claims = {
        "aud": CLIENT_ID, "iss": EMISOR, "tid": TID, "iat": ahora, "nbf": ahora,
        "exp": ahora + timedelta(hours=1), "name": "Laura Méndez",
        "preferred_username": "laura@data.cr", "email": "Laura@data.cr",
    }
    claims.update(cambios)
    claims = {k: v for k, v in claims.items() if v is not None}
    return jwt.encode(claims, clave, algorithm="RS256", headers={"kid": "clave-1"})


def entrar(client, token):
    return client.post("/api/auth/microsoft", json={"id_token": token})


def yo(client, resp):
    return client.get("/api/auth/me", headers={"Authorization": f"Bearer {resp.json()['access_token']}"}).json()


def test_valid_token_creates_a_requester_and_returns_the_app_session(client, session):
    resp = entrar(client, id_token())
    assert resp.status_code == 200, resp.text
    datos = resp.json()
    assert datos["token_type"] == "bearer" and datos["expires_in"] > 0
    me = yo(client, resp)
    assert (me["name"], me["email"], me["role"]) == ("Laura Méndez", "laura@data.cr", "Solicitante")
    usuario = session.scalar(select(User).where(User.email == "laura@data.cr"))
    assert usuario.role == "Solicitante" and usuario.password_hash is None


def test_existing_user_keeps_the_role(client, session):
    session.add(User(name="Laura M.", email="laura@data.cr", role="Supervisor"))
    session.commit()
    resp = entrar(client, id_token())
    assert resp.status_code == 200
    assert yo(client, resp)["role"] == "Supervisor"
    assert session.scalar(select(User).where(User.email == "laura@data.cr")).name == "Laura M."


def test_admin_inicial_always_enters_as_administrator(client, session):
    nuevo = entrar(client, id_token(email="kcastro@data.cr", name="Kristin Castro"))
    assert yo(client, nuevo)["role"] == "Administrador"
    # Aunque alguien le haya cambiado el rol, vuelve a entrar como Administrador.
    usuario = session.scalar(select(User).where(User.email == "kcastro@data.cr"))
    usuario.role = "Solicitante"
    session.commit()
    assert yo(client, entrar(client, id_token(email="kcastro@data.cr")))["role"] == "Administrador"


def test_assign_initial_role_is_a_separate_rule(monkeypatch):
    assert lm.asignar_rol_inicial("KCastro@data.cr").value == "Administrador"
    assert lm.asignar_rol_inicial("otra@data.cr", {"jobTitle": "Técnico"}).value == "Solicitante"
    monkeypatch.delenv("ADMIN_INICIAL")
    assert lm.asignar_rol_inicial("kcastro@data.cr").value == "Solicitante"


def test_email_falls_back_to_preferred_username(client):
    resp = entrar(client, id_token(email=None, preferred_username="Ana.Perez@data.cr", name=None))
    assert yo(client, resp)["email"] == "ana.perez@data.cr"
    assert yo(client, resp)["name"] == "ana.perez"


@pytest.mark.parametrize("token", [
    pytest.param(lambda: id_token(clave=OTRA_CLAVE), id="firma-de-otra-clave"),
    pytest.param(lambda: id_token()[:-4] + "abcd", id="firma-alterada"),
    pytest.param(lambda: id_token(aud="otra-app"), id="otra-audiencia"),
    pytest.param(lambda: id_token(exp=datetime.now(timezone.utc) - timedelta(minutes=5)), id="vencido"),
    pytest.param(lambda: "no-es-un-token", id="basura"),
    pytest.param(lambda: id_token(tid=None), id="sin-tenant"),
    pytest.param(lambda: id_token(email=None, preferred_username=None), id="sin-correo"),
])
def test_invalid_tokens_are_rejected(client, session, token):
    resp = entrar(client, token())
    assert resp.status_code == 401
    assert resp.json()["detail"] == "No se pudo validar la cuenta de Microsoft"
    assert session.scalar(select(User)) is None


@pytest.mark.parametrize("cambios", [
    pytest.param({"iss": f"https://login.microsoftonline.com/{OTRO_TID}/v2.0", "tid": OTRO_TID}, id="otro-emisor"),
    pytest.param({"tid": OTRO_TID}, id="otro-tid-con-el-emisor-de-la-empresa"),
])
def test_accounts_from_another_tenant_are_rejected(client, session, cambios):
    resp = entrar(client, id_token(**cambios))
    assert resp.status_code == 401
    assert session.scalar(select(User)) is None


def test_deactivated_user_cannot_enter(client, session):
    session.add(User(name="Laura", email="laura@data.cr", role="Técnico", is_active=False))
    session.commit()
    assert entrar(client, id_token()).status_code == 403


def test_without_configuration_the_login_is_unavailable(client, monkeypatch):
    monkeypatch.setenv("CORREO_M365_CLIENT_ID", "")
    assert entrar(client, id_token()).status_code == 503


def test_public_config_for_the_login_page(client):
    assert client.get("/api/auth/config").json() == {
        "tenant": "data.cr", "client_id": CLIENT_ID, "login_local": True,
    }


def test_tenant_configuration_is_read_once(monkeypatch):
    """El emisor y las claves salen de la configuración pública del tenant."""
    llamadas = []

    class Respuesta:
        def raise_for_status(self):
            pass

        def json(self):
            return {"issuer": EMISOR, "jwks_uri": f"https://login.microsoftonline.com/{TID}/discovery/v2.0/keys"}

    monkeypatch.setenv("CORREO_M365_TENANT", "tenant-de-prueba.cr")
    monkeypatch.setattr(lm, "_cache_openid", {})
    monkeypatch.setattr(lm.httpx, "get", lambda url, timeout: llamadas.append(url) or Respuesta())
    assert CONFIG_OPENID()["issuer"] == EMISOR
    assert CONFIG_OPENID()["jwks_uri"].endswith("/discovery/v2.0/keys")
    assert llamadas == ["https://login.microsoftonline.com/tenant-de-prueba.cr/v2.0/.well-known/openid-configuration"]
