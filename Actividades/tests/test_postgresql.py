"""Pruebas de compatibilidad con PostgreSQL.

Esta es la capa que mas valor ha dado: atrapa los errores que solo aparecen en
Render porque la base de produccion es PostgreSQL y la del equipo es SQLite.

Cuando las pruebas ya se ejecutan contra un PostgreSQL real (integracion
continua), el simulador sobra y se omiten: en ese escenario ya se prueba el
motor de verdad.
"""

import pytest

from tests.conftest import usando_postgresql_real

pytestmark = pytest.mark.skipif(
    usando_postgresql_real(),
    reason="ya se ejecuta contra un PostgreSQL real: el simulador no aplica",
)


class TestFormaDeLasFilas:
    """Las filas de PostgreSQL no admiten acceso por posicion.

    Regresion real: registrar_sesion usaba ``fila[0]`` y en produccion lanzo
    ``KeyError: 0``, lo que impidia iniciar sesion a todos los usuarios.
    """

    def test_el_simulador_reproduce_el_comportamiento(self, db):
        """El simulador debe fallar igual que PostgreSQL, para servir de prueba."""
        import pytest

        from tests.pg_simulado import FilaDict
        fila = FilaDict({"revision": 3})
        assert fila["revision"] == 3
        with pytest.raises(KeyError):
            fila[0]  # esto es lo que hacia fallar en Render

    def test_registrar_sesion_leyendo_por_nombre(self, db, monkeypatch, usuarios):
        """registrar_sesion debe leer la revision por nombre de columna."""
        from tests import pg_simulado

        pg_simulado.activar(db, monkeypatch, db.DB_FILE)

        assert db.registrar_sesion("token-de-prueba", "tester", "10.0.0.1") is True
        assert db.sesion_es_valida("token-de-prueba", "tester") is True

    def test_el_token_nace_en_la_revision_vigente(self, db, monkeypatch, usuarios):
        """Tras una revocacion, el token nuevo debe nacer en la revision actual.

        Si naciera en 0 con el usuario ya en 1, se invalidaria a si mismo en la
        peticion siguiente y expulsaria a su propio titular.
        """
        from tests import pg_simulado

        pg_simulado.activar(db, monkeypatch, db.DB_FILE)

        db.revocar_sesiones("tester")
        assert db.registrar_sesion("token-nuevo", "tester", "10.0.0.1") is True
        assert db.sesion_es_valida("token-nuevo", "tester") is True

    def test_listar_sesiones_devuelve_diccionarios(self, db, monkeypatch, usuarios):
        """listar_sesiones convierte cada fila; debe funcionar con ambos motores."""
        from tests import pg_simulado

        pg_simulado.activar(db, monkeypatch, db.DB_FILE)
        db.registrar_sesion("token-listado", "tester", "10.0.0.1")

        sesiones = db.listar_sesiones(usuario="tester")
        assert len(sesiones) == 1
        assert sesiones[0]["usuario"] == "tester"
        assert sesiones[0]["token"] == "token-listado"

    def test_el_login_registra_la_sesion_en_postgres(self, db, monkeypatch, app, usuarios):
        """El flujo completo de login debe funcionar con filas tipo diccionario."""
        from tests import pg_simulado

        pg_simulado.activar(db, monkeypatch, db.DB_FILE)

        cliente = app.test_client()
        pagina = cliente.get("/")
        assert pagina.status_code == 200

        import re
        token = re.search(
            r'name="csrf_token" value="([^"]+)"', pagina.get_data(as_text=True)
        ).group(1)
        respuesta = cliente.post(
            "/login",
            data={"usuario": "tester", "clave": "TesterTemporal123!",
                  "csrf_token": token},
        )
        assert respuesta.status_code == 302

        # La sesion debe quedar registrada en el servidor...
        assert len(db.listar_sesiones(usuario="tester")) == 1
        # ...y el usuario debe poder seguir operando (no ser expulsado).
        assert cliente.get("/gestion").status_code == 200


class TestTraduccionDeSql:
    """fix_query debe adaptar SQLite a PostgreSQL sin romper el SQL."""

    def test_placeholders_dentro_de_texto_no_se_convierten(self, db, monkeypatch):
        """Un '?' dentro de una cadena o comentario es texto, no un parametro."""
        monkeypatch.setattr(db, "DATABASE_URL", "postgresql://x")
        monkeypatch.setattr(db, "psycopg2", object())

        resultado = db.fix_query(
            "SELECT '?' AS literal, ? AS valor /* ? */ -- ?\nFROM t"
        )
        assert "SELECT '?'" in resultado
        assert "%s AS valor" in resultado
        assert "/* ? */" in resultado
        assert "-- ?" in resultado

    def test_insert_or_replace_se_traduce_para_postgres(self, db, monkeypatch):
        """INSERT OR REPLACE no existe en PostgreSQL."""
        monkeypatch.setattr(db, "DATABASE_URL", "postgresql://x")
        monkeypatch.setattr(db, "psycopg2", object())

        resultado = db.fix_query(
            "INSERT OR REPLACE INTO sesiones (token) VALUES (?)"
        )
        assert "INSERT OR REPLACE" not in resultado
        assert resultado.startswith("INSERT INTO sesiones")

    def test_insert_or_ignore_se_traduce_para_postgres(self, db, monkeypatch):
        monkeypatch.setattr(db, "DATABASE_URL", "postgresql://x")
        monkeypatch.setattr(db, "psycopg2", object())

        resultado = db.fix_query("INSERT OR IGNORE INTO usuarios (username) VALUES (?)")
        assert resultado == "INSERT INTO usuarios (username) VALUES (%s)"

    def test_en_sqlite_no_se_toca_la_sintaxis(self, db, monkeypatch):
        """Con SQLite el SQL debe quedarse tal cual."""
        monkeypatch.setattr(db, "DATABASE_URL", "")
        resultado = db.fix_query("INSERT OR REPLACE INTO t (a) VALUES (?)")
        assert "INSERT OR REPLACE" in resultado
        assert "?" in resultado
