"""Respaldo entre Neon (Render) y MySQL (260mb.net).

Neon es la base principal. El hosting de 260mb.net tiene una copia en MySQL
para poder seguir trabajando si Render o Neon fallan.

Este modulo hace dos cosas:

1. ``construir_respaldo``: arma un JSON con las tablas que necesita la version
   PHP. Lo consume ``php/respaldo.php`` desde el hosting de 260mb.net.
2. ``aplicar_respaldo``: recibe ese mismo JSON y lo aplica a Neon. Se usa solo
   cuando hubo una caida y se trabajo en la copia de 260mb.net.

Reglas de seguridad:

- El respaldo nunca se genera si falta ``RESPALDO_TOKEN``.
- La recuperacion solo inserta filas nuevas o actualiza las que llegan. Nunca
  borra una fila que no venga en el archivo.
- Las listas y las actividades personales se suman; no se reemplazan.
- Las contrasenas de Neon solo se cambian si la copia de 260 trae una
  contrasena distinta; la revision de sesion nunca baja.
- Si un ticket tiene el mismo radicado pero otra fecha de creacion, se marca
  como conflicto y no se toca.
"""

import hmac
import os
import uuid
from datetime import date, datetime, time
from decimal import Decimal

from config import logger
from database import db_session, get_cursor, get_db_connection, fix_query


FORMATO = "actividades-respaldo-1"

COLUMNAS = {
    "usuarios": [
        "username", "password_hash", "password_salt",
        "debe_cambiar_contrasena", "revision_sesion",
    ],
    "registros": [
        "id", "usuario", "tipo_actividad", "fecha", "dependencia",
        "solicitante", "tipo_solicitud", "medio_solicitud", "descripcion",
        "cumplido", "fecha_atencion", "observaciones", "sync_uid",
        "updated_at", "borrado",
    ],
    "listas_globales": ["tipo", "valor"],
    "actividades_personales": ["username", "actividad"],
    "configuracion_usuario": ["username", "clave", "valor"],
    "tickets": [
        "radicado", "dependencia", "solicitante", "correo", "telefono",
        "tipo_solicitud", "prioridad", "descripcion", "estado",
        "tecnico_asignado", "tecnicos_colaboradores", "solucion",
        "fecha_creacion", "fecha_atencion", "fecha_cierre",
        "actividades_ids",
    ],
}

ORDEN = {
    "usuarios": " ORDER BY username",
    "registros": " ORDER BY id",
    "listas_globales": " ORDER BY tipo, valor",
    "actividades_personales": " ORDER BY username, actividad",
    "configuracion_usuario": " ORDER BY username, clave",
    "tickets": " ORDER BY fecha_creacion, radicado",
}


# ---------------------------------------------------------------------------
# Token
# ---------------------------------------------------------------------------

def token_configurado():
    """True si Render tiene configurado el token de respaldo."""
    return bool(os.environ.get("RESPALDO_TOKEN", "").strip())


def token_valido(token):
    """Compara el token sin filtrar pistas por el tiempo de respuesta."""
    esperado = os.environ.get("RESPALDO_TOKEN", "").strip()
    recibido = str(token or "").strip()
    if not esperado or not recibido:
        return False
    return hmac.compare_digest(esperado, recibido)


# ---------------------------------------------------------------------------
# Exportar
# ---------------------------------------------------------------------------

def _valor_json(valor):
    """Convierte fechas y decimales a texto que MySQL y PHP entiendan."""
    if valor is None:
        return None
    if isinstance(valor, datetime):
        return valor.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(valor, date):
        return valor.strftime("%Y-%m-%d")
    if isinstance(valor, time):
        return valor.strftime("%H:%M:%S")
    if isinstance(valor, Decimal):
        return float(valor)
    if isinstance(valor, (bytes, bytearray)):
        return bytes(valor).hex()
    return valor


def _fila_a_dict(fila):
    """sqlite3.Row y RealDictRow se convierten igual a un diccionario."""
    return {clave: fila[clave] for clave in fila.keys()}


def construir_respaldo():
    """Devuelve el respaldo completo como diccionario listo para JSON."""
    conn = get_db_connection()
    try:
        cursor = get_cursor(conn)
        tablas = {}
        for tabla, columnas in COLUMNAS.items():
            sql = "SELECT %s FROM %s%s" % (
                ", ".join(columnas), tabla, ORDEN.get(tabla, "")
            )
            cursor.execute(sql)
            filas = []
            for fila in cursor.fetchall():
                datos = _fila_a_dict(fila)
                if tabla == "registros" and not datos.get("sync_uid"):
                    # Filas muy antiguas sin identificador estable. Se usa el
                    # id como respaldo para que la copia de 260 tenga una llave.
                    datos["sync_uid"] = "legacy-%s" % datos.get("id")
                filas.append({
                    columna: _valor_json(datos.get(columna))
                    for columna in columnas
                })
            tablas[tabla] = filas

        return {
            "formato": FORMATO,
            "generado": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "conteos": {tabla: len(filas) for tabla, filas in tablas.items()},
            "tablas": tablas,
        }
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Recuperar (MySQL -> Neon)
# ---------------------------------------------------------------------------

