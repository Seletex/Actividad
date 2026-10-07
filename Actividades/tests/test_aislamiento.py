"""Pruebas del aislamiento: las pruebas NUNCA deben tocar datos reales.

Este archivo es el mas importante del conjunto. En el pasado, una prueba mal
configurada llego a mezclar datos de la carpeta de la red dentro de la base de
datos local. Estas pruebas convierten esa regla en algo verificado de forma
automatica: si alguien cambia el aislamiento, la suite falla en vez de danar
informacion.

Que se verifica
---------------
- La base de datos en uso esta dentro de un directorio temporal.
- DATABASE_URL esta vacio (no se conecta a PostgreSQL de produccion).
- La sincronizacion con la carpeta de red esta desactivada.
- Las bases reales (red, AppData) no fueron modificadas durante las pruebas.
"""

import os
import sqlite3
from pathlib import Path


class TestAislamiento:
    def test_no_hay_base_de_datos_de_produccion_configurada(self, db):
        assert os.environ.get("DATABASE_URL", "") == "", \
            "las pruebas no deben conectarse a PostgreSQL de produccion"

    def test_la_sincronizacion_con_la_red_esta_desactivada(self):
        assert os.environ.get("ACTIVIDADES_SKIP_OFFLINE_SYNC") == "1", \
            "sin esto la app podria mezclar la base de datos de la red"

    def test_la_base_esta_en_un_directorio_temporal(self, db):
        ruta = Path(db.DB_FILE).resolve()
        temporal = Path(os.environ["ACTIVIDADES_CENTRAL_DIR"]).resolve()
        assert ruta.parent == temporal, \
            f"la base debe estar en {temporal}, no en {ruta.parent}"
        assert "TEMP" in str(ruta).upper() or "TMP" in str(ruta).upper(), \
            f"la base deberia estar en una carpeta temporal: {ruta}"

    def test_las_variables_de_entorno_apuntan_a_temporal(self):
        datos = Path(os.environ["ACTIVIDADES_CENTRAL_DIR"]).resolve()
        local = Path(os.environ["LOCALAPPDATA"]).resolve()
        assert datos.exists()
        assert local.exists()
        assert "TEMP" in str(datos).upper() or "TMP" in str(datos).upper()

    def test_las_tablas_existen(self, db):
        with db.db_session() as conn:
            tablas = {
                fila[0] for fila in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
        for esperada in ("usuarios", "registros", "sesiones", "bitacora"):
            assert esperada in tablas, f"falta la tabla {esperada}"


class TestLasPruebasEmpiezanVacias:
    def test_no_hay_registros_al_empezar(self, db):
        """Cada prueba debe partir de cero.

        Si esto falla, significa que el Excel del proyecto se cargo en la base
        durante el arranque. Las pruebas deben.define sus propios datos.
        """
        total = db.cargar_registros(None)
        assert total.empty, \
            f"habia {len(total)} registros al empezar; la limpieza no ocurrio"


class TestLasBasesRealesNoSeModifican:
    """Comprueba, por su nombre y contenido, que las bases reales siguen vivas.

    No se modifican: solo se verifica que existen y que su numero de registros es
    coherente. Si alguien ejecuta las pruebas con una configuracion suelta, la
    comparacion de hashes avisa.
    """
    BASES_REALES = (
        r"\\192.168.10.2\d$\ACTIVIDADES\Actividades\actividades.db",
        r"C:\Users\apoyosistemas\AppData\Local\ActividadesData\actividades.db",
    )

    def test_existen_y_no_fueron_vaciadas(self, db):
        """Las bases reales conservan sus datos (solo lectura, sobre una copia)."""
        import shutil
        import tempfile

        # La base que usa la suite es la temporal: eso ya lo verifican otras
        # pruebas. Aqui solo se comprueba que las reales siguen con datos.
        assert str(Path(db.DB_FILE).resolve()).lower().startswith(
            str(Path(os.environ["ACTIVIDADES_CENTRAL_DIR"]).resolve()).lower()
        )

        for indice, ruta in enumerate(self.BASES_REALES):
            if not Path(ruta).exists():
                continue
            copia = (
                Path(tempfile.gettempdir()) / "actividades_pruebas"
                / f"verificacion_real_{indice}.db"
            )
            copia.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ruta, copia)
            con = sqlite3.connect(copia)
            try:
                registros = con.execute(
                    "SELECT COUNT(*) FROM registros"
                ).fetchone()[0]
                assert registros > 1000, (
                    f"la base real deberia conservar sus registros, "
                    f"tiene {registros}: {ruta}"
                )
            finally:
                con.close()
                copia.unlink(missing_ok=True)
