"""Tests del inicio de sesión con msal (device code) usando un msal falso."""

import json

import pytest

from backend import correo_login
from backend.services import correo_auth as ca


class FakeApp:
    """Imita lo que se usa de msal.PublicClientApplication."""

    def __init__(self, cache, cuentas=(), silencioso=None, flujo=None, dispositivo=None):
        self.cache = cache
        self.cuentas = list(cuentas)
        self.silencioso = silencioso
        self.flujo = flujo or {"user_code": "ABC123",
                               "message": "Para iniciar sesión, abre https://microsoft.com/devicelogin "
                                          "y escribe el código ABC123."}
        self.dispositivo = dispositivo
        self.pedidos = []

    def get_accounts(self, username=None):
        if username:
            return [c for c in self.cuentas if c["username"] == username]
        return self.cuentas

    def acquire_token_silent(self, scopes, account):
        self.pedidos.append((scopes, account["username"]))
        return self.silencioso

    def initiate_device_flow(self, scopes):
        self.pedidos.append(("device", scopes))
        return self.flujo

    def acquire_token_by_device_flow(self, flujo):
        # msal escribe la caché al obtener el token.
        self.cache.deserialize(json.dumps({"AccessToken": {"x": {"secret": "t"}}}))
        self.cache.has_state_changed = True
        return self.dispositivo


def fabrica(**kwargs):
    creadas = []

    def crear(tenant, client_id, cache):
        app = FakeApp(cache, **kwargs)
        creadas.append((tenant, client_id, app))
        return app

    return crear, creadas


def test_silent_token_from_cache(tmp_path):
    cache = tmp_path / "cache.json"
    cache.write_text("{}")
    crear, creadas = fabrica(cuentas=[{"username": "kcastro@data.cr"}],
                             silencioso={"access_token": "abc"})
    token = ca.ProveedorToken("tenant", "cliente", "kcastro@data.cr", cache, crear=crear)
    assert token.obtener() == "abc"
    tenant, client_id, app = creadas[0]
    assert (tenant, client_id) == ("tenant", "cliente")
    assert app.pedidos == [(ca.PERMISOS, "kcastro@data.cr")]
    assert ca.PERMISOS == ["Mail.ReadWrite", "Mail.Send", "User.Read"]


@pytest.mark.parametrize("cuentas,silencioso,crear_archivo,mensaje", [
    ([], None, False, "no existe la caché"),
    ([], None, True, "ninguna cuenta"),
    ([{"username": "kcastro@data.cr"}], None, True, "venció"),
    ([{"username": "kcastro@data.cr"}], {"error_description": "AADSTS700082 expiró"}, True, "AADSTS"),
])
def test_missing_or_expired_session_raises(tmp_path, cuentas, silencioso, crear_archivo, mensaje):
    cache = tmp_path / "cache.json"
    if crear_archivo:
        cache.write_text("{}")
    crear, _ = fabrica(cuentas=cuentas, silencioso=silencioso)
    token = ca.ProveedorToken("t", "c", "kcastro@data.cr", cache, crear=crear)
    with pytest.raises(ca.SinSesionError, match=mensaje):
        token.obtener()


def test_app_is_created_once_and_cache_reloaded_when_file_changes(tmp_path):
    cache = tmp_path / "cache.json"
    cache.write_text("{}")
    crear, creadas = fabrica(cuentas=[{"username": "kcastro@data.cr"}],
                             silencioso={"access_token": "abc"})
    token = ca.ProveedorToken("t", "c", "kcastro@data.cr", cache, crear=crear)
    token.obtener()
    token.obtener()
    assert len(creadas) == 1
    app = creadas[0][2]
    leidos = []
    app.cache.deserialize = leidos.append
    cache.write_text('{"AccessToken": {}}')
    import os
    os.utime(cache, ns=(1, 1))  # fecha distinta: archivo cambiado
    token.obtener()
    assert leidos == ['{"AccessToken": {}}']