def _a_texto(valor):
    if valor is None:
        return ""
    return str(valor)


def _clave_contenido(fila):
    """Datos que no cambian cuando la fila se copia entre las dos bases."""
    fecha = _a_texto(fila.get("fecha")).replace("T", " ")[:19]
    return (
        _a_texto(fila.get("usuario")),
        fecha,
        _a_texto(fila.get("descripcion")),
    )


def _valor_bd(valor):
    """Normaliza booleanos y textos vacios antes de escribir."""
    if isinstance(valor, bool):
        return 1 if valor else 0
    return valor


def _insertar(cursor, tabla, fila, columnas):
    columnas = [c for c in columnas if c in fila]
    marcas = ", ".join(["?"] * len(columnas))
    sql = "INSERT INTO %s (%s) VALUES (%s)" % (
        tabla, ", ".join(columnas), marcas
    )
    cursor.execute(fix_query(sql), tuple(_valor_bd(fila[c]) for c in columnas))


def _actualizar(cursor, tabla, fila, columnas, condicion, parametros):
    columnas = [c for c in columnas if c in fila]
    if not columnas:
        return 0
    asignaciones = ", ".join("%s = ?" % c for c in columnas)
    sql = "UPDATE %s SET %s WHERE %s" % (tabla, asignaciones, condicion)
    valores = tuple(_valor_bd(fila[c]) for c in columnas) + tuple(parametros)
    cursor.execute(fix_query(sql), valores)
    return cursor.rowcount


def _aplicar_usuarios(cursor, filas):
    cursor.execute(
        "SELECT username, password_hash, revision_sesion FROM usuarios"
    )
    existentes = {f["username"]: _fila_a_dict(f) for f in cursor.fetchall()}
    insertados = actualizados = 0

    for fila in filas:
        nombre = _a_texto(fila.get("username")).strip()
        if not nombre:
            continue
        datos = {c: fila.get(c) for c in COLUMNAS["usuarios"] if c != "username"}
        if nombre not in existentes:
            _insertar(cursor, "usuarios", dict(datos, username=nombre),
                      COLUMNAS["usuarios"])
            insertados += 1
            continue

        # Una sesion abierta no debe revivir si la copia trae una revision
        # anterior. Se conserva siempre la mas alta.
        revision = max(
            int(existentes[nombre].get("revision_sesion") or 0),
            int(fila.get("revision_sesion") or 0),
        )
        datos["revision_sesion"] = revision

        # Si la copia no trae contrasena, no se borra la de Neon.
        if not datos.get("password_hash"):
            datos.pop("password_hash", None)
            datos.pop("password_salt", None)

        if _actualizar(cursor, "usuarios", datos,
                       [c for c in COLUMNAS["usuarios"] if c != "username"],
                       "username = ?", [nombre]):
            actualizados += 1

    return {"insertados": insertados, "actualizados": actualizados}


def _aplicar_registros(cursor, filas):
    cursor.execute("SELECT id, sync_uid, usuario, fecha, descripcion FROM registros")
    locales = [_fila_a_dict(f) for f in cursor.fetchall()]
    por_uid = {
        f["sync_uid"]: f for f in locales if f.get("sync_uid")
    }
    por_id = {f["id"]: f for f in locales}
    uids_entrantes = {
        _a_texto(f.get("sync_uid")).strip()
        for f in filas if _a_texto(f.get("sync_uid")).strip()
    }

    insertados = actualizados = adoptados = 0
    columnas = [c for c in COLUMNAS["registros"] if c != "id"]

    for fila in filas:
        uid = _a_texto(fila.get("sync_uid")).strip()
        datos = {c: fila.get(c) for c in columnas}
        if not uid:
            uid = uuid.uuid4().hex
        datos["sync_uid"] = uid
        if not datos.get("updated_at"):
            datos["updated_at"] = datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S.%f"
            )

        if uid in por_uid:
            _actualizar(cursor, "registros", datos, columnas,
                        "sync_uid = ?", [uid])
            actualizados += 1
            continue

        # Primera sincronizacion: la copia de 260 tiene identificadores
        # distintos. Se adopta la fila por id solo si el contenido coincide,
        # para no confundir dos registros diferentes que casualmente tengan
        # el mismo id.
        try:
            id_local = int(fila.get("id"))
        except (TypeError, ValueError):
            id_local = None
        local = por_id.get(id_local) if id_local is not None else None
        if (
            local
            and (not local.get("sync_uid") or local["sync_uid"] not in uids_entrantes)
            and _clave_contenido(local) == _clave_contenido(fila)
        ):
            _actualizar(cursor, "registros", datos, columnas,
                        "id = ?", [id_local])
            adoptados += 1
            continue

        _insertar(cursor, "registros", datos, columnas)
        insertados += 1

    return {
        "insertados": insertados,
        "actualizados": actualizados,
        "adoptados": adoptados,
    }


