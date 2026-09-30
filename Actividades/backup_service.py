"""
Generación de respaldos completos de la aplicación.

El archivo ZIP no incluye contraseñas ni hashes. Incluye los registros, la
configuración de usuarios, actividades personales y listas globales para poder
restaurarlos mediante las herramientas de la aplicación.
"""

import io
import json
import zipfile
from datetime import datetime

import database as db
from config import logger
from export_service import preparar_dataframe_exportable


def _json_bytes(data):
    return json.dumps(
        data, ensure_ascii=False, indent=2, default=str
    ).encode("utf-8")


def _leer_usuarios():
    data = db.cargar_usuarios()
    return {
        "usuarios": data.get("usuarios", []) or [],
        "actividades": data.get("actividades", {}) or {},
        "configuraciones": data.get("configuraciones", {}) or {},
    }


def _leer_listas():
    return {
        "actividades": db.cargar_actividades_globales(),
        "ubicaciones": db.cargar_ubicaciones(),
        "tipos_solicitud": db.cargar_tipos_solicitud(),
        "medios_solicitud": db.cargar_medios_solicitud(),
    }


def crear_respaldo_completo():
    """Crea un ZIP descargable con los datos operativos de la aplicación."""
    generado = datetime.now().strftime("%Y%m%d_%H%M%S")
    registros = db.cargar_registros(None)
    registros_export = preparar_dataframe_exportable(registros)
    usuarios = _leer_usuarios()
    listas = _leer_listas()
    resumen = {
        "generado": datetime.now().isoformat(timespec="seconds"),
        "registros": int(len(registros)),
        "usuarios": len(usuarios["usuarios"]),
        "actividades_personales": sum(
            len(items) for items in usuarios["actividades"].values()
        ),
        "listas_globales": sum(len(items) for items in listas.values()),
        "incluye_contrasenas": False,
    }

    archivo = io.BytesIO()
    with zipfile.ZipFile(
        archivo, mode="w", compression=zipfile.ZIP_DEFLATED
    ) as zip_file:
        # CSVutf-8 con BOM para abrirlo directamente en Excel.
        zip_file.writestr(
            "registros.csv",
            registros_export.to_csv(index=False).encode("utf-8-sig"),
        )
        try:
            excel = io.BytesIO()
            registros_export.to_excel(excel, index=False, engine="openpyxl")
            zip_file.writestr("registros.xlsx", excel.getvalue())
        except Exception:
            logger.exception("No se pudo incluir el Excel en el respaldo")

        zip_file.writestr("usuarios.json", _json_bytes(usuarios))
        zip_file.writestr("listas_globales.json", _json_bytes(listas))
        zip_file.writestr("manifiesto.json", _json_bytes(resumen))
        zip_file.writestr(
            "LEEME.txt",
            (
                "RESPALDO DE ACTIVIDADES\n"
                "=======================\n\n"
                "Este archivo contiene datos operativos de la aplicación.\n"
                "No contiene contraseñas ni hashes de contraseña.\n\n"
                "Restauración:\n"
                "1. Registros: use Reemplazar todos los registros y este Excel.\n"
                "2. Usuarios y configuración: use Sincronizar datos de usuarios "
                "y usuarios.json.\n"
                "3. Contraseñas: deben asignarse nuevamente desde Gestión > "
                "Usuarios del Sistema.\n\n"
                "Conserve este archivo en una ubicación privada.\n"
            ).encode("utf-8"),
        )

    archivo.seek(0)
    nombre = f"respaldo_actividades_{generado}.zip"
    logger.warning("Respaldo completo generado: %s (%s registros)", nombre, resumen["registros"])
    return archivo, nombre, resumen
