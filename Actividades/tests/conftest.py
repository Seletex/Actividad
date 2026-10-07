"""Configuracion comun de las pruebas.

REGLA INNEGOCIABLE
------------------
Ninguna prueba puede tocar las bases de datos reales (las de la carpeta de red,
las de AppData ni la de PostgreSQL). Para garantizarlo, este archivo:

1. Redirige TODAS las rutas de datos a una carpeta temporal.
2. Activa ACTIVIDADES_SKIP_OFFLINE_SYNC=1, que impide que la aplicacion
   busque y mezcle bases de datos de la red o de la carpeta del programa.
3. Verifica al final que la base en uso este dentro del directorio temporal.

Si alguien ejecuta las pruebas sin este aislamiento, el archivo test_aislamiento
falla de forma explicita en vez de modificar informacion real. Se agrego porque
en el pasado una prueba sin aislamiento termino mezclando datos de la red.
"""

import atexit
import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

# --- 1. Aislamiento ANTES de importar cualquier modulo de la aplicacion -----
RAIZ_PROYECTO = Path(__file__).resolve().parent.parent
if str(RAIZ_PROYECTO) not in sys.path:
    sys.path.insert(0, str(RAIZ_PROYECTO))

# Una carpeta por proceso: evita que dos ejecuciones simultaneas (o un
# subproceso) se borren la base de datos mutuamente.
_SALA_TEMPORAL = Path(tempfile.gettempdir()) / f"actividades_pruebas_{os.getpid()}"


def _limpiar_sala_al_salir():
    shutil.rmtree(_SALA_TEMPORAL, ignore_errors=True)


atexit.register(_limpiar_sala_al_salir)

if _SALA_TEMPORAL.exists():
    shutil.rmtree(_SALA_TEMPORAL, ignore_errors=True)

_DIR_DATOS = _SALA_TEMPORAL / "data"
_DIR_LOCALAPPDATA = _SALA_TEMPORAL / "localappdata"
_DIR_DATOS.mkdir(parents=True, exist_ok=True)
_DIR_LOCALAPPDATA.mkdir(parents=True, exist_ok=True)

# PostgreSQL real solo se usa en integracion continua, donde la base es un
# contenedor efimero sin datos. Para activarlo se define ACTIVIDADES_TEST_PG=1
# y la URL debe apuntar a la maquina local: si apunta a otro sitio (por ejemplo
# la base de Render) la suite se niega a arrancar en lugar de borrar la
# informacion de la entidad.
_USAR_POSTGRESQL = os.environ.get("ACTIVIDADES_TEST_PG", "") in ("1", "true", "yes")

if _USAR_POSTGRESQL:
    _url = os.environ.get("DATABASE_URL", "")
    _host_seguro = any(h in _url for h in ("localhost", "127.0.0.1", "postgres:"))
    if not _url or not _host_seguro:
        raise RuntimeError(
            "ACTIVIDADES_TEST_PG=1 exige un DATABASE_URL de PostgreSQL local "
            "(localhost). Se rechaza '" + (_url or "(vacia)") + "' para no "
            "conectarse a una base con datos reales."
        )
else:
    os.environ["DATABASE_URL"] = ""    # fuerza SQLite, nunca PostgreSQL real

os.environ["ACTIVIDADES_CENTRAL_DIR"] = str(_DIR_DATOS)
os.environ["ACTIVIDADES_SKIP_OFFLINE_SYNC"] = "1"   # prohibido sincronizar con la red
os.environ["LOCALAPPDATA"] = str(_DIR_LOCALAPPDATA)
os.environ["ADMIN_INITIAL_PASSWORD"] = ""           # evita el arranque de admin
os.environ["TRUST_PROXY"] = "false"
os.environ.pop("RENDER", None)
os.environ.pop("FLASK_SECRET_KEY", None)