def _aplicar_listas(cursor, filas):
    cursor.execute("SELECT tipo, valor FROM listas_globales")
    existentes = {
        (_a_texto(f["tipo"]), _a_texto(f["valor"]))
        for f in cursor.fetchall()
    }
    insertados = 0
    for fila in filas:
        tipo = _a_texto(fila.get("tipo")).strip()
        valor = _a_texto(fila.get("valor")).strip()
        if not tipo or not valor or (tipo, valor) in existentes:
            continue
        _insertar(cursor, "listas_globales", {"tipo": tipo, "valor": valor},
                  COLUMNAS["listas_globales"])
        existentes.add((tipo, valor))
        insertados += 1
    return {"insertados": insertados}


def _aplicar_actividades(cursor, filas):
    cursor.execute("SELECT username, actividad FROM actividades_personales")
    existentes = {
        (_a_texto(f["username"]), _a_texto(f["actividad"]))
        for f in cursor.fetchall()
    }
    insertados = 0
    for fila in filas:
        username = _a_texto(fila.get("username")).strip()
        actividad = _a_texto(fila.get("actividad")).strip()
        if not username or not actividad or (username, actividad) in existentes:
            continue
        _insertar(cursor, "actividades_personales",
                  {"username": username, "actividad": actividad},
                  COLUMNAS["actividades_personales"])
        existentes.add((username, actividad))
        insertados += 1
    return {"insertados": insertados}


def _aplicar_configuracion(cursor, filas):
    insertados = actualizados = 0
    for fila in filas:
        username = _a_texto(fila.get("username")).strip()
        clave = _a_texto(fila.get("clave")).strip()
        if not username or not clave:
            continue
        sql = (
            "INSERT INTO configuracion_usuario (username, clave, valor) "
            "VALUES (?, ?, ?) "
            "ON CONFLICT (username, clave) DO UPDATE SET valor = excluded.valor"
        )
        cursor.execute(fix_query(sql), (
            username, clave, _a_texto(fila.get("valor")),
        ))
        if cursor.rowcount == 1:
            insertados += 1
        else:
            actualizados += 1
    return {"insertados": insertados, "actualizados": actualizados}


def _misma_fecha(valor_a, valor_b):
    a = _a_texto(valor_a).replace("T", " ")[:19]
    b = _a_texto(valor_b).replace("T", " ")[:19]
    if not a or not b:
        return True
    return a == b


def _aplicar_tickets(cursor, filas):
    cursor.execute("SELECT radicado, fecha_creacion FROM tickets")
    existentes = {
        f["radicado"]: _fila_a_dict(f) for f in cursor.fetchall()
    }
    insertados = actualizados = conflictos = 0

    for fila in filas:
        radicado = _a_texto(fila.get("radicado")).strip()
        if not radicado:
            continue
        datos = {c: fila.get(c) for c in COLUMNAS["tickets"]}
        if radicado in existentes:
            if not _misma_fecha(
                existentes[radicado].get("fecha_creacion"),
                fila.get("fecha_creacion"),
            ):
                # Dos tickets distintos con el mismo radicado: no se toca
                # nada y se informa para revisarlo a mano.
                conflictos += 1
                continue
            _actualizar(cursor, "tickets", datos,
                        COLUMNAS["tickets"], "radicado = ?", [radicado])
            actualizados += 1
        else:
            _insertar(cursor, "tickets", datos, COLUMNAS["tickets"])
            existentes[radicado] = {"radicado": radicado}
            insertados += 1

    return {
        "insertados": insertados,
        "actualizados": actualizados,
        "conflictos": conflictos,
    }


def aplicar_respaldo(datos):
    """Aplica a Neon un respaldo generado por la version PHP.

    Todo ocurre en una sola transaccion: si algo falla, Neon queda como estaba.
    """
    if not isinstance(datos, dict) or datos.get("formato") != FORMATO:
        raise ValueError("El archivo no tiene el formato de respaldo esperado")
    if not isinstance(datos.get("tablas"), dict):
        raise ValueError("El respaldo no incluye las tablas")

    tablas = datos["tablas"]
    resumen = {}
    with db_session() as conn:
        cursor = get_cursor(conn)
        resumen["usuarios"] = _aplicar_usuarios(
            cursor, tablas.get("usuarios") or []
        )
        resumen["registros"] = _aplicar_registros(
            cursor, tablas.get("registros") or []
        )
        resumen["listas_globales"] = _aplicar_listas(
            cursor, tablas.get("listas_globales") or []
        )
        resumen["actividades_personales"] = _aplicar_actividades(
            cursor, tablas.get("actividades_personales") or []
        )
        resumen["configuracion_usuario"] = _aplicar_configuracion(
            cursor, tablas.get("configuracion_usuario") or []
        )
        resumen["tickets"] = _aplicar_tickets(
            cursor, tablas.get("tickets") or []
        )
    logger.info("Respaldo aplicado a Neon: %s", resumen)
    return resumen
