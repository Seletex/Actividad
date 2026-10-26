"""
respaldar_automatico.py - Respaldo automatico de PostgreSQL hacia una carpeta local.

Por que existe
--------------
La base de datos PostgreSQL gratuita de Render expira a los 30 dias y Render
elimina la base junto con todos sus datos, sin conservar ninguna copia. Este
script baja una copia a una carpeta del equipo (por ejemplo la carpeta
compartida de la red interna), de modo que la perdida de la base en la nube
deje de significar la perdida de la informacion.

Que contiene el respaldo
------------------------
Un ZIP con dos tipos de copia:

- ``base_completa.sql``: volcado completo de la base hecho con ``pg_dump``
  (registros, usuarios con sus contrasenas, bitacora y sesiones). Permite
  restaurar la aplicacion tal como estaba. Requiere tener instalado
  ``pg_dump``; si no esta, el respaldo se genera igual sin este archivo.
- ``registros.csv``, ``usuarios.json`` y ``manifiesto.json``: copia legible
  de los datos operativos, para abrir en Excel o reimportar desde la web.

Como usarlo
-----------
Desde el equipo, con la URL externa de PostgreSQL:

    python respaldar_automatico.py ^
        --url "postgresql://usuario:clave@ep-xxxx-yyy.us-west-2.aws.neon.tech/neondb?sslmode=require" ^
        --destino "\\192.168.10.2\\respaldos_actividades"

Para que se ejecute solo, cree una tarea programada de Windows con este mismo
comando (a diario, por ejemplo a las 18:00). El ZIP queda con la fecha y hora
en el nombre y el script conserva solo los ultimos respaldos indicados con
--conservar (30 por defecto).

Con ``--sin-dump`` se omite ``base_completa.sql`` y el ZIP no lleva
contrasenas, igual que el respaldo que genera la aplicacion.
"""

import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime

# Tiempo maximo que puede tardar pg_dump antes de darse por vencido.
_TIEMPO_MAXIMO_DUMP = 300

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:
    print("ERROR: falta psycopg2. Ejecute: pip install psycopg2-binary")
    sys.exit(1)


# Encabezados que la aplicacion reconoce al importar un Excel.
COLUMNAS_REGISTRO = [
    "ID", "USUARIO", "TIPO DE ACTIVIDAD", "FECHA", "DEPENDENCIA", "SOLICITANTE",
    "TIPO DE SOLICITUD", "MEDIO DE SOLICITUD", "DESCRIPCIÓN", "CUMPLIDO",
    "FECHA ATENCIÓN", "OBSERVACIONES",
]


def _texto(valor):
    """Convierte cualquier valor de PostgreSQL en texto utilizable en Excel."""
    if valor is None:
        return ""
    if hasattr(valor, "strftime"):
        return valor.strftime("%Y-%m-%d %H:%M:%S")
    return str(valor)


def _consultar(cursor, sql):
    cursor.execute(sql)
    return cursor.fetchall()


def buscar_pg_dump():
    """Localiza ``pg_dump``. Devuelve la ruta o ``None`` si no esta instalado."""
    ruta = shutil.which("pg_dump")
    if ruta:
        return ruta
    # En Windows no siempre queda en el PATH: se busca en PostgreSQL.
    candidatos = sorted(
        glob.glob(r"C:\Program Files\PostgreSQL\*\bin\pg_dump.exe"),
        reverse=True,
    )
    return candidatos[0] if candidatos else None


def volcar_base_completa(url, ruta_pg_dump):
    """Devuelve el volcado SQL completo de la base, o ``None`` si no se pudo.

    Incluye las contrasenas (hashes) y la bitacora, para que una restauracion
    deje la aplicacion exactamente como estaba. Se usa ``--clean --if-exists``
    para que el SQL se pueda cargar sobre una base vacia o sobre una existente.
    """
    try:
        resultado = subprocess.run(
            [
                ruta_pg_dump,
                "--no-owner",
                "--no-privileges",
                "--clean",
                "--if-exists",
                url,
            ],
            capture_output=True,
            timeout=_TIEMPO_MAXIMO_DUMP,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"AVISO: no se pudo ejecutar pg_dump: {exc}")
        return None

    if resultado.returncode != 0:
        detalle = resultado.stderr.decode("utf-8", "replace").strip()
        print(f"AVISO: pg_dump devolvio {resultado.returncode}: {detalle[:300]}")
        return None
    if not resultado.stdout:
        print("AVISO: pg_dump no devolvio datos")
        return None
    return resultado.stdout