if _USAR_POSTGRESQL:
    # Con base de datos configurada la app exige una clave de sesion. Se define
    # despues de borrarla arriba, porque si no se perderia. Es una clave
    # desechable: la base es un contenedor efimero de pruebas.
    os.environ["FLASK_SECRET_KEY"] = "clave-desechable-solo-para-pruebas"


# --- 2. Fixtures compartidos ------------------------------------------------

@pytest.fixture(scope="session")
def carpeta_temporal():
    """Carpeta temporal donde viven los datos de las pruebas."""
    return _SALA_TEMPORAL


@pytest.fixture(scope="session")
def db():
    """Modulo database, ya importado con el aislamiento aplicado."""
    import database
    database.inicializar_tablas()
    return database


@pytest.fixture(scope="session")
def modulo_app(db):
    """Importa la aplicacion una sola vez por sesion de pruebas.

    Importarla dispara ``initialize_app()``, que ademas carga el Excel del
    proyecto en la base de datos. Por eso las pruebas limpian DESPUES de este
    paso (ver ``datos_limpios``).
    """
    import app as modulo
    return modulo


def ejecutar(db, sentencia, parametros=()):
    """Ejecuta SQL funciona igual en SQLite y en PostgreSQL.

    No se puede usar ``conn.execute(...)``: la conexion de psycopg2 no tiene ese
    metodo. Hay que pasar por ``get_cursor``, que es lo que hace la aplicacion.
    """
    with db.db_session() as conn:
        cursor = db.get_cursor(conn)
        cursor.execute(db.fix_query(sentencia), parametros)


def consultar(db, sentencia, parametros=()):
    """Devuelve las filas como tuplas, sin depender del motor.

    Con PostgreSQL las filas son diccionarios, y ``fila[0]`` lanzaria
    ``KeyError``. Por eso se convierten a tupla por nombre de columna, con la
    misma precaution que se aplico en ``registrar_sesion``.
    """
    with db.db_session() as conn:
        cursor = db.get_cursor(conn)
        cursor.execute(db.fix_query(sentencia), parametros)
        filas = cursor.fetchall()
        if filas and isinstance(filas[0], dict):
            columnas = list(filas[0].keys())
            return [tuple(f[c] for c in columnas) for f in filas]
        return [tuple(f) for f in filas]


def usando_postgresql_real():
    """True si las pruebas se estan ejecutando contra un PostgreSQL real."""
    return os.environ.get("ACTIVIDADES_TEST_PG", "") in ("1", "true", "yes")


@pytest.fixture(autouse=True)
def datos_limpios(db, modulo_app):
    """Vacia las tablas de negocio antes de cada prueba.

    El orden importa: depende de ``modulo_app`` para ejecutarse despues de
    que la aplicacion arranco y cargo el Excel. Si se limpiara antes, las
    pruebas verian los 1.605 registros reales y los IDs no coincidirian.

    No toca usuarios ni configuracion: cada prueba define los que necesita.
    """
    ejecutar(db, "DELETE FROM registros")
    ejecutar(db, "DELETE FROM sesiones")
    assert db.cargar_registros(None).empty, "la limpieza no dejo registros"
    yield


@pytest.fixture
def usuarios(db):
    """Crea usuarios de prueba y les asigna contrasena."""
    data = db.cargar_usuarios()
    data["usuarios"] = ["admin", "tester"]
    assert db.guardar_usuarios(data), "no se pudieron guardar los usuarios"
    assert db.establecer_contrasena("admin", "AdminTemporal123!")
    assert db.establecer_contrasena("tester", "TesterTemporal123!")
    return {"admin": "AdminTemporal123!", "tester": "TesterTemporal123!"}


@pytest.fixture
def app(modulo_app, usuarios):
    """Aplicacion Flask lista para probar."""
    return modulo_app.app


@pytest.fixture
def cliente(app):
    """Cliente HTTP de Flask."""
    return app.test_client()


