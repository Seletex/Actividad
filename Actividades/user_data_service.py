"""
Sincronización de usuarios, actividades personales y configuraciones.

La sincronización no modifica las contraseñas existentes. Antes de escribir
crea respaldos de las tablas de configuración y usa una transacción única.
"""

import difflib
import json
import os
import re
import unicodedata
import uuid
from datetime import datetime

import config
import database as db
from config import logger


_TABLAS_RESPALDO = [
    "usuarios",
    "actividades_personales",
    "configuracion_usuario",
    "listas_globales",
]


def _archivo_usuarios(ruta_seleccionada=None):
    """Obtiene el JSON de usuarios incluido o el seleccionado por el admin."""
    candidatos = [
        ruta_seleccionada,
        config.USERS_FILE,
        os.path.join(config.DATA_DIR, "usuarios.json"),
        os.path.join(config.BASE_DIR, "usuarios.json"),
    ]
    vistos = set()
    for ruta in candidatos:
        if not ruta or ruta in vistos:
            continue
        vistos.add(ruta)
        if os.path.exists(ruta):
            return ruta
    raise FileNotFoundError(
        "No se encontró usuarios.json en el despliegue"
    )


def _archivo_configuracion():
    """Obtiene el JSON de listas globales incluido en el despliegue."""
    candidatos = [
        config.CONFIG_FILE,
        os.path.join(config.DATA_DIR, "config_actividades.json"),
        os.path.join(config.BASE_DIR, "config_actividades.json"),
    ]
    vistos = set()
    for ruta in candidatos:
        if not ruta or ruta in vistos:
            continue
        vistos.add(ruta)
        if os.path.exists(ruta):
            return ruta
    return None


def _nombre_respaldo(tabla):
    sello = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{tabla}_backup_{sello}_{uuid.uuid4().hex[:6]}"


def _insertar_usuario(cursor, usuario):
    if db.DATABASE_URL:
        cursor.execute(
            "INSERT INTO usuarios (username) VALUES (%s) "
            "ON CONFLICT (username) DO NOTHING",
            (usuario,),
        )
    else:
        cursor.execute(
            "INSERT OR IGNORE INTO usuarios (username) VALUES (?)",
            (usuario,),
        )
    return cursor.rowcount


def _clave_actividad(actividad):
    """Normaliza una actividad para comparar sin numeración ni espacios."""
    texto = unicodedata.normalize("NFKC", str(actividad or "")).strip().casefold()
    texto = re.sub(r"^\s*\d+\s*[.)-]\s*", "", texto)
    return re.sub(r"\s+", " ", texto)


def _tiene_numeracion(actividad):
    return bool(re.match(r"^\s*\d+\s*[.)-]\s*", str(actividad or "")))


def _actividades_similares(primera, segunda):
    return difflib.SequenceMatcher(
        None, _clave_actividad(primera), _clave_actividad(segunda)
    ).ratio() >= 0.95


def _mejor_actividad(primera, segunda):
    """Prefiere la versión sin numeración y, en empate, la más corta."""
    return min(
        (primera, segunda),
        key=lambda valor: (_tiene_numeracion(valor), len(str(valor or ""))),
    )


def _consultar_actividades(cursor, usuario):
    if db.DATABASE_URL:
        cursor.execute(
            "SELECT actividad FROM actividades_personales WHERE username = %s",
            (str(usuario),),
        )
    else:
        cursor.execute(
            "SELECT actividad FROM actividades_personales WHERE username = ?",
            (str(usuario),),
        )
    return [str(row[0] or "") for row in cursor.fetchall()]


def _eliminar_actividad(cursor, usuario, actividad):
    if db.DATABASE_URL:
        cursor.execute(
            "DELETE FROM actividades_personales WHERE username = %s AND actividad = %s",
            (str(usuario), actividad),
        )
    else:
        cursor.execute(
            "DELETE FROM actividades_personales WHERE username = ? AND actividad = ?",
            (str(usuario), actividad),
        )


