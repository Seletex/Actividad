# -*- coding: utf-8 -*-
"""Importa a PostgreSQL las actividades que quedaron solo en bases SQLite.

Para que sirve
--------------
Cuando la aplicacion trabajaba sin conexion (o el servidor estaba caido), cada
equipo guardo sus actividades en su propio ``actividades.db``. Este script
compara esas bases con PostgreSQL y sube **solo lo que falta**, sin repetir lo
que ya esta.

Como se decide que falta
------------------------
Se comparan los datos de la actividad (usuario, fecha de atencion, tipo,
dependencia, solicitante, tipo y medio de solicitud, descripcion, cumplido y
observaciones) ignorando mayusculas, tildes y espacios de mas. La comparacion
respeta la cantidad: si el equipo tiene dos registros iguales y la nube uno,
se sube uno.

Uso
---
Ensayar (no escribe nada):

    python importar_faltantes.py --carpeta "C:\\Escaner"

Aplicar los cambios (antes crea un respaldo con pg_dump):

    python importar_faltantes.py --carpeta "C:\\Escaner" --aplicar

Excluir un registro concreto que se sabe que ya esta subido con otro texto:

    python importar_faltantes.py --carpeta "C:\\Escaner" --aplicar ^
        --excluir "Freddy:3950"

La URL se toma de ``--url`` o de la variable de entorno ``DATABASE_URL``.
"""

import argparse
import os
import shutil
import sqlite3
import subprocess
import sys
import unicodedata
import uuid
from collections import Counter
from datetime import datetime
from pathlib import Path

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:
    print("ERROR: falta psycopg2. Ejecute: pip install psycopg2-binary")
    sys.exit(1)


# Carpetas conocidas de C:\Escaner. Se pueden cambiar con --usuario.
USUARIOS_POR_CARPETA = {
    "Manolo": "Manolo",
    "Juan": "JuanB",
    "Freddy": "Freddy",
}

COLUMNAS = [
    "tipo_actividad", "dependencia", "solicitante", "tipo_solicitud",
    "medio_solicitud", "descripcion", "cumplido", "fecha_atencion",
    "observaciones",
]

# Columnas que se copian tal cual a PostgreSQL.
CAMPOS_INSERCION = [
    "usuario", "tipo_actividad", "fecha", "dependencia", "solicitante",
    "tipo_solicitud", "medio_solicitud", "descripcion", "cumplido",
    "fecha_atencion", "observaciones",
]


def texto(valor):
    if valor is None:
        return ""
    if hasattr(valor, "strftime"):
        return valor.strftime("%Y-%m-%d %H:%M:%S")
    return str(valor)


def normalizar(valor):
    """Minusculas, sin tildes y con los espacios colapsados."""
    limpio = " ".join(texto(valor).replace("\r\n", "\n").replace("\r", "\n").split())
    limpio = limpio.casefold()
    limpio = unicodedata.normalize("NFKD", limpio)
    return "".join(c for c in limpio if not unicodedata.combining(c))


def dia(valor):
    return texto(valor)[:10]


def clave(fila):
    """Identidad logica de una actividad, para comparar dos bases."""
    return tuple(
        [normalizar(fila.get("usuario")), dia(fila.get("fecha"))]
        + [normalizar(fila.get(c)) for c in COLUMNAS]
    )


def faltantes(locales, remotos, excluir=()):
    """Devuelve las filas locales que no estan en remotos.

    ``excluir`` son ids locales que no se deben subir aunque falten (por
    ejemplo, porque ya se subieron con otro texto).
    """
    cupo = Counter(clave(f) for f in remotos)
    usados = Counter()
    resultado = []
    for fila in locales:
        if fila.get("id") in excluir:
            continue
        k = clave(fila)
        usados[k] += 1
        if usados[k] > cupo.get(k, 0):
            resultado.append(fila)
    return resultado


