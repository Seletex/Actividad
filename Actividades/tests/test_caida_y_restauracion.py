"""Pruebas de la caída de la base de datos y de la restauración.

Regresión real: cuando Render eliminó la base PostgreSQL gratuita (esas bases
expiran a los 30 días), la aplicación respondía "Contraseña incorrecta" a
todos los usuarios y además consumía sus intentos de acceso, lo que terminaba
bloqueando la IP del equipo por 15 minutos.

Aquí se comprueba que:
  - una caída de la base se informa como caída y no como error del usuario;
  - una caída de la base no cuenta como intento fallido;
  - existe un punto de consulta del estado del servicio;
  - la restauración desde el navegador recupera también los catálogos.
"""

import json

import pytest

from tests.conftest import consultar, ejecutar, usando_postgresql_real


class TestBaseDeDatosCaida:
    """La caída de la base de datos no es un error del usuario."""

    def test_el_login_no_dice_contrasena_incorrecta(self, modulo_app, cliente, token_de,
                                                     monkeypatch):
        """Con la base caída el mensaje debe hablar del servicio, no de la clave."""
        monkeypatch.setattr(
            modulo_app, "verificar_credenciales", lambda usuario, clave: (False, "error_bd")
        )

        pagina = cliente.get("/")
        token = token_de(cliente)
        respuesta = cliente.post(
            "/login",
            data={"usuario": "tester", "clave": "cualquiera", "csrf_token": token},
        )
        assert respuesta.status_code == 302

        destino = respuesta.headers.get("Location", "")
        assert "error_bd" not in destino
        assert "Contrase%C3%B1a+incorrecta" not in destino
        assert "fuera+de+servicio" in destino or "fuera%20de%20servicio" in destino

    def test_la_caida_no_registra_intento_fallido(self, modulo_app, cliente, token_de,
                                                   monkeypatch):
        """Repetir el ingreso con la base caída no debe bloquear la IP.

        Con el comportamiento anterior, diez intentos bastaban para que el
        equipo quedara fifteen minutos sin poder entrar.
        """
        import web_security

        monkeypatch.setattr(
            modulo_app, "verificar_credenciales", lambda usuario, clave: (False, "error_bd")
        )

        ip = "203.0.113.9"
        web_security._login_attempts.pop(ip, None)

        for _ in range(15):
            pagina = cliente.get("/")
            token = token_de(cliente)
            cliente.post(
                "/login",
                data={"usuario": "tester", "clave": "cualquiera", "csrf_token": token},
                environ_base={"REMOTE_ADDR": ip},
            )

        assert not web_security.login_bloqueado(ip), (
            "la caida de la base de datos no debe bloquear al usuario"
        )

    def test_una_contrasena_mala_si_cuenta_como_intento(self, modulo_app, cliente, token_de,
                                                       monkeypatch):
        """En cambio, una contraseña realmente incorrecta sí debe contar."""
        import web_security

        monkeypatch.setattr(
            modulo_app, "verificar_credenciales",
            lambda usuario, clave: (False, "clave_incorrecta")
        )

        ip = "203.0.113.10"
        web_security._login_attempts.pop(ip, None)

        pagina = cliente.get("/")
        token = token_de(cliente)
        cliente.post(
            "/login",
            data={"usuario": "tester", "clave": "mala", "csrf_token": token},
            environ_base={"REMOTE_ADDR": ip},
        )

        assert web_security.login_bloqueado(ip) is False
        assert ip in web_security._login_attempts, (
            "el intento fallido debe quedar registrado"
        )

    def test_verificar_credenciales_distingue_el_error_de_base(self, db, monkeypatch):
        """El modulo de base de datos debe avisar que fallo la conexion."""
        def _fallar():
            raise RuntimeError("no hay conexion con el servidor")

        monkeypatch.setattr(db, "get_db_connection", _fallar)

        ok, motivo = db.verificar_credenciales("tester", "clave")
        assert ok is False
        assert motivo == "error_bd", (
            "un fallo de conexion debe distinguirse de una clave incorrecta"
        )


class TestEstadoDelServicio:
    """El punto /salud dice si la base de datos responde."""

    def test_salud_informa_los_registros(self, app, cliente):
        respuesta = cliente.get("/salud")
        assert respuesta.status_code == 200

        datos = json.loads(respuesta.get_data(as_text=True))
        assert datos["servicio"] == "ok"
        assert datos["base_datos"] == "ok"
        assert isinstance(datos["registros"], int)

    def test_salud_avisa_cuando_la_base_no_responde(self, app, cliente, monkeypatch):
        import database

        def _fallar():
            raise RuntimeError("no hay conexion con el servidor")

        monkeypatch.setattr(database, "get_db_connection", _fallar)

        respuesta = cliente.get("/salud")
        assert respuesta.status_code == 503

        datos = json.loads(respuesta.get_data(as_text=True))
        assert datos["base_datos"] == "no disponible"
        assert datos["servicio"] == "degradado"


