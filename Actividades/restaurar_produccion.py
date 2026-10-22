"""
restaurar_produccion.py - Restaura una base PostgreSQL a partir de una copia local.

Se creó para recuperar la aplicación después de que Render eliminara la base de
datos PostgreSQL gratuita (esas bases expiran a los 30 dias y Render no guarda
ninguna copia de las bases que elimina).

El script es autónomo: no importa la aplicación, por lo que no puede tocar las
bases reales del equipo ni disparar sincronizaciones. Solo escribe en la
PostgreSQL que se le indique.

Ejemplo (desde el equipo, con la URL externa de la base nueva de Render):

    python restaurar_produccion.py ^
        --url "postgresql://usuario:clave@ep-xxxx-yyy.us-west-2.aws.neon.tech/neondb?sslmode=require" ^
        --local "%LOCALAPPDATA%\\ActividadesData\\actividades.db" ^
        --contrasena-admin "UnaClaveFuerte"

Que hace:
  1. Crea las tablas que falten en PostgreSQL.
  2. Copia usuarios, actividades personales, configuracion, listas globales y
     registros desde el archivo SQLite local.
  3. Opcionalmente asigna la contraseña del administrador.
  4. Verifica y muestra el resultado de cada tabla.

Las contraseñas de los demas usuarios NO se restauran (en la copia local no
existen hashes). Hay que asignarlas desde la web: Gestion > Usuarios del Sistema.
"""

import argparse
import hashlib
import json
import os
import secrets
import sqlite3
import sys
from datetime import datetime

try:
    import psycopg2
    from psycopg2.extras import execute_values
except ImportError:
    print("ERROR: falta psycopg2. Ejecute: pip install psycopg2-binary")
    sys.exit(1)


PBKDF2_ITER = 260_000

# Tablas que se restauran, en el orden correcto (respetando dependencias).
TABLAS = [
    "usuarios",
    "actividades_personales",
    "configuracion_usuario",
    "listas_globales",
    "registros",
]

ESQUEMA = [
    """
    CREATE TABLE IF NOT EXISTS usuarios (
        username TEXT PRIMARY KEY,
        password_hash TEXT,
        password_salt TEXT,
        debe_cambiar_contrasena INTEGER DEFAULT 0,
        revision_sesion INTEGER DEFAULT 0
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS actividades_personales (
        username TEXT, actividad TEXT, UNIQUE(username, actividad)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS configuracion_usuario (
        username TEXT, clave TEXT, valor TEXT, PRIMARY KEY (username, clave)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS listas_globales (
        tipo TEXT, valor TEXT, UNIQUE(tipo, valor)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS registros (
        id SERIAL PRIMARY KEY,
        usuario TEXT, tipo_actividad TEXT, fecha TIMESTAMP, dependencia TEXT,
        solicitante TEXT, tipo_solicitud TEXT, medio_solicitud TEXT,
        descripcion TEXT, cumplido TEXT, fecha_atencion TEXT, observaciones TEXT,
        sync_uid TEXT, updated_at TEXT, borrado INTEGER DEFAULT 0
    )
    """,
]

# Columnas que se copian de cada tabla (las que existen en SQLite y en PG).
COLUMNAS = {
    "usuarios": ["username", "password_hash", "password_salt", "debe_cambiar_contrasena"],
    "actividades_personales": ["username", "actividad"],
    "configuracion_usuario": ["username", "clave", "valor"],
    "listas_globales": ["tipo", "valor"],
    "registros": [
        "id", "usuario", "tipo_actividad", "fecha", "dependencia",
        "solicitante", "tipo_solicitud", "medio_solicitud", "descripcion",
        "cumplido", "fecha_atencion", "observaciones",
        "sync_uid", "updated_at", "borrado",
    ],
}


def hashear_contrasena(contrasena, salt=None):
    """Replica el algoritmo de database.py (PBKDF2-SHA256)."""
    if salt is None:
        salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", contrasena.encode("utf-8"), bytes.fromhex(salt), PBKDF2_ITER
    ).hex()
    return digest, salt


def columnas_existentes(cursor, tabla):
    cursor.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name = %s",
        (tabla,),
    )
    return {fila[0] for fila in cursor.fetchall()}


def leer_sqlite(ruta, tabla, columnas):
    """Lee las filas de una tabla del SQLite local, ignorando columnas ausentes."""
    conexion = sqlite3.connect(ruta)
    conexion.row_factory = sqlite3.Row
    try:
        existentes = {
            fila["name"] for fila in conexion.execute(f'PRAGMA table_info("{tabla}")')
        }
        if not existentes:
            return []
        elegidas = [c for c in columnas if c in existentes]
        if not elegidas:
            return []
        consulta = f'SELECT {", ".join(elegidas)} FROM "{tabla}"'
        return [dict(fila) for fila in conexion.execute(consulta)]
    finally:
        conexion.close()