def leer_sqlite(ruta, usuario):
    """Lee las actividades de un usuario. Abre la base en solo lectura."""
    uri = "file:" + Path(ruta).as_posix() + "?mode=ro"
    conexion = sqlite3.connect(uri, uri=True)
    conexion.row_factory = sqlite3.Row
    try:
        cursor = conexion.cursor()
        cursor.execute(
            "SELECT * FROM registros WHERE usuario = ? ORDER BY id", (usuario,)
        )
        return [dict(fila) for fila in cursor.fetchall()]
    finally:
        conexion.close()


def leer_neon(url):
    conexion = psycopg2.connect(url, connect_timeout=60)
    try:
        cursor = conexion.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT * FROM registros WHERE COALESCE(borrado, 0) = 0")
        return [dict(fila) for fila in cursor.fetchall()]
    finally:
        conexion.close()


def fecha_para_insertar(fila):
    valor = texto(fila.get("fecha")).strip()
    if len(valor) >= 19 and valor[4] == "-" and valor[7] == "-":
        return valor[:19]
    referencia = dia(fila.get("fecha_atencion")) or dia(valor)
    if len(referencia) == 10:
        return referencia + " 00:00:00"
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def buscar_pg_dump():
    ruta = shutil.which("pg_dump")
    if ruta:
        return ruta
    import glob
    candidatos = sorted(
        glob.glob(r"C:\Program Files\PostgreSQL\*\bin\pg_dump.exe"), reverse=True
    )
    return candidatos[0] if candidatos else None


def respaldar_antes(url, destino):
    """Genera un volcado completo antes de escribir. Devuelve la ruta."""
    pg_dump = buscar_pg_dump()
    if not pg_dump:
        raise SystemExit(
            "ERROR: no se encontro pg_dump. Instale las herramientas de "
            "PostgreSQL o pase --sin-respaldo (no recomendado)."
        )
    os.makedirs(destino, exist_ok=True)
    nombre = f"antes_importacion_{datetime.now():%Y%m%d_%H%M%S}.sql"
    ruta = os.path.join(destino, nombre)
    resultado = subprocess.run(
        [pg_dump, "--no-owner", "--no-privileges", "--clean", "--if-exists",
         "--file", ruta, url],
        capture_output=True,
    )
    if resultado.returncode != 0:
        detalle = resultado.stderr.decode("utf-8", "replace").strip()
        raise SystemExit(f"ERROR: pg_dump fallo: {detalle[:500]}")
    return ruta


def insertar(url, filas):
    """Inserta las filas en una sola transaccion. Devuelve (carpeta, id_viejo, id_nuevo)."""
    insertados = []
    conexion = psycopg2.connect(url, connect_timeout=60)
    try:
        cursor = conexion.cursor()
        ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for fila in filas:
            valores = [fila.get(c) for c in CAMPOS_INSERCION]
            valores[2] = fecha_para_insertar(fila)
            valores = valores + [uuid.uuid4().hex, ahora, 0]
            cursor.execute(
                "INSERT INTO registros ("
                + ", ".join(CAMPOS_INSERCION)
                + ", sync_uid, updated_at, borrado) VALUES ("
                + ", ".join(["%s"] * (len(CAMPOS_INSERCION) + 3))
                + ") RETURNING id",
                tuple(valores),
            )
            insertados.append(
                (fila.get("_carpeta"), fila.get("id"), cursor.fetchone()[0])
            )
        conexion.commit()
    except Exception:
        conexion.rollback()
        raise
    finally:
        conexion.close()
    return insertados


def carpetas_a_procesar(raiz, mapa):
    """Devuelve [(ruta_db, carpeta, usuario)] de las carpetas configuradas."""
    resultado = []
    for carpeta, usuario in mapa.items():
        ruta = Path(raiz) / carpeta / "actividades.db"
        if ruta.exists():
            resultado.append((ruta, carpeta, usuario))
    return resultado