class TestArranqueResiliente:
    """La aplicación debe sobrevivir a una base de datos caída."""

    def test_un_fallo_de_base_muestra_el_aviso_de_servicio_caido(
        self, modulo_app, cliente, entrar_en, monkeypatch
    ):
        """Una consulta que falla debe dar un aviso claro, no un error 500."""
        import psycopg2

        entrar_en(cliente, "tester", "TesterTemporal123!")

        def _fallar(*args, **kwargs):
            raise psycopg2.OperationalError(
                'could not translate host name "dpg-inexistente" to address'
            )

        monkeypatch.setattr(modulo_app, "cargar_registros", _fallar)

        respuesta = cliente.get("/listado")
        assert respuesta.status_code == 503
        texto = respuesta.get_data(as_text=True)
        assert "temporalmente no disponible" in texto
        assert "Sus datos no se han perdido" in texto

    def test_la_aplicacion_arranca_aunque_la_base_no_responda(
        self, modulo_app, db, monkeypatch
    ):
        """Un arranque con la base caída no debe tumbar el servicio."""
        def _fallar():
            raise RuntimeError("no hay conexion con el servidor")

        monkeypatch.setattr(db, "inicializar_usuarios", _fallar)

        # No debe lanzar excepcion: el servicio tiene que quedar en pie para
        # poder avisar al usuario y mostrar el estado en /salud.
        modulo_app.initialize_app()


@pytest.mark.skipif(
    not usando_postgresql_real(),
    reason="la herramienta de restauración se prueba contra un PostgreSQL real",
)
class TestHerramientaDeRestauracion:
    """La herramienta que se usa para recuperar la base tras una caída."""

    def _crear_origen(self, ruta):
        import sqlite3

        conexion = sqlite3.connect(ruta)
        conexion.executescript(
            """
            CREATE TABLE usuarios (
                username TEXT PRIMARY KEY, password_hash TEXT, password_salt TEXT,
                debe_cambiar_contrasena INTEGER DEFAULT 0
            );
            CREATE TABLE actividades_personales (
                username TEXT, actividad TEXT, UNIQUE(username, actividad)
            );
            CREATE TABLE configuracion_usuario (
                username TEXT, clave TEXT, valor TEXT, PRIMARY KEY (username, clave)
            );
            CREATE TABLE listas_globales (
                tipo TEXT, valor TEXT, UNIQUE(tipo, valor)
            );
            CREATE TABLE registros (
                id INTEGER PRIMARY KEY, usuario TEXT, tipo_actividad TEXT, fecha TEXT,
                dependencia TEXT, solicitante TEXT, tipo_solicitud TEXT,
                medio_solicitud TEXT, descripcion TEXT, cumplido TEXT,
                fecha_atencion TEXT, observaciones TEXT, sync_uid TEXT,
                updated_at TEXT, borrado INTEGER DEFAULT 0
            );
            """
        )
        conexion.execute(
            "INSERT INTO usuarios (username, password_hash) VALUES (?, ?)",
            ("pruebacopia", ""),
        )
        conexion.execute(
            "INSERT INTO actividades_personales (username, actividad) VALUES (?, ?)",
            ("pruebacopia", "Actividad de la copia"),
        )
        conexion.execute(
            "INSERT INTO configuracion_usuario (username, clave, valor) VALUES (?, ?, ?)",
            ("pruebacopia", "dependencia", '"Oficina"'),
        )
        conexion.execute(
            "INSERT INTO listas_globales (tipo, valor) VALUES (?, ?)",
            ("ubicacion", "Dependencia copiada"),
        )
        conexion.execute(
            "INSERT INTO registros (id, usuario, tipo_actividad, fecha, dependencia, "
            "solicitante, tipo_solicitud, medio_solicitud, descripcion, cumplido, "
            "fecha_atencion, observaciones, sync_uid, updated_at, borrado) "
            "VALUES (900001, 'pruebacopia', 'Copia', '2026-10-01 08:00:00', "
            "'Oficina', 'Solicitante', 'Tipo', 'Medio', 'Descripcion', 'Si', "
            "'2026-10-01', 'Observacion', 'uid-copia', '2026-10-01 08:00:00', 0)"
        )
        conexion.commit()
        conexion.close()

    def test_el_script_copia_los_datos_de_un_archivo_local(self, db, tmp_path):
        import os
        import subprocess
        import sys
        from pathlib import Path

        origen = tmp_path / "origen.db"
        self._crear_origen(origen)

        script = Path(__file__).resolve().parent.parent / "restaurar_produccion.py"
        url = os.environ.get("DATABASE_URL", "")
        assert url, "se necesita DATABASE_URL para esta prueba"

        try:
            resultado = subprocess.run(
                [
                    sys.executable, str(script),
                    "--url", url,
                    "--local", str(origen),
                    "--modo", "combinar",
                ],
                capture_output=True,
                text=True,
                timeout=300,
            )
            assert resultado.returncode == 0, resultado.stdout + resultado.stderr

            usuarios = consultar(db, "SELECT username FROM usuarios WHERE username = ?",
                                  ("pruebacopia",))
            assert usuarios == [("pruebacopia",)]

            actividades = consultar(
                db, "SELECT actividad FROM actividades_personales WHERE username = ?",
                ("pruebacopia",),
            )
            assert actividades == [("Actividad de la copia",)]

            configuracion = consultar(
                db, "SELECT valor FROM configuracion_usuario WHERE username = ? AND clave = ?",
                ("pruebacopia", "dependencia"),
            )
            assert configuracion == [('"Oficina"',)]

            listas = consultar(
                db, "SELECT valor FROM listas_globales WHERE tipo = ? AND valor = ?",
                ("ubicacion", "Dependencia copiada"),
            )
            assert listas == [("Dependencia copiada",)]

            registros = consultar(
                db, "SELECT usuario, descripcion FROM registros WHERE id = ?", (900001,)
            )
            assert registros == [("pruebacopia", "Descripcion")]
        finally:
            ejecutar(db, "DELETE FROM registros WHERE id = ?", (900001,))
            ejecutar(db, "DELETE FROM usuarios WHERE username = ?", ("pruebacopia",))
            ejecutar(db, "DELETE FROM actividades_personales WHERE username = ?",
                    ("pruebacopia",))
            ejecutar(db, "DELETE FROM configuracion_usuario WHERE username = ?",
                    ("pruebacopia",))
            ejecutar(db, "DELETE FROM listas_globales WHERE valor = ?",
                    ("Dependencia copiada",))


