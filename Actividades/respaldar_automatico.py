"""
respaldar_automatico.py - Respaldo automatico de PostgreSQL hacia una carpeta local.

Por que existe
--------------
La base de datos PostgreSQL gratuita de Render expira a los 30 dias y Render
elimina la base junto con todos sus datos, sin conservar ninguna copia. Este
script baja una copia a una carpeta del equipo (por ejemplo la carpeta
compartida de la red interna), de modo que la perdida de la base en la nube
deje de significar la perdida de la informacion.

Como usarlo
-----------
Desde el equipo, con la URL externa de PostgreSQL:

    python respaldar_automatico.py ^
        --url "postgresql://usuario:clave@dpg-xxxx-a.oregon-postgres.render.com/actividades" ^
        --destino "\\192.168.10.2\\respaldos_actividades"

Para que se ejecute solo, cree una tarea programada de Windows con este mismo
comando (a diario, por ejemplo a las 22:00). El ZIP queda con la fecha y hora
en el nombre y el script conserva solo los ultimos respaldos indicados con
--conservar (30 por defecto).

El archivo NO contiene contrasenas ni hashes de contrasena, igual que el
respaldo que genera la aplicacion.
"""

import argparse
import glob
import json
import os
import sys
import zipfile
from datetime import datetime

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
        "incluye_contrasenas": False,
        "origen": argumentos.url.split("@")[-1],
    }

    with zipfile.ZipFile(ruta, "w", compression=zipfile.ZIP_DEFLATED) as zip_file:
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
                "Este archivo contiene datos operativos de la aplicacion.\n"
                "No contiene contrasenas ni hashes de contrasena.\n\n"
                "Restauracion:\n"
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
    if eliminados:
        print(f"  respaldos antiguos eliminados: {eliminados}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
