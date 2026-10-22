"""
fusionar_bases.py - Copia los datos de una base PostgreSQL a otra, fusionando.

Se creo para rescatar la base de Render que quedo suspendida al caducar el plan
gratuito: se reactiva pagando un mes, se copia todo a la base nueva (Neon) y
luego se puede borrar la de Render.

Que hace
--------
- ``registros``: la base de ORIGEN es la fuente de verdad (es la que estuvo en
  produccion). Se copia completa, conservando los identificadores.
  Por seguridad, si el origen tuviera MENOS registros que el destino, se niega
  a reemplazar (salvo que se pase --forzar), para no destruir datos.
- ``usuarios``: se copian los hashes de contrasena del origen, de modo que las
  contrasenas originales vuelven a funcionar. Un usuario que exista en el
  destino y no en el origen se conserva. Si el origen trae el hash vacio y el
  destino tiene uno, se conserva el del destino.
- ``actividades_personales``, ``listas_globales``: union sin duplicados.
- ``configuracion_usuario``: se queda el valor del origen.

Ejemplo:

    python fusionar_bases.py ^
        --origen "postgresql://...@dpg-xxxx-a.oregon-postgres.render.com/actividades?sslmode=require" ^
        --destino "postgresql://...@ep-xxxx.us-west-2.aws.neon.tech/neondb?sslmode=require" ^
        --contrasena-admin "UnaClaveTemporal"

Las contrasenas de los demas usuarios NO se tocan: se recuperan las originales
del origen.
"""

import argparse
import hashlib
import secrets
import sys
from datetime import datetime

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor, execute_values
except ImportError:
    print("ERROR: falta psycopg2. Ejecute: pip install psycopg2-binary")
    sys.exit(1)


PBKDF2_ITER = 260_000