def main():
    analizador = argparse.ArgumentParser(
        description="Sube a PostgreSQL las actividades que solo estan en SQLite."
    )
    analizador.add_argument("--carpeta", required=True,
                            help="Carpeta que contiene las subcarpetas de cada equipo.")
    analizador.add_argument("--url", default=os.environ.get("DATABASE_URL", ""),
                            help="URL de PostgreSQL (o variable DATABASE_URL).")
    analizador.add_argument("--aplicar", action="store_true",
                            help="Escribe en la base. Sin esta opcion solo informa.")
    analizador.add_argument("--excluir", action="append", default=[],
                            metavar="CARPETA:ID",
                            help="No subir ese id local (se puede repetir).")
    analizador.add_argument("--usuario", action="append", default=[],
                            metavar="CARPETA=USUARIO",
                            help="Cambia la correspondencia carpeta -> usuario.")
    analizador.add_argument("--destino-respaldo",
                            default=os.path.join(
                                os.environ.get("USERPROFILE", os.path.expanduser("~")),
                                "Documents", "Documentos", "Respaldo"),
                            help="Carpeta donde guardar el respaldo previo.")
    analizador.add_argument("--sin-respaldo", action="store_true",
                            help="No crear respaldo antes de escribir (no recomendado).")
    argumentos = analizador.parse_args()

    if not argumentos.url:
        print("ERROR: falta --url (o la variable de entorno DATABASE_URL).")
        return 2

    mapa = dict(USUARIOS_POR_CARPETA)
    for cambio in argumentos.usuario:
        if "=" not in cambio:
            print(f"ERROR: --usuario espera CARPETA=USUARIO, no {cambio!r}")
            return 2
        carpeta, usuario = cambio.split("=", 1)
        mapa[carpeta.strip()] = usuario.strip()

    excluir = {}
    for item in argumentos.excluir:
        if ":" not in item:
            print(f"ERROR: --excluir espera CARPETA:ID, no {item!r}")
            return 2
        carpeta, identificador = item.split(":", 1)
        excluir.setdefault(carpeta.strip(), set()).add(int(identificador))

    remotos = leer_neon(argumentos.url)
    print(f"Registros vivos en PostgreSQL: {len(remotos)}")
    print()

    pendientes = []
    for ruta, carpeta, usuario in carpetas_a_procesar(argumentos.carpeta, mapa):
        locales = leer_sqlite(ruta, usuario)
        del_usuario = [f for f in remotos if f.get("usuario") == usuario]
        candidatos = faltantes(locales, del_usuario, excluir.get(carpeta, set()))
        print(f"{carpeta} ({usuario}): {len(locales)} en el equipo, "
              f"{len(del_usuario)} en PostgreSQL, faltan {len(candidatos)}")
        for fila in candidatos:
            fila["_carpeta"] = carpeta
            pendientes.append(fila)
            print(f"   id={fila.get('id')}  {dia(fila.get('fecha_atencion'))}  "
                  f"{texto(fila.get('solicitante'))[:25]:25s}  "
                  f"{texto(fila.get('descripcion'))[:70]}")
        print()

    if not pendientes:
        print("No hay nada que subir: todo esta en PostgreSQL.")
        return 0

    print(f"Total a subir: {len(pendientes)}")
    if not argumentos.aplicar:
        print("ENSAYO: no se escribio nada. Use --aplicar para subirlos.")
        return 0

    if not argumentos.sin_respaldo:
        ruta_respaldo = respaldar_antes(argumentos.url, argumentos.destino_respaldo)
        print(f"Respaldo previo: {ruta_respaldo}")

    insertados = insertar(argumentos.url, pendientes)
    print(f"Insertados: {len(insertados)}")
    for carpeta, id_viejo, id_nuevo in insertados:
        print(f"   {carpeta}: id local {id_viejo} -> id nuevo {id_nuevo}")

    # Comprobacion final: ya no debe faltar nada.
    remotos = leer_neon(argumentos.url)
    quedan = 0
    for ruta, carpeta, usuario in carpetas_a_procesar(argumentos.carpeta, mapa):
        locales = leer_sqlite(ruta, usuario)
        del_usuario = [f for f in remotos if f.get("usuario") == usuario]
        restantes = faltantes(locales, del_usuario, excluir.get(carpeta, set()))
        quedan += len(restantes)
    print()
    if quedan:
        print(f"ATENCION: todavia faltan {quedan} registros. Revise el informe.")
        return 1
    print("Comprobado: ya no falta ningun registro de las carpetas revisadas.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
