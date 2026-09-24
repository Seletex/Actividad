# -*- coding: utf-8 -*-
"""
sync_db_to_postgres.py - Sube los datos de la base local (SQLite) a la base
PostgreSQL usada por Render en la web.

Uso:
    python sync_db_to_postgres.py --url "postgresql://usuario:clave@host:puerto/db"
    # o exporta previamente la variable y omite --url:
    set DATABASE_URL=postgresql://...        (Windows CMD)
    $env:DATABASE_URL="postgresql://..."      (Windows PowerShell)
    python sync_db_to_postgres.py

Opciones:
    --url URL     Connection string de PostgreSQL (Render). Si se omite usa DATABASE_URL del entorno.
    --modo MODE   merge (por defecto) | reemplazar | vacio
                  - merge: inserta/actualiza sin borrar lo existente en la web.
                  - reemplazar: limpia y vuelve a insertar (pide confirmacion).
                  - vacio: solo migra lo que no exista (no modifica existente).
    --tablas T    Solo migra esas tablas separadas por coma: usuarios,registros,...
    --local PATH  Ruta del SQLite local (por defecto usa la BD local configurada).
"""

import argparse
import os
import sqlite3
import sys
from datetime import datetime

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:
    print("ERROR: no está instalado psycopg2. Ejecuta: pip install psycopg2-binary")
    sys.exit(1)


def conectar_sqlite(ruta):
    conn = sqlite3.connect(ruta)
    conn.row_factory = sqlite3.Row
    return conn


def conectar_postgres(url):
    if not url:
        raise ValueError("No se proporcionó la URL de PostgreSQL (usa --url o DATABASE_URL).")
    return psycopg2.connect(url)


def leer_tabla(sqlite_conn, tabla, columnas):
    cols = ", ".join(columnas)
    cursor = sqlite_conn.execute(f"SELECT {cols} FROM {tabla}")
    filas = [dict(r) for r in cursor.fetchall()]
    return filas


def col_existe(pg_conn, tabla, col):
    cur = pg_conn.cursor()
    cur.execute(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name=%s AND column_name=%s",
        (tabla, col)
    )
    existe = cur.fetchone() is not None
    cur.close()
    return existe


# ---------------------------------------------------------------------------
# Tablas y sus columnas (orden = el mismo del esquema local)
# ---------------------------------------------------------------------------

MAPA_TABLAS = {
    "usuarios": {
        "columnas": ["username", "password_hash", "password_salt", "debe_cambiar_contrasena"],
        "claves": ["username"],
    },
    "actividades_personales": {
        "columnas": ["username", "actividad"],
        "claves": ["username", "actividad"],
    },
    "configuracion_usuario": {
        "columnas": ["username", "clave", "valor"],
        "claves": ["username", "clave"],
    },
    "listas_globales": {
        "columnas": ["tipo", "valor"],
        "claves": ["tipo", "valor"],
    },
    "registros": {
        "columnas": ["id", "usuario", "tipo_actividad", "fecha", "dependencia",
                     "solicitante", "tipo_solicitud", "medio_solicitud",
                     "descripcion", "cumplido", "fecha_atencion", "observaciones"],
        "claves": ["id"],
    },
    "bitacora": {
        "columnas": ["usuario", "accion", "detalle", "ip", "fecha"],
        "claves": [],  # sin clave natural; se inserta siempre
    },
}


def asegurar_columnas(pg_conn, tabla, columnas):
    """Agrega columnas que falten en Postgres (evita errores por esquemas distintos)."""
    for col in columnas:
        if col == "id":
            continue
        if col_existe(pg_conn, tabla, col):
            continue
        # Inferir tipo
        t = "TEXT"
        if col in ("debe_cambiar_contrasena",):
            t = "INTEGER"
        cur = pg_conn.cursor()
        try:
            cur.execute(f"ALTER TABLE {tabla} ADD COLUMN {col} {t}")
            pg_conn.commit()
            print(f"   + columna agregada en {tabla}: {col} ({t})")
        except Exception:
            pg_conn.rollback()
        finally:
            cur.close()