def sincronizar_datos_usuarios(ruta_seleccionada=None):
    """Sincroniza el JSON de usuarios sin sobrescribir contraseñas."""
    ruta = _archivo_usuarios(ruta_seleccionada)
    with open(ruta, "r", encoding="utf-8") as archivo:
        datos = json.load(archivo)

    usuarios = [str(u).strip() for u in datos.get("usuarios", []) if str(u).strip()]
    actividades = datos.get("actividades", {}) or {}
    configuraciones = datos.get("configuraciones", {}) or {}
    listas = {}
    ruta_config = _archivo_configuracion()
    if ruta_config:
        try:
            with open(ruta_config, "r", encoding="utf-8") as archivo:
                listas = json.load(archivo) or {}
        except (OSError, json.JSONDecodeError):
            logger.exception("No se pudo leer config_actividades.json")
            listas = {}
    respaldos = {}
    resumen = {
        "usuarios_nuevos": 0,
        "actividades": 0,
        "actividades_eliminadas": 0,
        "configuraciones": 0,
        "listas": 0,
    }

    with db.db_session() as conn:
        cursor = conn.cursor()

        for tabla in _TABLAS_RESPALDO:
            nombre = _nombre_respaldo(tabla)
            respaldos[tabla] = nombre
            cursor.execute(
                f'CREATE TABLE "{nombre}" AS SELECT * FROM "{tabla}"'
            )

        for usuario in usuarios:
            resumen["usuarios_nuevos"] += _insertar_usuario(cursor, usuario)

        for usuario, items in actividades.items():
            if not isinstance(items, list):
                continue

            existentes = _consultar_actividades(cursor, usuario)
            conservadas = []
            for actividad in existentes:
                if not _clave_actividad(actividad):
                    continue
                indice = next(
                    (
                        i
                        for i, conservada in enumerate(conservadas)
                        if _actividades_similares(actividad, conservada)
                    ),
                    None,
                )
                if indice is None:
                    conservadas.append(actividad)
                    continue

                ganador = _mejor_actividad(conservadas[indice], actividad)
                perdedor = actividad if ganador == conservadas[indice] else conservadas[indice]
                _eliminar_actividad(cursor, usuario, perdedor)
                resumen["actividades_eliminadas"] += 1
                conservadas[indice] = ganador

            for actividad in items:
                actividad = str(actividad).strip()
                if not _clave_actividad(actividad):
                    continue
                if any(
                    _actividades_similares(actividad, conservada)
                    for conservada in conservadas
                ):
                    continue
                if db.DATABASE_URL:
                    cursor.execute(
                        "INSERT INTO actividades_personales (username, actividad) "
                        "VALUES (%s, %s) ON CONFLICT (username, actividad) DO NOTHING",
                        (str(usuario), actividad),
                    )
                else:
                    cursor.execute(
                        "INSERT OR IGNORE INTO actividades_personales "
                        "(username, actividad) VALUES (?, ?)",
                        (str(usuario), actividad),
                    )
                if cursor.rowcount > 0:
                    resumen["actividades"] += 1
                    conservadas.append(actividad)

        for usuario, config_usuario in configuraciones.items():
            if not isinstance(config_usuario, dict):
                continue
            for clave, valor in config_usuario.items():
                valor_serializado = json.dumps(valor, ensure_ascii=False)
                if db.DATABASE_URL:
                    cursor.execute(
                        "INSERT INTO configuracion_usuario (username, clave, valor) "
                        "VALUES (%s, %s, %s) "
                        "ON CONFLICT (username, clave) DO UPDATE SET valor = EXCLUDED.valor",
                        (str(usuario), str(clave), valor_serializado),
                    )
                else:
                    cursor.execute(
                        "INSERT INTO configuracion_usuario (username, clave, valor) "
                        "VALUES (?, ?, ?) "
                        "ON CONFLICT(username, clave) DO UPDATE SET valor = excluded.valor",
                        (str(usuario), str(clave), valor_serializado),
                    )
                resumen["configuraciones"] += max(0, cursor.rowcount)

        mapping_listas = {
            "actividades": "actividad",
            "dependencias": "ubicacion",
            "tipos_solicitud": "tipo_solicitud",
            "medios_solicitud": "medio_solicitud",
        }
        for clave, tipo in mapping_listas.items():
            valores = listas.get(clave, [])
            if not isinstance(valores, list):
                continue
            for valor in valores:
                valor = str(valor).strip()
                if not valor:
                    continue
                if db.DATABASE_URL:
                    cursor.execute(
                        "INSERT INTO listas_globales (tipo, valor) VALUES (%s, %s) "
                        "ON CONFLICT (tipo, valor) DO NOTHING",
                        (tipo, valor),
                    )
                else:
                    cursor.execute(
                        "INSERT OR IGNORE INTO listas_globales (tipo, valor) "
                        "VALUES (?, ?)",
                        (tipo, valor),
                    )
                resumen["listas"] += max(0, cursor.rowcount)

    db.clear_cache()
    logger.warning(
        "Datos de usuarios sincronizados desde %s: %s",
        ruta,
        resumen,
    )
    return {
        "archivo": ruta,
        "resumen": resumen,
        "respaldos": respaldos,
    }