@pytest.fixture
def otro_cliente(app):
    """Segundo cliente, independiente del primero.

    Simula otro dispositivo (u otra pestana): tiene su propia cookie de sesion,
    de modo que ambos pueden estar conectados al mismo tiempo.
    """
    return app.test_client()


@pytest.fixture
def entrar_en(app):
    """Fabrica un login en cualquier cliente y con cualquier usuario.

    Se usa para simular dos equipos con sesiones simultaneas, que es el caso
    que interesa cuando se prueba la revocacion.
    """
    import re

    def entrar(cliente_http, usuario="tester", clave="TesterTemporal123!"):
        pagina = cliente_http.get("/")
        token = re.search(
            r'name="csrf_token" value="([^"]+)"', pagina.get_data(as_text=True)
        ).group(1)
        respuesta = cliente_http.post("/login", data={
            "usuario": usuario, "clave": clave, "csrf_token": token,
        })
        assert respuesta.status_code == 302, "el login deberia redirigir"
        return respuesta

    return entrar


@pytest.fixture
def token_de(app):
    """Extrae el token CSRF de cualquier cliente, justo antes de usarlo."""

    import re

    def obtener(cliente_http):
        pagina = cliente_http.get("/")
        coincidencia = re.search(
            r'name="csrf_token" value="([^"]+)"', pagina.get_data(as_text=True)
        )
        assert coincidencia, "no se encontro el token CSRF en la pagina"
        return coincidencia.group(1)

    return obtener


@pytest.fixture
def token_csrf(cliente):
    """Devuelve una funcion que entrega el token CSRF vigente.

    Importante: el token se rota en cada inicio de sesion (``session.clear()``
    lo borra y se genera uno nuevo). Por eso hay que pedirlo justo antes de
    cada envio y no guardarlo en una variable.
    """
    import re

    def obtener():
        pagina = cliente.get("/")
        coincidencia = re.search(
            r'name="csrf_token" value="([^"]+)"', pagina.get_data(as_text=True)
        )
        assert coincidencia, "no se encontro el token CSRF en la pagina"
        return coincidencia.group(1)

    return obtener


@pytest.fixture
def iniciar_sesion(cliente, token_csrf):
    """Fabrica una funcion para entrar con un usuario de prueba."""

    def entrar(usuario="tester", clave="TesterTemporal123!"):
        respuesta = cliente.post(
            "/login",
            data={"usuario": usuario, "clave": clave, "csrf_token": token_csrf()},
        )
        assert respuesta.status_code == 302, "el login deberia redirigir"
        return respuesta

    return entrar


@pytest.fixture
def como_admin(cliente, token_csrf):
    """Cliente con la sesion de administrador iniciada."""
    respuesta = cliente.post(
        "/login",
        data={
            "usuario": "admin",
            "clave": "AdminTemporal123!",
            "csrf_token": token_csrf(),
        },
    )
    assert respuesta.status_code == 302
    return cliente


@pytest.fixture
def registrar(db):
    """Inserta un registro directamente en la base de datos."""

    def _registrar(usuario="tester", actividad="Actividad de prueba",
                   fecha="2026-09-01 08:00:00", fecha_atencion="2026-09-10",
                   solicitante="Solicitante", tipo_solicitud="Asistencia",
                   medio_solicitud="Email", descripcion="Descripcion",
                   cumplido="Sí", dependencia="Dependencia",
                   observaciones="Observaciones"):
        ejecutar(db,
            """INSERT INTO registros
               (usuario, tipo_actividad, fecha, dependencia, solicitante,
                tipo_solicitud, medio_solicitud, descripcion, cumplido,
                fecha_atencion, observaciones, borrado)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,0)""",
            (usuario, actividad, fecha, dependencia, solicitante,
             tipo_solicitud, medio_solicitud, descripcion, cumplido,
             fecha_atencion, observaciones),
        )
        return True

    return _registrar
