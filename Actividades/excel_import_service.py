"""
Servicio de importación de registros desde un archivo Excel.

La función de reemplazo trabaja dentro de una sola transacción: primero crea
una tabla de respaldo, luego reemplaza los registros y, si cualquier operación
falla, se revierte todo el proceso.
"""

import re
import unicodedata
import uuid
from datetime import datetime

import pandas as pd

import database as db
from config import logger


_COLUMNAS = [
    "id",
    "usuario",
    "tipo_actividad",
    "fecha",
    "dependencia",
    "solicitante",
    "tipo_solicitud",
    "medio_solicitud",
    "descripcion",
    "cumplido",
    "fecha_atencion",
    "observaciones",
]

_ENCABEZADOS = {
    "ID": "id",
    "USUARIO": "usuario",
    "TIPO DE ACTIVIDAD": "tipo_actividad",
    "ACTIVIDAD": "tipo_actividad",
    "FECHA": "fecha",
    "DEPENDENCIA": "dependencia",
    "UBICACION": "dependencia",
    "LUGAR": "dependencia",
    "SOLICITANTE": "solicitante",
    "TIPO DE SOLICITUD": "tipo_solicitud",
    "MEDIO DE SOLICITUD": "medio_solicitud",
    "MEDIO": "medio_solicitud",
    "DESCRIPCION": "descripcion",
    "DESCRIPCIÓN": "descripcion",
    "CUMPLIDO": "cumplido",
    "FECHA ATENCION": "fecha_atencion",
    "FECHA ATENCIÓN": "fecha_atencion",
    "OBSERVACIONES": "observaciones",
}


def _normalizar_columna(nombre):
    texto = str(nombre or "").strip().upper()
    texto = unicodedata.normalize("NFKD", texto)
    texto = texto.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", texto)


def _normalizar_valor(valor):
    if valor is None:
        return ""
    try:
        if pd.isna(valor):
            return ""
    except (TypeError, ValueError):
        pass
    if hasattr(valor, "strftime"):
        return valor.strftime("%Y-%m-%d %H:%M:%S")
    return str(valor).strip()


def _leer_filas(ruta):
    """Lee el Excel y devuelve filas normalizadas para los once campos."""
    frame = pd.read_excel(ruta, engine="openpyxl")
    disponibles = {}
    for columna in frame.columns:
        clave = _ENCABEZADOS.get(_normalizar_columna(columna))
        if clave and clave not in disponibles:
            disponibles[clave] = columna

    requeridas = {"usuario", "tipo_actividad", "fecha", "cumplido"}
    faltantes = requeridas - set(disponibles)
    if faltantes:
        raise ValueError(
            "El Excel no contiene las columnas requeridas: "
            + ", ".join(sorted(faltantes))
        )

    filas = []
    ids_vistos = set()
    siguiente_id = 1
    for _, fila in frame.iterrows():
        valores = {}
        for columna in _COLUMNAS:
            origen = disponibles.get(columna)
            valores[columna] = _normalizar_valor(
                fila[origen] if origen is not None else ""
            )

        id_texto = valores.get("id", "")
        if id_texto:
            try:
                id_registro = int(float(id_texto))
            except (TypeError, ValueError):
                id_registro = siguiente_id
        else:
            id_registro = siguiente_id
        siguiente_id = max(siguiente_id, id_registro + 1)

        if id_registro in ids_vistos:
            raise ValueError(
                f"El Excel contiene el ID {id_registro} más de una vez"
            )
        ids_vistos.add(id_registro)
        valores["id"] = id_registro
        filas.append(valores)

    if not filas:
        raise ValueError("El archivo Excel no contiene registros")
    return filas


def _nombre_respaldo():
    sello = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"registros_backup_{sello}_{uuid.uuid4().hex[:6]}"


def reemplazar_registros_desde_excel(ruta):
    """Reemplaza todos los registros por los del Excel, con respaldo previo.

    Devuelve un diccionario con ``total`` y ``respaldo``. La creación del
    respaldo, el borrado y la inserción se ejecutan en la misma transacción.
    """
    filas = _leer_filas(ruta)
    nombre_respaldo = _nombre_respaldo()
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    insert_columns = _COLUMNAS + ["sync_uid", "updated_at", "borrado"]
    insert_values = [
        tuple(fila[columna] for columna in _COLUMNAS)
        + (uuid.uuid4().hex, ahora, 0)
        for fila in filas
    ]
    insert_markers = ", ".join(["?"] * len(insert_columns))

    with db.db_session() as conn:
        cursor = conn.cursor()

        cursor.execute(
            db.fix_query(f'CREATE TABLE "{nombre_respaldo}" AS SELECT * FROM registros')
        )
        cursor.execute(db.fix_query("DELETE FROM registros"))

        cursor.executemany(
            db.fix_query(
                f"INSERT INTO registros ({', '.join(insert_columns)}) "
                f"VALUES ({insert_markers})"
            ),
            insert_values,
        )

        if db.DATABASE_URL:
            cursor.execute(
                "SELECT setval(pg_get_serial_sequence('registros', 'id'), "
                "COALESCE((SELECT MAX(id) FROM registros), 1), true)"
            )

    logger.warning(
        "Registros reemplazados desde Excel: %s filas. Respaldo: %s",
        len(filas),
        nombre_respaldo,
    )
    return {"total": len(filas), "respaldo": nombre_respaldo}
