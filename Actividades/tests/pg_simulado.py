"""Simulador del driver de PostgreSQL para poder probar sin servidor.

Por que existe
--------------
Render usa PostgreSQL; el equipo de escritorio usa SQLite. Los dos devuelven las
filas de forma distinta:

- SQLite: ``sqlite3.Row`` admite ``fila[0]`` y ``fila['columna']``.
- PostgreSQL: ``RealDictRow`` (de ``RealDictCursor``) es un diccionario y
  **no** admite ``fila[0]``: lanza ``KeyError``.

Gracias a esa diferencia, un codigo puede pasar todas las pruebas locales y
fallar en produccion. Ya ocurrio: ``registrar_sesion`` usaba ``fila[0]`` y
rompio el inicio de sesion en Render.

Este modulo reproduce el comportamiento de PostgreSQL sobre un SQLite en
memoria, sin necesidad de instalar un servidor. Si el codigo usa acceso
posicional a una fila, aqui falla igual que en Render.
"""

import re
import sqlite3


class FilaDict(dict):
    """Fila tipo RealDictRow: acceso por nombre, nunca por posicion."""

    def __getitem__(self, clave):
        if isinstance(clave, int):
            raise KeyError(clave)
        return dict.__getitem__(self, clave)


class CursorPostgresSimulado:
    """Cursor que devuelve filas como diccionario y traduce sintaxis de PG."""

    def __init__(self, conexion):
        self._conexion = conexion
        self._filas = []
        self.rowcount = -1

    # -- Traduccion de sentencias -------------------------------------------
    @staticmethod
    def _traducir(sql):
        """Convierte sintaxis exclusiva de PostgreSQL a su equivalente SQLite."""
        if re.search(r"\bsetval\s*\(", sql, re.IGNORECASE):
            return None  # secuencia de PostgreSQL: no aplica en SQLite
        if re.match(
            r"\s*(CREATE SEQUENCE|ALTER TABLE \S+ ALTER COLUMN)", sql, re.IGNORECASE
        ):
            return None

        consulta = sql
        if "%s" in consulta:
            consulta = consulta.replace("%s", "?")
        if re.search(r"ON CONFLICT\s+DO NOTHING", consulta, re.IGNORECASE):
            consulta = re.sub(r"\s+ON CONFLICT\s+DO NOTHING", "", consulta,
                              flags=re.IGNORECASE)
            consulta = re.sub(r"INSERT INTO", "INSERT OR IGNORE INTO", consulta,
                              flags=re.IGNORECASE)

        coincidencia = re.match(
            r"\s*ALTER TABLE (\S+) ADD COLUMN IF NOT EXISTS (\S+) (.*)",
            consulta, re.IGNORECASE,
        )
        if coincidencia:
            tabla, columna, resto = coincidencia.groups()
            return ("__si_ya_existe__", tabla, columna,
                    f'ALTER TABLE "{tabla}" ADD COLUMN "{columna}" {resto}')
        return consulta

    # -- API de cursor -------------------------------------------------------
    def execute(self, sql, parametros=None):
        real = self._conexion.cursor()
        traducida = self._traducir(sql)

        if traducida is None:
            self._filas = []
            self.rowcount = -1
            return self

        if isinstance(traducida, tuple):
            _, tabla, columna, alternativa = traducida
            ya_existe = any(
                fila[1].lower() == columna.lower()
                for fila in real.execute(f'PRAGMA table_info("{tabla}")').fetchall()
            )
            if ya_existe:
                self._filas = []
                return self
            traducida = alternativa

        real.execute(traducida, parametros or ())
        self.rowcount = real.rowcount

        if traducida.strip().upper().startswith("SELECT"):
            nombres = [c[0] for c in real.description]
            self._filas = [FilaDict(dict(zip(nombres, f))) for f in real.fetchall()]
        else:
            self._filas = []
        return self

    def executemany(self, sql, secuencia):
        total = 0
        for parametros in secuencia:
            self.execute(sql, parametros)
            total += max(self.rowcount, 0)
        self.rowcount = total
        return self

    def fetchone(self):
        return self._filas[0] if self._filas else None

    def fetchall(self):
        return self._filas


class ConexionPostgresSimulada:
    """Conexion minima que produce cursores con filas tipo diccionario."""

    def __init__(self, ruta):
        self._real = sqlite3.connect(ruta, timeout=30)
        self._real.row_factory = sqlite3.Row

    def cursor(self, cursor_factory=None):
        return CursorPostgresSimulado(self._real)

    def execute(self, sql, parametros=None):
        return self._real.cursor().execute(sql, parametros or ())

    def executemany(self, sql, secuencia):
        return self._real.cursor().executemany(sql, secuencia)

    def commit(self):
        self._real.commit()

    def rollback(self):
        self._real.rollback()

    def close(self):
        self._real.close()


def activar(modulo_database, monkeypatch, ruta_db):
    """Pone el modulo ``database`` en modo PostgreSQL simulado.

    A partir de la llamada, ``get_cursor`` devuelve filas como diccionario, igual
    que en Render. ``monkeypatch`` restaura el estado original al terminar la
    prueba.
    """
    clase_psycopg2 = type("Psycopg2Simulado", (), {
        "extensions": type("Extensiones", (), {
            "connection": ConexionPostgresSimulada,
        }),
    })

    monkeypatch.setattr(modulo_database, "DATABASE_URL", "postgresql://simulado")
    monkeypatch.setattr(modulo_database, "psycopg2", clase_psycopg2)
    monkeypatch.setattr(
        modulo_database, "get_db_connection",
        lambda: ConexionPostgresSimulada(ruta_db),
    )
    return modulo_database