# Columnas por tabla, en el orden en que se copian.
COLUMNAS = {
    "usuarios": [
        "username", "password_hash", "password_salt",
        "debe_cambiar_contrasena", "revision_sesion",
    ],
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


def columnas_de(cursor, tabla):
    cursor.execute(
        "SELECT column_name AS nombre FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name = %s",
        (tabla,),
    )
    nombres = []
    for fila in cursor.fetchall():
        nombres.append(fila["nombre"] if isinstance(fila, dict) else fila[0])
    return set(nombres)


def leer_tabla(cursor, tabla):
    """Devuelve las filas de una tabla como diccionarios."""
    existentes = columnas_de(cursor, tabla)
    if not existentes:
        return [], []
    elegidas = [c for c in COLUMNAS[tabla] if c in existentes]
    cursor.execute(f'SELECT {", ".join(elegidas)} FROM "{tabla}"')
    return elegidas, [dict(fila) for fila in cursor.fetchall()]


def contar(cursor, tabla):
    cursor.execute(f'SELECT COUNT(*) AS total FROM "{tabla}"')
    fila = cursor.fetchone()
    if isinstance(fila, dict):
        return fila["total"]
    return fila[0]


def main():
    analizador = argparse.ArgumentParser(
        description="Fusiona los datos de una base PostgreSQL (origen) en otra (destino)."
    )
    analizador.add_argument("--origen", required=True, help="URL de la base de Render.")
    analizador.add_argument("--destino", required=True, help="URL de la base de Neon.")
    analizador.add_argument(
        "--contrasena-admin",
        default="",
        help="Si se indica, deja esta contrasena al usuario admin (con cambio obligatorio).",
    )
    analizador.add_argument(
        "--forzar",
        action="store_true",
        help="Permite reemplazar los registros aunque el origen tenga menos que el destino.",
    )
    argumentos = analizador.parse_args()

    print(f"Origen  (Render): {argumentos.origen.split('@')[-1]}")
    print(f"Destino (Neon)  : {argumentos.destino.split('@')[-1]}")
    print("-" * 62)

    try:
        origen = psycopg2.connect(argumentos.origen, connect_timeout=60)
    except Exception as exc:
        print(f"ERROR: no se pudo conectar con el ORIGEN (Render): {exc}")
        print("Compruebe que la base ya diga 'Available' en Render.")
        return 1
    try:
        destino = psycopg2.connect(argumentos.destino, connect_timeout=60)
    except Exception as exc:
        print(f"ERROR: no se pudo conectar con el DESTINO (Neon): {exc}")
        origen.close()
        return 1

    origen.autocommit = True
    destino.autocommit = False
    cur_o = origen.cursor(cursor_factory=RealDictCursor)
    cur_d = destino.cursor()

    try:
        total_origen = contar(cur_o, "registros")
        total_destino = contar(cur_d, "registros")
        print(f"Registros en el origen  : {total_origen}")
        print(f"Registros en el destino : {total_destino}")

        if total_origen < total_destino and not argumentos.forzar:
            print()
            print("DETENIDO: el origen tiene menos registros que el destino.")
            print("Reemplazar borraria informacion. Si aun asi quiere hacerlo,")
            print("repita el comando agregando --forzar.")
            return 1

        # ---- registros: el origen es la fuente de verdad ----
        columnas_r, filas_r = leer_tabla(cur_o, "registros")
        if filas_r:
            columnas_destino = columnas_de(cur_d, "registros")
            columnas_r = [c for c in columnas_r if c in columnas_destino]
            cur_d.execute('DELETE FROM "registros"')
            execute_values(
                cur_d,
                f'INSERT INTO "registros" ({", ".join(columnas_r)}) VALUES %s',
                [tuple(fila.get(c) for c in columnas_r) for fila in filas_r],
            )
            cur_d.execute("SELECT MAX(id) FROM registros")
            maximo = cur_d.fetchone()[0]
            cur_d.execute("SELECT pg_get_serial_sequence('registros', 'id')")
            secuencia = cur_d.fetchone()[0]
            if maximo and secuencia:
                cur_d.execute("SELECT setval(%s, %s, true)", (secuencia, maximo))
        print(f"  registros copiados      : {len(filas_r)}")

        # ---- usuarios: se conservan los hashes originales ----
        columnas_u, filas_u = leer_tabla(cur_o, "usuarios")
        cur_d.execute("SELECT username FROM usuarios")
        en_destino = {fila[0] for fila in cur_d.fetchall()}
        nuevos = 0
        actualizados = 0
        for fila in filas_u:
            valores = [fila.get(c) for c in columnas_u]
            if fila["username"] in en_destino:
                asignaciones = []
                for columna in columnas_u:
                    if columna == "username":
                        continue
                    if columna in ("password_hash", "password_salt"):
                        # Nunca se borra un hash existente con uno vacio.
                        asignaciones.append(
                            f"{columna} = COALESCE(NULLIF(EXCLUDED.{columna}, ''), usuarios.{columna})"
                        )
                    elif columna in ("debe_cambiar_contrasena", "revision_sesion"):
                        asignaciones.append(
                            f"{columna} = COALESCE(EXCLUDED.{columna}, 0)"
                        )
                    else:
                        asignaciones.append(f"{columna} = EXCLUDED.{columna}")
                cur_d.execute(
                    f'INSERT INTO "usuarios" ({", ".join(columnas_u)}) VALUES '
                    f'({", ".join(["%s"] * len(columnas_u))}) '
                    f'ON CONFLICT (username) DO UPDATE SET {", ".join(asignaciones)}',
                    valores,
                )
                actualizados += 1
            else:
                cur_d.execute(
                    f'INSERT INTO "usuarios" ({", ".join(columnas_u)}) VALUES '
                    f'({", ".join(["%s"] * len(columnas_u))})',
                    valores,
                )
                nuevos += 1
        cur_d.execute(
            "INSERT INTO usuarios (username) VALUES ('admin') ON CONFLICT DO NOTHING"
        )
        print(f"  usuarios nuevos         : {nuevos}")
        print(f"  usuarios actualizados   : {actualizados}")

        # ---- actividades personales (union) ----
        columnas_a, filas_a = leer_tabla(cur_o, "actividades_personales")
        for fila in filas_a:
            cur_d.execute(
                f'INSERT INTO "actividades_personales" ({", ".join(columnas_a)}) VALUES '
                f'({", ".join(["%s"] * len(columnas_a))}) ON CONFLICT DO NOTHING',
                [fila.get(c) for c in columnas_a],
            )
        print(f"  actividades del origen  : {len(filas_a)}")

        # ---- configuracion de usuario (el origen manda) ----
        columnas_c, filas_c = leer_tabla(cur_o, "configuracion_usuario")
        for fila in filas_c:
            cur_d.execute(
                'INSERT INTO "configuracion_usuario" (username, clave, valor) '
                "VALUES (%s, %s, %s) "
                "ON CONFLICT (username, clave) DO UPDATE SET valor = EXCLUDED.valor",
                (fila.get("username"), fila.get("clave"), fila.get("valor")),
            )
        print(f"  configuraciones         : {len(filas_c)}")

        # ---- listas globales (union) ----
        columnas_l, filas_l = leer_tabla(cur_o, "listas_globales")
        for fila in filas_l:
            cur_d.execute(
                f'INSERT INTO "listas_globales" ({", ".join(columnas_l)}) VALUES '
                f'({", ".join(["%s"] * len(columnas_l))}) ON CONFLICT DO NOTHING',
                [fila.get(c) for c in columnas_l],
            )
        print(f"  listas globales         : {len(filas_l)}")

        if argumentos.contrasena_admin:
            if len(argumentos.contrasena_admin) < 10:
                print("ERROR: la contrasena debe tener al menos 10 caracteres.")
                destino.rollback()
                return 1
            hash_guardado, salt = hashear_contrasena(argumentos.contrasena_admin)
            cur_d.execute(
                "UPDATE usuarios SET password_hash = %s, password_salt = %s, "
                "debe_cambiar_contrasena = 1, "
                "revision_sesion = COALESCE(revision_sesion, 0) + 1 "
                "WHERE username = 'admin'",
                (hash_guardado, salt),
            )
            print("  contrasena de admin     : asignada (cambio obligatorio)")

        destino.commit()

        print("-" * 62)
        print("Verificacion en el destino:")
        for tabla in ("registros", "usuarios", "actividades_personales",
                      "configuracion_usuario", "listas_globales"):
            print(f"  {tabla:24s} {contar(cur_d, tabla)}")

        cur_d.execute(
            "SELECT COUNT(*) FROM usuarios WHERE password_hash IS NOT NULL "
            "AND password_hash <> ''"
        )
        con_clave = cur_d.fetchone()[0]
        cur_d.execute("SELECT COUNT(*) FROM usuarios")
        total_usuarios = cur_d.fetchone()[0]
        print(f"  usuarios con contrasena: {con_clave} de {total_usuarios}")
        if con_clave < total_usuarios:
            print("  Los usuarios sin contrasena deben asignarse desde la web.")
    except Exception as exc:
        destino.rollback()
        print(f"ERROR durante la fusion: {type(exc).__name__}: {exc}", flush=True)
        import traceback
        traceback.print_exc()
        return 1
    finally:
        cur_o.close()
        cur_d.close()
        origen.close()
        destino.close()

    print("-" * 62)
    print("Fusion completada. " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