def test_real_msal_cache_round_trip(tmp_path):
    ruta = tmp_path / "cache.json"
    cache = ca.cargar_cache(ruta)
    cache.has_state_changed = True
    ca.guardar_cache(cache, ruta)
    assert ruta.exists()
    assert oct(ruta.stat().st_mode & 0o777) == "0o600"
    assert ca.cargar_cache(ruta).serialize()


def test_missing_ids_raise():
    with pytest.raises(ca.SinSesionError, match="CORREO_M365"):
        ca.ProveedorToken("", "", "x@y", ca.CACHE_POR_DEFECTO).obtener()


def test_device_code_login_prints_code_and_saves_cache(tmp_path):
    cache = tmp_path / "sub" / "cache.json"
    crear, _ = fabrica(dispositivo={"access_token": "abc",
                                    "id_token_claims": {"preferred_username": "kcastro@data.cr"}})
    salida = []
    resultado = ca.iniciar_sesion("t", "c", cache, imprimir=salida.append, crear=crear)
    assert "microsoft.com/devicelogin" in salida[0]
    assert "ABC123" in salida[0]
    assert resultado["access_token"] == "abc"
    assert cache.exists()
    assert "AccessToken" in cache.read_text()


def test_device_code_login_failure(tmp_path):
    crear, _ = fabrica(dispositivo={"error_description": "el usuario canceló"})
    with pytest.raises(ca.SinSesionError, match="canceló"):
        ca.iniciar_sesion("t", "c", tmp_path / "c.json", imprimir=lambda m: None, crear=crear)


def test_cache_path_from_env(tmp_path):
    assert ca.ruta_cache(str(tmp_path / "x.json")) == tmp_path / "x.json"
    assert ca.ruta_cache("") == ca.CACHE_POR_DEFECTO


def test_cache_file_is_ignored_by_git():
    from backend.database import PROJECT_ROOT

    assert ".msal_cache.json" in (PROJECT_ROOT / ".gitignore").read_text()


# --- Comando correo_login ------------------------------------------------------


def test_login_command_requires_tenant_and_client():
    salida = []
    assert correo_login.main(env={}, imprimir=salida.append) == 1
    assert "CORREO_M365_TENANT" in salida[0]


def test_login_command_success_and_warns_on_other_account(tmp_path, engine):
    from sqlalchemy.orm import sessionmaker

    salida = []
    usados = []

    def iniciar(tenant, client_id, cache, imprimir):
        usados.append((tenant, client_id, cache))
        imprimir("Abre https://microsoft.com/devicelogin y escribe ABC123")
        return {"access_token": "x", "id_token_claims": {"preferred_username": "Otra@data.cr"}}

    env = {"CORREO_M365_TENANT": "t", "CORREO_M365_CLIENT_ID": "c",
           "CORREO_USUARIO": "kcastro@data.cr", "CORREO_M365_CACHE": str(tmp_path / "c.json")}
    assert correo_login.main(env=env, imprimir=salida.append, iniciar=iniciar,
                             session_factory=sessionmaker(bind=engine)) == 0
    # Los tokens van a la base; el archivo de antes solo se importa.
    [(tenant, client_id, almacen)] = usados
    assert (tenant, client_id) == ("t", "c")
    assert isinstance(almacen, ca.AlmacenBD) and almacen.importar_de == tmp_path / "c.json"
    assert any("devicelogin" in s for s in salida)
    assert any("otra@data.cr" in s for s in salida)
    assert any("ATENCIÓN" in s for s in salida)


def test_login_command_reports_failure(tmp_path):
    def iniciar(*args, **kwargs):
        raise ca.SinSesionError("AADSTS7000218: falta permitir flujos de clientes públicos")

    salida = []
    env = {"CORREO_M365_TENANT": "t", "CORREO_M365_CLIENT_ID": "c"}
    assert correo_login.main(env=env, imprimir=salida.append, iniciar=iniciar,
                             session_factory=lambda: None) == 1
    assert "AADSTS7000218" in salida[0]