def migrar_tabla(pg_conn, sqlite_conn, tabla, spec, modo, tablas_seleccionadas):
    if tabla not in tablas_seleccionadas:
        return 0

    columnas = spec["columnas"]
    claves = spec["claves"]
    print(f"\n[migrando] tabla '{tabla}' ...")

    # Si no existe en Postgres, se crea al arrancar la app (inicializar_tablas).
    # Aquí si la tabla no existe, creamos una versión básica para poder insertar.
    cur = pg_conn.cursor()
    cur.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_name=%s",
        (tabla,)
    )
    existe_tabla = cur.fetchone() is not None
    cur.close()
    if not existe_tabla:
        print(f"   [aviso] La tabla '{tabla}' no existe en Postgres. Se creará una básica.")
        crear_tabla_basica(pg_conn, tabla, columnas)

    asegurar_columnas(pg_conn, tabla, columnas)

    filas = leer_tabla(sqlite_conn, tabla, columnas)
    print(f"   {len(filas)} fila(s) en local.")

    if not filas:
        return 0

    # Modo reemplazar: borrar datos de la tabla en destino
    if modo == "reemplazar":
        cur = pg_conn.cursor()
        cur.execute(f"TRUNCATE TABLE {tabla} RESTART IDENTITY CASCADE")
        pg_conn.commit()
        cur.close()
        print(f"   (modo reemplazar) datos previos de '{tabla}' borrados.")

    col_list = ", ".join(columnas)
    placeholders = ", ".join(["%s"] * len(columnas))

    if claves:
        # ON CONFLICT en Postgres
        conflicto = ", ".join(claves)
        actualizar = ", ".join(f"{c} = EXCLUDED.{c}" for c in columnas if c not in claves)
        if actualizar:
            plantilla = (f"INSERT INTO {tabla} ({col_list}) VALUES ({placeholders}) "
                         f"ON CONFLICT ({conflicto}) DO UPDATE SET {actualizar}")
        else:
            # No hay columnas fuera de la clave -> DO NOTHING
            plantilla = (f"INSERT INTO {tabla} ({col_list}) VALUES ({placeholders}) "
                         f"ON CONFLICT ({conflicto}) DO NOTHING")
    else:
        plantilla = f"INSERT INTO {tabla} ({col_list}) VALUES ({placeholders})"

    insertadas = 0
    cur = pg_conn.cursor()
    for fila in filas:
        valores = [fila.get(c) for c in columnas]
        try:
            if modo == "vacio" and claves:
                # Verificar si ya existe
                where = " AND ".join(f"{c} = %s" for c in claves)
                cur.execute(f"SELECT 1 FROM {tabla} WHERE {where}", [fila[c] for c in claves])
                if cur.fetchone():
                    continue
            cur.execute(plantilla, valores)
            insertadas += 1
        except Exception as e:
            pg_conn.rollback()
            print(f"   [error] fila {insertadas + 1} ({fila.get('id') or fila.get('username')}): {e}")
        else:
            # commit parcial para no perder el progreso si algo falla
            if (insertadas % 500) == 0:
                pg_conn.commit()

    cur.close()
    pg_conn.commit()
    print(f"   [+] {insertadas} fila(s) procesadas en '{tabla}'.")
    return insertadas


def crear_tabla_basica(pg_conn, tabla, columnas):
    """Crea la tabla en Postgres con las columnas dadas (mínimo para migrar)."""
    definiciones = []
    for c in columnas:
        if c == "id":
            definiciones.append("id SERIAL PRIMARY KEY")
        elif c == "debe_cambiar_contrasena":
            definiciones.append("debe_cambiar_contrasena INTEGER DEFAULT 0")
        elif c == "fecha":
            definiciones.append("fecha TIMESTAMP")
        elif c == "username":
            definiciones.append("username TEXT PRIMARY KEY")
        else:
            definiciones.append(f"{c} TEXT")
    ddl = f"CREATE TABLE IF NOT EXISTS {tabla} ({', '.join(definiciones)})"
    cur = pg_conn.cursor()
    cur.execute(ddl)
    pg_conn.commit()
    cur.close()


def principal():
    parser = argparse.ArgumentParser(description="Sube datos de SQLite local a PostgreSQL (Render).")
    parser.add_argument("--url", help="Connection string de PostgreSQL. Si se omite usa DATABASE_URL.")
    parser.add_argument("--modo", default="merge", choices=["merge", "reemplazar", "vacio"])
    parser.add_argument("--tablas", help="Solo estas tablas (coma): usuarios,registros,...")
    parser.add_argument("--local", help="Ruta del SQLite local (por defecto la BD configurada).")
    args = parser.parse_args()

    # Ruta del SQLite local
    ruta_local = args.local
    sistema_archivo_db = os.path.join(os.path.dirname(os.path.abspath(__file__)), "actividades.db")
    if not ruta_local:
        try:
            from config import DB_FILE
            ruta_local = DB_FILE
        except Exception:
            ruta_local = sistema_archivo_db

    if not os.path.exists(ruta_local):
        print(f"ERROR: no se encontró la BD local en: {ruta_local}")
        sys.exit(1)

    # URL de Postgres
    url = args.url or os.environ.get("DATABASE_URL")
    if not url:
        print("ERROR: falta la URL de PostgreSQL.")
        print("   Uso: python sync_db_to_postgres.py --url \"postgresql://usuario:clave@host/db\"")
        print("   o exporta la variable DATABASE_URL antes.")
        sys.exit(1)

    tablas_seleccionadas = set(args.tablas.split(",")) if args.tablas else set(MAPA_TABLAS.keys())
    tablas_seleccionadas = {t.strip() for t in tablas_seleccionadas}

    if args.modo == "reemplazar":
        resp = input(f"[aviso] Modo 'reemplazar' borrará los datos de la web. ¿Continuar? (s/N): ").strip().lower()
        if resp != "s":
            print("Cancelado.")
            sys.exit(0)

    print("=" * 60)
    print("  SINCRONIZACION DE DATOS -> PostgreSQL (Render)")
    print("=" * 60)
    print(f"  Local SQLite : {ruta_local}")
    print(f"  Modo         : {args.modo}")
    print(f"  Tablas       : {', '.join(sorted(tablas_seleccionadas))}")
    print("=" * 60)

    sqlite_conn = conectar_sqlite(ruta_local)
    pg = conectar_postgres(url)
    pg.autocommit = False

    total = 0
    try:
        for tabla, spec in MAPA_TABLAS.items():
            if tabla in tablas_seleccionadas:
                total += migrar_tabla(pg, sqlite_conn, tabla, spec, args.modo, tablas_seleccionadas)
    finally:
        try:
            sqlite_conn.close()
        except Exception:
            pass
        try:
            pg.close()
        except Exception:
            pass

    print("\n" + "=" * 60)
    print(f"  Sincronización completada. Filas procesadas: {total}")
    print("=" * 60)
    print("Recuerda: al desplegar, la app en Render creará/usará las mismas")
    print("tablas. Revisa en la web que los datos (usuarios, registros, etc.)")
    print("aparezcan correctamente.")


if __name__ == "__main__":
    principal()