def main():
    analizador = argparse.ArgumentParser(
        description="Genera un respaldo local de la base PostgreSQL de la aplicacion."
    )
    analizador.add_argument(
        "--url",
        default=os.environ.get("DATABASE_URL", ""),
        help="URL de conexion a PostgreSQL (o variable de entorno DATABASE_URL).",
    )
    analizador.add_argument(
        "--destino",
        default=os.path.join(
            os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
            "ActividadesData",
            "respaldos",
        ),
        help="Carpeta donde se guardan los respaldos.",
    )
    analizador.add_argument(
        "--conservar",
        type=int,
        default=30,
        help="Cuantos respaldos antiguos se conservan (0 = todos).",
    )
    analizador.add_argument(
        "--sin-dump",
        action="store_true",
        help=(
            "No incluir base_completa.sql. El respaldo queda sin contrasenas, "
            "como el que genera la aplicacion."
        ),
    )
    argumentos = analizador.parse_args()

    if not argumentos.url:
        print("ERROR: falta --url (o la variable de entorno DATABASE_URL).")
        return 2

    try:
        os.makedirs(argumentos.destino, exist_ok=True)
    except OSError as exc:
        print(f"ERROR: no se pudo crear la carpeta de destino: {exc}")
        return 2

    conexion = None
    try:
        conexion = psycopg2.connect(argumentos.url, connect_timeout=20)
        conexion.autocommit = True
        cursor = conexion.cursor(cursor_factory=RealDictCursor)

        registros = _consultar(
            cursor,
            "SELECT id, usuario, tipo_actividad, fecha, dependencia, solicitante, "
            "tipo_solicitud, medio_solicitud, descripcion, cumplido, "
            "fecha_atencion, observaciones FROM registros "
            "WHERE borrado IS NULL OR borrado = 0 ORDER BY id",
        )
        usuarios = _consultar(cursor, "SELECT username FROM usuarios ORDER BY username")
        actividades = _consultar(
            cursor, "SELECT username, actividad FROM actividades_personales ORDER BY username"
        )
        configuraciones = _consultar(
            cursor, "SELECT username, clave, valor FROM configuracion_usuario ORDER BY username"
        )
        listas = _consultar(
            cursor, "SELECT tipo, valor FROM listas_globales ORDER BY tipo, valor"
        )
    except Exception as exc:
        print(f"ERROR: no se pudo leer la base de datos: {exc}")
        if conexion:
            conexion.close()
        return 1
    finally:
        if conexion and not conexion.closed:
            pass

    # Arma las estructuras que usa la aplicacion para restaurar.
    mapa_actividades = {}
    for fila in actividades:
        mapa_actividades.setdefault(fila["username"], []).append(fila["actividad"])

    mapa_configuraciones = {}
    for fila in configuraciones:
        valor = fila["valor"]
        try:
            valor = json.loads(valor)
        except (TypeError, ValueError):
            pass
        mapa_configuraciones.setdefault(fila["username"], {})[fila["clave"]] = valor

    mapa_listas = {
        "actividades": [], "ubicaciones": [],
        "tipos_solicitud": [], "medios_solicitud": [],
    }
    claves = {
        "actividad": "actividades",
        "ubicacion": "ubicaciones",
        "tipo_solicitud": "tipos_solicitud",
        "medio_solicitud": "medios_solicitud",
    }
    for fila in listas:
        destino = claves.get(fila["tipo"])
        if destino:
            mapa_listas[destino].append(fila["valor"])

    usuarios_json = {
        "usuarios": [fila["username"] for fila in usuarios],
        "actividades": mapa_actividades,
        "configuraciones": mapa_configuraciones,
        "listas_globales": mapa_listas,
    }

    # Copia completa de la base: es la que permite restaurar todo, incluidas
    # las contrasenas. Si pg_dump no esta, el respaldo operativo se genera igual.
    volcado = None
    if not argumentos.sin_dump:
        ruta_pg_dump = buscar_pg_dump()
        if ruta_pg_dump:
            volcado = volcar_base_completa(argumentos.url, ruta_pg_dump)
        else:
            print(
                "AVISO: no se encontro pg_dump; el respaldo no incluira "
                "base_completa.sql"
            )

    sello = datetime.now().strftime("%Y%m%d_%H%M%S")
    nombre = f"respaldo_actividades_{sello}.zip"
    ruta = os.path.join(argumentos.destino, nombre)

    import io

    buffer_csv = io.StringIO()
    buffer_csv.write(",".join(COLUMNAS_REGISTRO) + "\n")
    for fila in registros:
        valores = [
            fila["id"], fila["usuario"], fila["tipo_actividad"], _texto(fila["fecha"]),
            fila["dependencia"], fila["solicitante"], fila["tipo_solicitud"],
            fila["medio_solicitud"], fila["descripcion"], fila["cumplido"],
            fila["fecha_atencion"], fila["observaciones"],
        ]
        escapados = []
        for valor in valores:
            texto = _texto(valor).replace('"', '""')
            escapados.append(f'"{texto}"')
        buffer_csv.write(",".join(escapados) + "\n")

    manifiesto = {
        "generado": datetime.now().isoformat(timespec="seconds"),
        "registros": len(registros),
        "usuarios": len(usuarios),
        "actividades_personales": len(actividades),
        "configuraciones": len(configuraciones),
        "listas_globales": len(listas),
        "incluye_contrasenas": bool(volcado),
        "incluye_base_completa": bool(volcado),
        "origen": argumentos.url.split("@")[-1],
    }

    with zipfile.ZipFile(ruta, "w", compression=zipfile.ZIP_DEFLATED) as zip_file:
        if volcado:
            zip_file.writestr("base_completa.sql", volcado)
        zip_file.writestr("registros.csv", buffer_csv.getvalue().encode("utf-8-sig"))
        zip_file.writestr(
            "usuarios.json",
            json.dumps(usuarios_json, ensure_ascii=False, indent=2, default=str).encode("utf-8"),
        )
        zip_file.writestr(
            "manifiesto.json",
            json.dumps(manifiesto, ensure_ascii=False, indent=2, default=str).encode("utf-8"),
        )
        zip_file.writestr(
            "LEEME.txt",
            (
                "RESPALDO DE ACTIVIDADES\n"
                "=======================\n\n"
                "Este archivo contiene los datos operativos de la aplicacion.\n"
                + (
                    "Incluye base_completa.sql: copia total de la base, con los\n"
                    "usuarios y sus contrasenas cifradas. Tratar como confidencial.\n"
                    if volcado
                    else "No incluye contrasenas ni hashes de contrasena.\n"
                )
                + "\n"
                "Restauracion completa (recomendada; deja todo como estaba):\n"
                "  psql \"postgresql://usuario:clave@servidor/base\" -f base_completa.sql\n"
                "\n"
                "Restauracion parcial, desde la web:\n"
                "1. Registros: use 'Reemplazar todos los registros' y registros.csv\n"
                "   convertido a .xlsx (mismos encabezados).\n"
                "2. Usuarios, actividades y catalogos: use 'Sincronizar datos de\n"
                "   usuarios' y usuarios.json.\n"
                "3. Contrasenas: deben asignarse nuevamente desde Gestion >\n"
                "   Usuarios del Sistema.\n"
            ).encode("utf-8"),
        )

    cursor.close()
    conexion.close()

    # Conserva solo los respaldos mas recientes.
    eliminados = 0
    if argumentos.conservar > 0:
        anteriores = sorted(
            glob.glob(os.path.join(argumentos.destino, "respaldo_actividades_*.zip"))
        )
        for viejo in anteriores[:-argumentos.conservar]:
            try:
                os.remove(viejo)
                eliminados += 1
            except OSError:
                pass

    print(f"Respaldo generado: {ruta}")
    print(f"  registros: {len(registros)} | usuarios: {len(usuarios)} | "
          f"actividades: {len(actividades)} | listas: {len(listas)}")
    print(f"  base completa (con contrasenas): {'si' if volcado else 'no'}")
    if eliminados:
        print(f"  respaldos antiguos eliminados: {eliminados}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