class TestRestauracionDesdeElNavegador:
    """El JSON de un respaldo debe devolver los catalogos completos."""

    def test_las_listas_globales_se_restauran_desde_el_json(self, db, tmp_path):
        """El respaldo guarda "ubicaciones"; el importador debe leerlas.

        Con el nombre anterior ("dependencias") el catalogo de ubicaciones se
        perdia en cada restauracion hecha desde el navegador.
        """
        from user_data_service import sincronizar_datos_usuarios

        ejecutar(db, "DELETE FROM listas_globales")

        archivo = tmp_path / "usuarios.json"
        archivo.write_text(
            json.dumps(
                {
                    "usuarios": ["restaurado"],
                    "actividades": {},
                    "configuraciones": {},
                    "listas_globales": {
                        "actividades": ["Actividad de prueba"],
                        "ubicaciones": ["Oficina de Sistemas"],
                        "tipos_solicitud": ["Tipo de prueba"],
                        "medios_solicitud": ["Medio de prueba"],
                    },
                }
            ),
            encoding="utf-8",
        )

        resultado = sincronizar_datos_usuarios(str(archivo))
        assert resultado["resumen"]["listas"] >= 4

        tipos = {
            fila[0]: fila[1]
            for fila in consultar(db, "SELECT tipo, valor FROM listas_globales")
        }
        valores = set(tipos.values())
        assert "Oficina de Sistemas" in valores
        assert "Actividad de prueba" in valores
        assert "Tipo de prueba" in valores
        assert "Medio de prueba" in valores

    def test_el_archivo_de_listas_globales_tambien_se_acepta(self, db, tmp_path):
        """Un "listas_globales.json" suelto tambien debe servir."""
        from user_data_service import sincronizar_datos_usuarios

        ejecutar(db, "DELETE FROM listas_globales")

        archivo = tmp_path / "listas_globales.json"
        archivo.write_text(
            json.dumps(
                {
                    "actividades": ["Actividad suelta"],
                    "ubicaciones": ["Dependencia suelta"],
                    "tipos_solicitud": [],
                    "medios_solicitud": [],
                }
            ),
            encoding="utf-8",
        )

        sincronizar_datos_usuarios(str(archivo))

        valores = {
            fila[0] for fila in consultar(db, "SELECT valor FROM listas_globales")
        }
        assert "Actividad suelta" in valores
        assert "Dependencia suelta" in valores
