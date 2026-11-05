"""Repara actividades que quedaron cortadas en 200 caracteres.

Por que existe
-------------
La version web guardaba ``TIPO DE ACTIVIDAD`` con un limite de 200 caracteres,
mientras que las actividades asignadas miden hasta 318. Por eso algunas filas
de la misma actividad quedaron completas (importadas o creadas antes) y otras
quedaron cortadas a la mitad.

Este script busca las filas cuyo texto mide exactamente 200 caracteres, las
compara con las actividades completas conocidas (actividades personales,
registros ya completos y ``usuarios.json``) y restaura el texto original.

Uso
---
Primero, sin cambiar nada (muestra lo que haria)::

    python reparar_actividades_recortadas.py --url "postgresql://..."

Luego, para aplicar los cambios (pida el respaldo antes)::

    python reparar_actividades_recortadas.py --url "postgresql://..." --aplicar

Solo restaura cuando la coincidencia es unica. Si un texto cortado puede
corresponder a dos actividades distintas, lo deja igual y lo informa.
"""

import argparse
import json
import os
import sys
from datetime import datetime

try:
    import psycopg2
except ImportError:
    print("ERROR: falta psycopg2. Ejecute: pip install psycopg2-binary")
    sys.exit(1)

LIMITE = 200
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USUARIOS_JSON = os.path.join(BASE_DIR, "usuarios.json")


def _texto(valor):
    return "" if valor is None else str(valor)


def _recorrer_actividades(nodo, salida):
    """Agrega a ``salida`` todos los textos largos del archivo de usuarios."""
    if isinstance(nodo, dict):
        for valor in nodo.values():
            _recorrer_actividades(valor, salida)
    elif isinstance(nodo, list):
        for item in nodo:
            _recorrer_actividades(item, salida)
    elif isinstance(nodo, str):
        salida.add(nodo)


def cargar_completas(cursor):
    """Textos completos conocidos (con mas de 200 caracteres)."""
    completas = set()

    cursor.execute("SELECT actividad FROM actividades_personales")
    for (actividad,) in cursor.fetchall():
        texto = _texto(actividad)
        if len(texto) > LIMITE:
            completas.add(texto)

    cursor.execute(
        "SELECT DISTINCT tipo_actividad FROM registros "
        "WHERE length(tipo_actividad) > %s",
        (LIMITE,),
    )
    for (actividad,) in cursor.fetchall():
        texto = _texto(actividad)
        if len(texto) > LIMITE:
            completas.add(texto)

    if os.path.exists(USUARIOS_JSON):
        try:
            with open(USUARIOS_JSON, encoding="utf-8") as archivo:
                _recorrer_actividades(json.load(archivo), completas)
        except (OSError, ValueError) as error:
            print(f"AVISO: no se pudo leer {USUARIOS_JSON}: {error}")

    return {texto for texto in completas if len(texto) > LIMITE}


def buscar_completa(cortado, completas):
    """Devuelve el texto completo unico que empieza con ``cortado``."""
    candidatos = [texto for texto in completas if texto.startswith(cortado)]
    if not candidatos:
        base = cortado.rstrip()
        candidatos = [texto for texto in completas if texto.startswith(base)]
    candidatos = sorted(set(candidatos))
    if len(candidatos) == 1:
        return candidatos[0], []
    return None, candidatos


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--url",
        default=os.environ.get("DATABASE_URL", ""),
        help="URL de PostgreSQL (por defecto toma DATABASE_URL)",
    )
    parser.add_argument(
        "--aplicar",
        action="store_true",
        help="Guarda los cambios; sin esta opcion solo muestra el informe",
    )
    parser.add_argument(
        "--reporte",
        default=os.path.join(BASE_DIR, "reparacion_actividades.json"),
        help="Archivo donde se guarda el detalle de la revision",
    )
    args = parser.parse_args()

    if not args.url:
        print("ERROR: indique --url o defina DATABASE_URL")
        return 1

    conexion = psycopg2.connect(args.url, connect_timeout=60)
    conexion.autocommit = False
    cursor = conexion.cursor()

    completas = cargar_completas(cursor)
    print(f"Actividades completas conocidas: {len(completas)}")

    cursor.execute(
        "SELECT id, usuario, fecha, solicitante, tipo_actividad "
        "FROM registros WHERE length(tipo_actividad) = %s "
        "AND COALESCE(borrado, 0) = 0 ORDER BY id",
        (LIMITE,),
    )
    filas = cursor.fetchall()
    print(f"Registros con la actividad cortada a {LIMITE}: {len(filas)}")

    cambios = []
    sin_coincidencia = []
    ambiguas = []

    for identificador, usuario, fecha, solicitante, actual in filas:
        actual = _texto(actual)
        completa, opciones = buscar_completa(actual, completas)
        if completa:
            cambios.append(
                {
                    "id": identificador,
                    "usuario": usuario,
                    "fecha": str(fecha),
                    "solicitante": solicitante,
                    "antes": actual,
                    "despues": completa,
                }
            )
        elif opciones:
            ambiguas.append(
                {
                    "id": identificador,
                    "usuario": usuario,
                    "fecha": str(fecha),
                    "candidatas": opciones,
                }
            )
            print(
                f"  AMBIGUA id {identificador} ({usuario}): "
                f"{len(opciones)} actividades posibles"
            )
        else:
            sin_coincidencia.append(
                {
                    "id": identificador,
                    "usuario": usuario,
                    "fecha": str(fecha),
                    "texto": actual,
                }
            )
            print(f"  SIN COINCIDENCIA id {identificador} ({usuario})")

    print(f"Se pueden restaurar: {len(cambios)}")
    print(f"Ambiguas: {len(ambiguas)}")
    print(f"Sin coincidencia: {len(sin_coincidencia)}")

    if cambios:
        print("\nEjemplos:")
        for cambio in cambios[:5]:
            print(
                f"  id {cambio['id']} ({cambio['usuario']}): "
                f"{cambio['antes'][-35:]!r} -> {cambio['despues'][-35:]!r}"
            )

    if args.aplicar and cambios:
        momento = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for cambio in cambios:
            cursor.execute(
                "UPDATE registros SET tipo_actividad = %s, updated_at = %s "
                "WHERE id = %s",
                (cambio["despues"], momento, cambio["id"]),
            )
        cursor.execute(
            "INSERT INTO bitacora (usuario, accion, detalle, ip, fecha) "
            "VALUES (%s, %s, %s, %s, %s)",
            (
                "admin",
                "REPARAR_ACTIVIDADES",
                f"Restaurados {len(cambios)} registros con la actividad cortada",
                "script",
                momento,
            ),
        )
        conexion.commit()
        print(f"\nAPLICADO: {len(cambios)} registros actualizados")
    elif args.aplicar:
        conexion.rollback()
        print("\nNo hay cambios que aplicar")
    else:
        conexion.rollback()
        print("\nSIMULACION: no se cambio nada (use --aplicar para guardar)")

    conexion.close()

    reporte = {
        "fecha": datetime.now().isoformat(timespec="seconds"),
        "aplicado": bool(args.aplicar and cambios),
        "revisados": len(filas),
        "restaurados": len(cambios),
        "cambios": cambios,
        "ambiguas": ambiguas,
        "sin_coincidencia": sin_coincidencia,
    }
    try:
        with open(args.reporte, "w", encoding="utf-8") as archivo:
            json.dump(reporte, archivo, ensure_ascii=False, indent=2)
        print(f"Informe: {args.reporte}")
    except OSError as error:
        print(f"AVISO: no se pudo escribir el informe: {error}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