def main():
    analizador = argparse.ArgumentParser(
        description="Restaura una base PostgreSQL desde una copia local en SQLite."
    )
    analizador.add_argument(
        "--url",
        default=os.environ.get("DATABASE_URL", ""),
        help="URL de conexión a PostgreSQL (o variable de entorno DATABASE_URL).",
    )
    analizador.add_argument(
        "--local",
        default=os.path.join(
            os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
            "ActividadesData",
            "actividades.db",
        ),
        help="Ruta del archivo SQLite de origen.",
    )
    analizador.add_argument(
        "--modo",
        choices=["reemplazar", "combinar"],
        default="reemplazar",
        help="'reemplazar' vacia las tablas antes de copiar (recomendado para una "
             "base nueva). 'combinar' agrega lo que falte sin borrar nada.",
    )
    analizador.add_argument(
        "--contrasena-admin",
        default="",
        help="Si se indica, asigna esta contraseña al usuario admin.",
    )
    analizador.add_argument(
        "--forzar-cambio-admin",
        action="store_true",
        help="Obliga al administrador a cambiar la contraseña en su próximo ingreso.",
    )
    argumentos = analizador.parse_args()

    if not argumentos.url:
        print("ERROR: falta --url (o la variable de entorno DATABASE_URL).")
        return 2
    if not os.path.exists(argumentos.local):
        print(f"ERROR: no existe el archivo local {argumentos.local}")
        return 2

    print(f"Origen (SQLite) : {argumentos.local}")
    print(f"Destino (PG)     : {argumentos.url.split('@')[-1]}")
    print(f"Modo             : {argumentos.modo}")
    print("-" * 62)

    conexion = psycopg2.connect(argumentos.url)
    conexion.autocommit = False
    cursor = conexion.cursor()

    # Claves naturales de cada tabla, para poder combinarla sin duplicar.
    CONFLICTOS = {
        "usuarios": ("username", "DO NOTHING"),
        "actividades_personales": ("username, actividad", "DO NOTHING"),
        "configuracion_usuario": ("username, clave", "DO UPDATE SET valor = EXCLUDED.valor"),
        "listas_globales": ("tipo, valor", "DO NOTHING"),
        "registros": ("id", "DO NOTHING"),
    }

    try:
        for sentencia in ESQUEMA:
            cursor.execute(sentencia)

        resumen = {}
        for tabla in TABLAS:
            filas = leer_sqlite(argumentos.local, tabla, COLUMNAS[tabla])
            if not filas:
                resumen[tabla] = 0
                print(f"  {tabla:26s} sin datos en el origen")
                continue

            existentes = columnas_existentes(cursor, tabla)
            elegidas = [c for c in COLUMNAS[tabla] if c in existentes]
            if not elegidas:
                print(f"  {tabla:26s} OMITIDA (no existe en PostgreSQL)")
                continue

            if argumentos.modo == "reemplazar":
                cursor.execute(f'TRUNCATE TABLE "{tabla}" RESTART IDENTITY CASCADE')

            valores = []
            for fila in filas:
                valores.append(
                    tuple(
                        fila.get(columna) if fila.get(columna) is not None else ""
                        for columna in elegidas
                    )
                )
            if valores:
                clave, accion = CONFLICTOS.get(tabla, ("", "DO NOTHING"))
                if clave:
                    sentencia = (
                        f'INSERT INTO "{tabla}" ({", ".join(elegidas)}) VALUES %s '
                        f"ON CONFLICT ({clave}) {accion}"
                    )
                else:
                    sentencia = (
                        f'INSERT INTO "{tabla}" ({", ".join(elegidas)}) VALUES %s'
                    )
                execute_values(cursor, sentencia, valores)
            resumen[tabla] = len(valores)
            print(f"  {tabla:26s} {len(valores):>6d} fila(s) copiada(s)")

        # La secuencia de ids de "registros" debe quedar por delante del maximo.
        cursor.execute("SELECT MAX(id) FROM registros")
        maximo = cursor.fetchone()[0]
        if maximo:
            cursor.execute(
                "SELECT setval(pg_get_serial_sequence('registros', 'id'), %s, true)",
                (maximo,),
            )

        # El administrador siempre debe existir.
        cursor.execute(
            "INSERT INTO usuarios (username) VALUES (%s) ON CONFLICT DO NOTHING",
            ("admin",),
        )

        if argumentos.contrasena_admin:
            if len(argumentos.contrasena_admin) < 10:
                print("ERROR: la contraseña del administrador debe tener al menos 10 caracteres.")
                conexion.rollback()
                return 2
            hash_guardado, salt = hashear_contrasena(argumentos.contrasena_admin)
            cursor.execute(
                "UPDATE usuarios SET password_hash = %s, password_salt = %s, "
                "debe_cambiar_contrasena = %s WHERE username = %s",
                (
                    hash_guardado,
                    salt,
                    1 if argumentos.forzar_cambio_admin else 0,
                    "admin",
                ),
            )
            print("  contrasena de admin        asignada")

        conexion.commit()

        print("-" * 62)
        print("Verificacion en PostgreSQL:")
        for tabla in TABLAS:
            cursor.execute(f'SELECT COUNT(*) FROM "{tabla}"')
            total = cursor.fetchone()[0]
            esperado = resumen.get(tabla, 0)
            marca = "OK " if total >= esperado else "!! "
            print(f"  {marca}{tabla:26s} {total:>6d} (origen: {esperado})")

        cursor.execute("SELECT COUNT(*) FROM usuarios WHERE password_hash IS NOT NULL "
                       "AND password_hash <> ''")
        con_clave = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM usuarios")
        total_usuarios = cursor.fetchone()[0]
        print(f"  usuarios con contrasena: {con_clave} de {total_usuarios}")
        if con_clave < total_usuarios:
            print("  Recordatorio: asigne las contrasenas desde la web, en")
            print("  Gestion > Usuarios del Sistema (deje 'forzar cambio' marcado).")
    except Exception as exc:
        conexion.rollback()
        print(f"ERROR durante la restauracion: {exc}")
        return 1
    finally:
        cursor.close()
        conexion.close()

    print("-" * 62)
    print("Restauracion completada. " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
