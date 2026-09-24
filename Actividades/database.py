
"""
Módulo de base de datos SQLITE: reemplaza la versión basada en archivos.
Implementa la misma interfaz que database.py pero usando SQLite.
"""

import os
import json
import uuid
import hashlib
import hmac
import secrets
import sqlite3
import time
import random
import shutil
import pandas as pd
from datetime import datetime
from config import (
    EXCEL_FILE, USERS_FILE, CONFIG_FILE, DB_FILE, DATABASE_URL, COLUMNAS, 
    ACTIVIDADES_DEFAULT, UBICACIONES_DEFAULT, TIPOS_SOLICITUD_DEFAULT, MEDIOS_SOLICITUD_DEFAULT,
    logger, DIRS_SEARCH, MASTER_DIR, DATA_DIR
)
from utils import cache_decorator, medir_tiempo, clear_cache
from contextlib import contextmanager

# Intentar importar psycopg2 para PostgreSQL (Render)
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:
    psycopg2 = None

# DB_NAME eliminado, usamos DB_FILE de config

def retry_operation(max_retries=5, base_delay=0.5):
    """Decorador para reintentar operaciones de BD en caso de bloqueo o I/O error"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except (sqlite3.OperationalError, sqlite3.DatabaseError, OSError, PermissionError) as e:
                    last_exception = e
                    sleep_time = base_delay * (2 ** attempt) + random.uniform(0, 0.5)
                    logger.warning(f"[WARNING] Reintento {attempt + 1}/{max_retries} en {func.__name__} por: {e}. Esperando {sleep_time:.2f}s")
                    time.sleep(sleep_time)
            logger.error(f"[ERROR] Fallo crítico en {func.__name__} después de {max_retries} intentos.")
            raise last_exception
        return wrapper
    return decorator

def get_db_connection():
    """Obtiene una conexión a PostgreSQL o SQLite según la configuración."""
    if DATABASE_URL:
        if psycopg2 is None:
            raise RuntimeError("DATABASE_URL está configurado, pero psycopg2 no está instalado")
        try:
            return psycopg2.connect(DATABASE_URL)
        except Exception:
            logger.exception("No se pudo conectar a PostgreSQL")
            raise
    
    # Resiliencia para SQLite en red
    conn = None
    try:
        # Timeout aumentado considerablemente para redes lentas
        conn = sqlite3.connect(DB_FILE, timeout=60)
        conn.row_factory = sqlite3.Row
        # WAL mode: mejor concurrencia para múltiples usuarios en servidor
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=FULL")      # Máxima seguridad de datos
    except Exception as e:
        logger.error(f"Error fatal conectando a SQLite: {e}")
        raise e
        
    return conn

def get_cursor(conn):
    """Devuelve un cursor tipo diccionario compatible entre ambos motores"""
    if DATABASE_URL and psycopg2 and isinstance(conn, psycopg2.extensions.connection):
        return conn.cursor(cursor_factory=RealDictCursor)
    return conn.cursor()

@contextmanager
def db_session():
    """Context manager para asegurar que las conexiones se cierren siempre"""
    conn = get_db_connection()
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def fix_query(query):
    """Adapta la sintaxis de la consulta de SQLite (?) a Postgres (%s)"""
    if DATABASE_URL and psycopg2:
        return query.replace('?', '%s').replace('INSERT OR IGNORE', 'INSERT').replace('AUTOINCREMENT', '')
    return query

@retry_operation(max_retries=5, base_delay=1.0)
def inicializar_tablas():
    """Crea todas las tablas necesarias si no existen (SQLite y Postgres)"""
    try:
        conn = get_db_connection()
        cursor = get_cursor(conn)
        
        # 1. Crear tabla de usuarios con soporte de autenticación
        cursor.execute(fix_query("""
            CREATE TABLE IF NOT EXISTS usuarios (
                username TEXT PRIMARY KEY,
                password_hash TEXT,
                password_salt TEXT,
                debe_cambiar_contrasena INTEGER DEFAULT 0
            )
        """))

        # Agregar columnas de seguridad a bases de datos existentes
        if DATABASE_URL:
            cursor.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS password_hash TEXT")
            cursor.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS password_salt TEXT")
            cursor.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS debe_cambiar_contrasena INTEGER DEFAULT 0")
        else:
            cols = [row[1] for row in cursor.execute("PRAGMA table_info(usuarios)").fetchall()]
            if "password_hash" not in cols:
                cursor.execute("ALTER TABLE usuarios ADD COLUMN password_hash TEXT")
            if "password_salt" not in cols:
                cursor.execute("ALTER TABLE usuarios ADD COLUMN password_salt TEXT")
            if "debe_cambiar_contrasena" not in cols:
                cursor.execute("ALTER TABLE usuarios ADD COLUMN debe_cambiar_contrasena INTEGER DEFAULT 0")

        # 1b. Crear tabla de auditoría con una clave válida en ambos motores
        bitacora_query = """
            CREATE TABLE IF NOT EXISTS bitacora (
                id SERIAL PRIMARY KEY,
                usuario TEXT,
                accion TEXT,
                detalle TEXT,
                ip TEXT,
                fecha TEXT
            )
        """
        if not DATABASE_URL:
            bitacora_query = bitacora_query.replace(
                "SERIAL PRIMARY KEY", "INTEGER PRIMARY KEY AUTOINCREMENT"
            )
        cursor.execute(fix_query(bitacora_query))

        # Reparar tablas de auditoría antiguas creadas como INTEGER en PostgreSQL
        if DATABASE_URL:
            cursor.execute("CREATE SEQUENCE IF NOT EXISTS bitacora_id_seq")
            cursor.execute(
                "ALTER TABLE bitacora ALTER COLUMN id "
                "SET DEFAULT NEXTVAL('bitacora_id_seq')"
            )
            cursor.execute(
                "SELECT setval('bitacora_id_seq', "
                "COALESCE((SELECT MAX(id) FROM bitacora), 0) + 1, false)"
            )
        
        # 2. Crear tabla de actividades personales
        cursor.execute(fix_query("CREATE TABLE IF NOT EXISTS actividades_personales (username TEXT, actividad TEXT, UNIQUE(username, actividad))"))
        
        # 3. Crear tabla de configuración de usuario
        cursor.execute(fix_query("CREATE TABLE IF NOT EXISTS configuracion_usuario (username TEXT, clave TEXT, valor TEXT, PRIMARY KEY (username, clave))"))
        
        # 4. Crear tabla de listas globales (ubicaciones, tipos, medios, actividades globales)
        cursor.execute(fix_query("CREATE TABLE IF NOT EXISTS listas_globales (tipo TEXT, valor TEXT, UNIQUE(tipo, valor))"))
        
        # 5. Crear tabla de registros
        query_registros = """
            CREATE TABLE IF NOT EXISTS registros (
                id SERIAL PRIMARY KEY,
                usuario TEXT, tipo_actividad TEXT, fecha TIMESTAMP, dependencia TEXT,
                solicitante TEXT, tipo_solicitud TEXT, medio_solicitud TEXT,
                descripcion TEXT, cumplido TEXT, fecha_atencion TEXT, observaciones TEXT,
                sync_uid TEXT, updated_at TEXT, borrado INTEGER DEFAULT 0
            )
        """
        # Adaptar SERIAL para SQLite
        if not DATABASE_URL:
            query_registros = query_registros.replace('SERIAL PRIMARY KEY', 'INTEGER PRIMARY KEY AUTOINCREMENT')
        
        cursor.execute(fix_query(query_registros))

        # Asegurar columnas de sincronización también en PostgreSQL
        if DATABASE_URL:
            cursor.execute("ALTER TABLE registros ADD COLUMN IF NOT EXISTS sync_uid TEXT")
            cursor.execute("ALTER TABLE registros ADD COLUMN IF NOT EXISTS updated_at TEXT")
            cursor.execute(
                "ALTER TABLE registros ADD COLUMN IF NOT EXISTS "
                "borrado INTEGER DEFAULT 0"
            )
            cursor.execute(
                "UPDATE registros SET updated_at = COALESCE(updated_at, fecha) "
                "WHERE updated_at IS NULL"
            )
            cursor.execute(
                "UPDATE registros SET borrado = 0 WHERE borrado IS NULL"
            )
        
        # 6. Asegurar usuario admin
        if DATABASE_URL:
            cursor.execute("INSERT INTO usuarios (username) VALUES (%s) ON CONFLICT DO NOTHING", ('admin',))
        else:
            cursor.execute("INSERT OR IGNORE INTO usuarios (username) VALUES (?)", ('admin',))
            
        # 7. Migración única desde JSON si la tabla está vacía
        cursor.execute("SELECT COUNT(*) as count FROM usuarios")
        count = cursor.fetchone()['count']
        if count <= 1 and os.path.exists(USERS_FILE):
             try:
                 logger.info(f"Iniciando migración desde {USERS_FILE}...")
                 with open(USERS_FILE, 'r', encoding='utf-8') as f:
                     data = json.load(f)
                 
                 # Migrar usuarios
                 for u in data.get("usuarios", []):
                     if u.lower() != 'admin':
                         if DATABASE_URL:
                             cursor.execute("INSERT INTO usuarios (username) VALUES (%s) ON CONFLICT DO NOTHING", (u,))
                         else:
                             cursor.execute("INSERT OR IGNORE INTO usuarios (username) VALUES (?)", (u,))
                 
                 # Migrar actividades personales
                 act_dict = data.get("actividades", {})
                 for user, acts in act_dict.items():
                     for act in acts:
                         if DATABASE_URL:
                             cursor.execute("INSERT INTO actividades_personales (username, actividad) VALUES (%s, %s) ON CONFLICT DO NOTHING", (user, act))
                         else:
                             cursor.execute("INSERT OR IGNORE INTO actividades_personales (username, actividad) VALUES (?, ?)", (user, act))
                 
                 # Migrar configuraciones (incluyendo datos_contrato)
                 conf_dict = data.get("configuraciones", {})
                 for user, conf in conf_dict.items():
                     for key, val in conf.items():
                         val_str = json.dumps(val, ensure_ascii=False)
                         if DATABASE_URL:
                             cursor.execute("INSERT INTO configuracion_usuario (username, clave, valor) VALUES (%s, %s, %s) ON CONFLICT (username, clave) DO UPDATE SET valor=EXCLUDED.valor", (user, key, val_str))
                         else:
                             cursor.execute("INSERT INTO configuracion_usuario (username, clave, valor) VALUES (?, ?, ?) ON CONFLICT(username, clave) DO UPDATE SET valor=excluded.valor", (user, key, val_str))
                 
                 logger.info("Migración desde JSON completada con éxito.")
             except Exception as me:
                 logger.error(f"Error durante la migración: {me}")
        
        # 8. Migración desde Excel si la tabla registros está vacía
        cursor.execute("SELECT COUNT(*) as count FROM registros")
        reg_count = cursor.fetchone()['count']
        if reg_count == 0 and os.path.exists(EXCEL_FILE):
            try:
                logger.info(f"Iniciando migración desde {EXCEL_FILE}...")
                # Leer excel, forzar string para evitar problemas de tipos
                df_excel = pd.read_excel(EXCEL_FILE, engine='openpyxl')
                
                # Mapeo inverso de columnas de Excel a SQL
                inv_col_map = {
                    "USUARIO": "usuario",
                    "TIPO DE ACTIVIDAD": "tipo_actividad",
                    "FECHA": "fecha",
                    "DEPENDENCIA": "dependencia",
                    "SOLICITANTE": "solicitante",
                    "TIPO DE SOLICITUD": "tipo_solicitud",
                    "MEDIO DE SOLICITUD": "medio_solicitud",
                    "DESCRIPCIÓN": "descripcion",
                    "CUMPLIDO": "cumplido",
                    "FECHA ATENCIÓN": "fecha_atencion",
                    "OBSERVACIONES": "observaciones"
                }
                
                for _, row in df_excel.iterrows():
                    vals = []
                    cols = []
                    for excel_col, sql_col in inv_col_map.items():
                        if excel_col in df_excel.columns:
                            val = row[excel_col]
                            # Manejar fechas de Pandas
                            if excel_col == "FECHA" and pd.notnull(val):
                                try:
                                    val = pd.to_datetime(val).strftime('%Y-%m-%d %H:%M:%S')
                                except:
                                    val = str(val)
                            else:
                                val = str(val) if pd.notnull(val) else ""
                            
                            vals.append(val)
                            cols.append(sql_col)
                    
                    if vals:
                        placeholders = ", ".join(["?"] * len(vals))
                        columnas_str = ", ".join(cols)
                        q = f"INSERT INTO registros ({columnas_str}) VALUES ({placeholders})"
                        cursor.execute(fix_query(q), tuple(vals))
                
                logger.info(f"Migración desde Excel completada. {len(df_excel)} registros importados.")
            except Exception as e_excel:
                logger.error(f"Error migrando Excel: {e_excel}")

        # Migrar columnas de sincronización (registros) para SQLite
        if not DATABASE_URL:
            try:
                _asegurar_columnas_sync(conn)
            except Exception as e_sync:
                logger.error(f"Error migrando columnas de sincronización: {e_sync}")

        conn.commit()
        conn.close()
        logger.info("Base de datos inicializada correctamente.")
    except Exception as e:
        logger.error(f"Error crítico inicializando base de datos: {e}")

def inicializar_tablas_postgres():
    """Stub para compatibilidad, redirige a inicializar_tablas"""
    inicializar_tablas()

# =============================================================================
# FUNCIONES DE INICIALIZACIÓN (Stub para compatibilidad)
# =============================================================================

@medir_tiempo
def inicializar_usuarios():
    """Punto de entrada para inicialización desde app_web.py."""
    # PostgreSQL es la fuente de verdad en web; no intentar sincronizar archivos de red.
    if not DATABASE_URL:
        try:
            sincronizar_red_a_local()
        except Exception as e:
            logger.warning(f"[INIT] No se pudo sincronizar desde red: {e}")
    
    inicializar_tablas()
    clear_cache()

def inicializar_config():
    pass

def inicializar_excel():
    pass

# =============================================================================
# CARGA DE USUARIOS
# =============================================================================

@cache_decorator
@medir_tiempo
def cargar_usuarios():
    """Carga usuarios y sus configuraciones/actividades desde SQLite"""
    try:
        conn = get_db_connection()
        cursor = get_cursor(conn)
        
        # Cargar usuarios
        cursor.execute("SELECT username FROM usuarios")
        usuarios = [row['username'] for row in cursor.fetchall()]
        
        # Cargar actividades personales
        actividades = {}
        cursor.execute("SELECT username, actividad FROM actividades_personales")
        for row in cursor.fetchall():
            user = row['username']
            if user not in actividades:
                actividades[user] = []
            actividades[user].append(row['actividad'])
            
        # Cargar configuraciones
        configuraciones = {}
        cursor.execute("SELECT username, clave, valor FROM configuracion_usuario")
        for row in cursor.fetchall():
            user = row['username']
            if user not in configuraciones:
                configuraciones[user] = {}
            try:
                configuraciones[user][row['clave']] = json.loads(row['valor'])
            except:
                 configuraciones[user][row['clave']] = row['valor']

        conn.close()
        
        return {
            "usuarios": usuarios if usuarios else ["admin"],
            "actividades": actividades,
            "configuraciones": configuraciones
        }
    except Exception as e:
        logger.error(f"Error cargando usuarios SQL: {e}")
        return {"usuarios": ["admin"]}

@medir_tiempo
def guardar_usuarios(data):
    """
    Sincroniza la lista de usuarios en la base de datos con la lista proporcionada.
    Agrega usuarios nuevos y elimina los que ya no están en la lista (excepto admin).
    """
    try:
        conn = get_db_connection()
        cursor = get_cursor(conn)
        
        new_users_set = set(data.get("usuarios", []))
        if "admin" not in new_users_set:
            new_users_set.add("admin") # Asegurar admin

        # 1. Obtener usuarios actuales en DB
        cursor.execute("SELECT username FROM usuarios")
        current_db_users = set(row['username'] for row in cursor.fetchall())

        # 2. Identificar a agregar y eliminar
        to_add = new_users_set - current_db_users
        to_remove = current_db_users - new_users_set

        # 3. Eliminar
        for user in to_remove:
            if user != 'admin': # Seguridad extra
                # Eliminar datos asociados para evitar huérfanos
                cursor.execute(fix_query("DELETE FROM actividades_personales WHERE username = ?"), (user,))
                cursor.execute(fix_query("DELETE FROM configuracion_usuario WHERE username = ?"), (user,))
                cursor.execute(fix_query("DELETE FROM usuarios WHERE username = ?"), (user,))

        # 4. Agregar
        for user in to_add:
            if DATABASE_URL:
                # Postgres: ON CONFLICT
                cursor.execute("INSERT INTO usuarios (username) VALUES (%s) ON CONFLICT DO NOTHING", (user,))
            else:
                # SQLite
                cursor.execute("INSERT OR IGNORE INTO usuarios (username) VALUES (?)", (user,))
        
        conn.commit()
        conn.close()
        clear_cache()
        sincronizar_db_a_master()
        return True
    except Exception as e:
        logger.error(f"Error sincronizando usuarios SQL: {e}")
        return False


# =============================================================================
# AUTENTICACIÓN Y AUDITORÍA
# =============================================================================

_PBKDF2_ITER = 260_000


def _hash_contrasena(contrasena, salt=None):
    """Genera un hash PBKDF2-SHA256 y su sal aleatoria."""
    if salt is None:
        salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        contrasena.encode("utf-8"),
        bytes.fromhex(salt),
        _PBKDF2_ITER,
    ).hex()
    return digest, salt


def _verificar_contrasena(contrasena, hash_guardado, salt):
    """Verifica una contraseña sin comparar valores de forma vulnerable a timing."""
    if not hash_guardado or not salt:
        return False
    candidate, _ = _hash_contrasena(contrasena, salt)
    return hmac.compare_digest(candidate, hash_guardado)


def verificar_credenciales(usuario, contrasena):
    """Valida usuario y contraseña.

    Devuelve ``(True, info)`` o ``(False, motivo)``. Los usuarios sin
    contraseña configurada no pueden acceder a la aplicación web.
    """
    try:
        conn = get_db_connection()
        try:
            cursor = get_cursor(conn)
            cursor.execute(
                fix_query(
                    "SELECT username, password_hash, password_salt, "
                    "debe_cambiar_contrasena FROM usuarios WHERE username = ?"
                ),
                (usuario,),
            )
            row = cursor.fetchone()
        finally:
            conn.close()

        if not row:
            return False, "usuario_inexistente"
        if not row["password_hash"]:
            return False, "sin_contrasena"
        if not _verificar_contrasena(
            contrasena, row["password_hash"], row["password_salt"]
        ):
            return False, "clave_incorrecta"

        return True, {
            "username": row["username"],
            "debe_cambiar": bool(row["debe_cambiar_contrasena"]),
        }
    except Exception:
        logger.exception("Error verificando credenciales")
        return False, "error"


def establecer_contrasena(usuario, contrasena, limpiar_debe_cambiar=True):
    """Establece o cambia la contraseña de un usuario."""
    if not contrasena or len(contrasena) < 6:
        return False, "La contraseña debe tener al menos 6 caracteres"

    try:
        password_hash, password_salt = _hash_contrasena(contrasena)
        with db_session() as conn:
            cursor = get_cursor(conn)
            cursor.execute(
                fix_query(
                    "UPDATE usuarios SET password_hash = ?, password_salt = ?, "
                    "debe_cambiar_contrasena = ? WHERE username = ?"
                ),
                (
                    password_hash,
                    password_salt,
                    0 if limpiar_debe_cambiar else 1,
                    usuario,
                ),
            )
            if cursor.rowcount == 0:
                return False, "El usuario no existe"
        clear_cache()
        return True, "Contraseña actualizada correctamente"
    except Exception:
        logger.exception("Error estableciendo contraseña")
        return False, "Error al actualizar la contraseña"


def marcar_debe_cambiar_contrasena(usuario, debe_cambiar=True):
    """Marca o desmarca el cambio de contraseña para el próximo ingreso."""
    try:
        with db_session() as conn:
            cursor = get_cursor(conn)
            cursor.execute(
                fix_query(
                    "UPDATE usuarios SET debe_cambiar_contrasena = ? "
                    "WHERE username = ?"
                ),
                (1 if debe_cambiar else 0, usuario),
            )
        clear_cache()
        return True
    except Exception:
        logger.exception("Error marcando cambio de contraseña")
        return False


def usuario_debe_cambiar_contrasena(usuario):
    """Indica si el usuario debe cambiar su contraseña en el próximo ingreso."""
    try:
        conn = get_db_connection()
        try:
            cursor = get_cursor(conn)
            cursor.execute(
                fix_query(
                    "SELECT debe_cambiar_contrasena FROM usuarios "
                    "WHERE username = ?"
                ),
                (usuario,),
            )
            row = cursor.fetchone()
        finally:
            conn.close()
        return bool(row and row["debe_cambiar_contrasena"])
    except Exception:
        logger.exception("Error consultando cambio de contraseña")
        return False


def usuario_tiene_contrasena(usuario):
    """Indica si el usuario ya configuró una contraseña."""
    try:
        conn = get_db_connection()
        try:
            cursor = get_cursor(conn)
            cursor.execute(
                fix_query("SELECT password_hash FROM usuarios WHERE username = ?"),
                (usuario,),
            )
            row = cursor.fetchone()
        finally:
            conn.close()
        return bool(row and row["password_hash"])
    except Exception:
        logger.exception("Error consultando contraseña configurada")
        return False


def registrar_auditoria(usuario, accion, detalle="", ip=""):
    """Registra una acción sin impedir la operación principal si falla."""
    try:
        with db_session() as conn:
            cursor = get_cursor(conn)
            cursor.execute(
                fix_query(
                    "INSERT INTO bitacora (usuario, accion, detalle, ip, fecha) "
                    "VALUES (?, ?, ?, ?, ?)"
                ),
                (
                    usuario,
                    accion,
                    str(detalle)[:1000],
                    ip or "",
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                ),
            )
    except Exception:
        logger.exception("Error registrando auditoría")


def obtener_bitacora(limite=500):
    """Devuelve los eventos de auditoría más recientes."""
    try:
        conn = get_db_connection()
        try:
            cursor = get_cursor(conn)
            cursor.execute(
                fix_query(
                    "SELECT id, usuario, accion, detalle, ip, fecha "
                    "FROM bitacora ORDER BY id DESC LIMIT ?"
                ),
                (limite,),
            )
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()
    except Exception:
        logger.exception("Error obteniendo bitácora")
        return []


def limpiar_bitacora():
    """Elimina todos los registros de auditoría."""
    try:
        with db_session() as conn:
            cursor = get_cursor(conn)
            cursor.execute(fix_query("DELETE FROM bitacora"))
        return True
    except Exception:
        logger.exception("Error limpiando bitácora")
        return False


def obtener_ultimo_acceso(usuario):
    """Devuelve la fecha del último acceso registrado de un usuario."""
    try:
        conn = get_db_connection()
        try:
            cursor = get_cursor(conn)
            cursor.execute(
                fix_query(
                    "SELECT MAX(fecha) as f FROM bitacora "
                    "WHERE usuario = ? AND accion = 'LOGIN'"
                ),
                (usuario,),
            )
            row = cursor.fetchone()
        finally:
            conn.close()
        return row["f"] if row else None
    except Exception:
        logger.exception("Error obteniendo último acceso")
        return None


@medir_tiempo
def obtener_configuracion_usuario(usuario):
    """Obtiene la configuración personalizada de un usuario"""
    try:
        conn = get_db_connection()
        cursor = get_cursor(conn)
        # En el modelo actual, guardamos claves individuales.
        # Pero por compatibilidad, la función espera un dict completo de config.
        # Vamos a reconstruirlo.
        
        # Default config
        config = {
            "tema": "claro",
            "columnas_visibles": ["TIPO DE ACTIVIDAD", "FECHA", "DEPENDENCIA", "SOLICITANTE", "DESCRIPCIÓN", "CUMPLIDO"],
            "orden_por": "FECHA",
            "orden_direccion": "desc",
            "datos_contrato": {"objeto": "", "nro": "", "nombre": "", "cedula": "", "supervisor": ""}
        }

        cursor.execute(fix_query("SELECT clave, valor FROM configuracion_usuario WHERE username = ?"), (usuario,))
        rows = cursor.fetchall()
        for row in rows:
            try:
                config[row['clave']] = json.loads(row['valor'])
            except:
                pass
                
        conn.close()
        try:
            dc = config.get("datos_contrato", {}) or {}
            keys = ['objeto','nro','nombre','cedula','supervisor']
            if not any(dc.get(k) for k in keys):
                candidates = []
                for d in DIRS_SEARCH:
                    p = os.path.join(d, "usuarios.json")
                    if os.path.exists(p):
                        candidates.append(p)
                candidates.insert(0, USERS_FILE)
                seen = []
                uniq = [x for x in candidates if not (x in seen or seen.append(x))]
                found = None
                found_user = usuario
                for p in uniq:
                    try:
                        with open(p, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        for who in [usuario, 'admin']:
                            user_cfg = data.get('configuraciones', {}).get(who, {})
                            dc2 = user_cfg.get('datos_contrato')
                            if isinstance(dc2, dict) and any(dc2.get(k) for k in keys):
                                found = dc2
                                found_user = who
                                break
                        if found:
                            break
                    except Exception:
                        continue
                if isinstance(found, dict):
                    config['datos_contrato'] = found
                    try:
                        conn2 = get_db_connection()
                        cur2 = get_cursor(conn2)
                        val_str = json.dumps(found, ensure_ascii=False)
                        q = fix_query('''
                            INSERT INTO configuracion_usuario (username, clave, valor)
                            VALUES (?, ?, ?)
                            ON CONFLICT(username, clave) DO UPDATE SET valor=excluded.valor
                        ''')
                        cur2.execute(q, (usuario, 'datos_contrato', val_str))
                        conn2.commit()
                        conn2.close()
                    except Exception:
                        pass
        except Exception:
            pass
        return config
    except Exception as e:
        logger.error(f"Error obteniendo config usuario {usuario}: {e}")
        return {}

@medir_tiempo
def guardar_configuracion_usuario(usuario, config):
    """Guarda la configuración personalizada"""
    try:
        conn = get_db_connection()
        cursor = get_cursor(conn)
        
        for key, value in config.items():
            val_str = json.dumps(value, ensure_ascii=False)
            query = '''
                INSERT INTO configuracion_usuario (username, clave, valor) 
                VALUES (?, ?, ?)
                ON CONFLICT(username, clave) DO UPDATE SET valor=excluded.valor
            '''
            query = fix_query(query)
            cursor.execute(query, (usuario, key, val_str))
            
        conn.commit()
        conn.close()
        clear_cache()
        sincronizar_db_a_master()
        return True
    except Exception as e:
        logger.error(f"Error guardando config usuario {usuario}: {e}")
        return False

# =============================================================================
# GESTIÓN DIRECTA DE ACTIVIDADES PERSONALES (SQL)
# =============================================================================

def agregar_actividad_personal_db(usuario, actividad):
    """Agrega una actividad personal verificando duplicados"""
    try:
        conn = get_db_connection()
        cursor = get_cursor(conn)
        
        # Verificar si ya existe
        cursor.execute(fix_query("SELECT 1 FROM actividades_personales WHERE username = ? AND actividad = ?"), (usuario, actividad))
        if cursor.fetchone():
            conn.close()
            return False # Ya existe
            
        cursor.execute(fix_query("INSERT INTO actividades_personales (username, actividad) VALUES (?, ?)"), (usuario, actividad))
        conn.commit()
        conn.close()
        clear_cache()
        sincronizar_db_a_master()
        return True
    except Exception as e:
        logger.error(f"Error agregando actividad personal DB: {e}")
        return False

def eliminar_actividad_personal_db(usuario, actividad):
    try:
        conn = get_db_connection()
        cursor = get_cursor(conn)
        cursor.execute(fix_query("DELETE FROM actividades_personales WHERE username = ? AND actividad = ?"), (usuario, actividad))
        conn.commit()
        conn.close()
        clear_cache()
        sincronizar_db_a_master()
        return True
    except Exception as e:
        logger.error(f"Error eliminando actividad personal DB: {e}")
        return False

# =============================================================================
# CARGA DE CONFIGURACIÓN (Listas de opciones)
# =============================================================================

def _cargar_lista_global(tipo, default):
    try:
        with db_session() as conn:
            cursor = get_cursor(conn)
            cursor.execute(fix_query("SELECT valor FROM listas_globales WHERE tipo = ?"), (tipo,))
            rows = cursor.fetchall()
            return [row['valor'] for row in rows] if rows else default
    except Exception as e:
        logger.error(f"Error cargando lista {tipo}: {e}")
        return default

def _guardar_lista_global(tipo, lista):
    try:
        with db_session() as conn:
            cursor = get_cursor(conn)
            cursor.execute(fix_query("DELETE FROM listas_globales WHERE tipo = ?"), (tipo,))
            for val in lista:
                cursor.execute(fix_query("INSERT OR IGNORE INTO listas_globales (tipo, valor) VALUES (?, ?)"), (tipo, val))
        clear_cache()
        sincronizar_db_a_master()
        return True
    except Exception as e:
        logger.error(f"Error guardando lista {tipo}: {e}")
        return False

@cache_decorator
@medir_tiempo
def cargar_actividades_globales():
    return _cargar_lista_global('actividad', ACTIVIDADES_DEFAULT)

@cache_decorator
@medir_tiempo
def cargar_actividades(usuario=None):
    """
    Carga actividades disponibles.
    Solo retorna actividades personales del usuario.
    """
    try:
        personales = []
        
        # Si hay un usuario específico, cargar sus actividades personales
        if usuario:
            conn = get_db_connection()
            cursor = get_cursor(conn)
            cursor.execute(fix_query("SELECT actividad FROM actividades_personales WHERE username = ?"), (usuario,))
            personales = [row['actividad'] for row in cursor.fetchall()]
            conn.close()
            
        return sorted(list(set(personales)))
    except Exception as e:
        logger.error(f"Error cargando actividades para {usuario}: {e}")
        return []

@cache_decorator
@medir_tiempo
def cargar_ubicaciones():
    return _cargar_lista_global('ubicacion', UBICACIONES_DEFAULT)

@cache_decorator
@medir_tiempo
def cargar_tipos_solicitud():
    return _cargar_lista_global('tipo_solicitud', TIPOS_SOLICITUD_DEFAULT)

@cache_decorator
@medir_tiempo
def cargar_medios_solicitud():
    return _cargar_lista_global('medio_solicitud', MEDIOS_SOLICITUD_DEFAULT)

@medir_tiempo
def guardar_actividades(actividades):
    return _guardar_lista_global('actividad', actividades)

@medir_tiempo
def guardar_ubicaciones(ubicaciones):
    return _guardar_lista_global('ubicacion', ubicaciones)

@medir_tiempo
def guardar_tipos_solicitud(tipos):
    return _guardar_lista_global('tipo_solicitud', tipos)

@medir_tiempo
def guardar_medios_solicitud(medios):
    return _guardar_lista_global('medio_solicitud', medios)

# =============================================================================
# CRUD DE REGISTROS
# =============================================================================

# =============================================================================
# SINCRONIZACIÓN LOCAL <-> RED
# =============================================================================
# Sincronización POR REGISTRO y POR USUARIO:
# - Crea los registros que faltan, actualiza los editados y propaga los
#   borrados (última escritura gana por updated_at).
# - Cada registro tiene un sync_uid único y estable entre BDs (los datos
#   existentes reciben un UID determinístico según su contenido).
# - Así los datos de un equipo que estuvo sin red se conservan y se unen a la
#   base central sin perder ni duplicar registros.

_TABLAS_CON_CLAVE_UNICA = [
    "usuarios",
    "actividades_personales",
    "configuracion_usuario",
    "listas_globales",
]

_COLUMNAS_REGISTRO = [
    "usuario", "tipo_actividad", "fecha", "dependencia", "solicitante",
    "tipo_solicitud", "medio_solicitud", "descripcion", "cumplido",
    "fecha_atencion", "observaciones",
]

_SYNC_COLUMNS = _COLUMNAS_REGISTRO + ["sync_uid", "updated_at", "borrado"]

def _ahora():
    """Timestamp ISO con microsegundos para resolver conflictos de sincronización."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")

def _sval(v):
    """Convierte un valor (incluido NaN/None/Timestamp) a texto seguro."""
    if v is None:
        return ""
    try:
        if pd.isna(v):
            return ""
    except Exception:
        pass
    if hasattr(v, "strftime"):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    return str(v)

def _legacy_uid(vals):
    """UID determinístico basado en el contenido: mismo registro = mismo UID en cualquier BD."""
    h = hashlib.sha1("|".join(_sval(v).strip() for v in vals).encode("utf-8")).hexdigest()[:16]
    return "legacy_" + h

def _asegurar_columnas_sync(conn):
    """Agrega las columnas de sincronización a 'registros' si faltan y rellena las filas existentes."""
    try:
        cur = conn.execute("PRAGMA table_info(registros)")
        cols = {r[1] for r in cur.fetchall()}
        if "sync_uid" not in cols:
            conn.execute("ALTER TABLE registros ADD COLUMN sync_uid TEXT")
        if "updated_at" not in cols:
            conn.execute("ALTER TABLE registros ADD COLUMN updated_at TEXT")
        if "borrado" not in cols:
            conn.execute("ALTER TABLE registros ADD COLUMN borrado INTEGER DEFAULT 0")
        # Asignar UID a filas legacy a partir de su contenido (determinístico entre BDs)
        sel = ", ".join(_COLUMNAS_REGISTRO)
        filas_legacy = conn.execute("SELECT id, %s FROM registros WHERE sync_uid IS NULL OR sync_uid = ''" % sel).fetchall()
        if filas_legacy:
            conn.executemany(
                "UPDATE registros SET sync_uid = ? WHERE id = ?",
                [(_legacy_uid(f[1:]), f[0]) for f in filas_legacy],
            )
        conn.execute("UPDATE registros SET updated_at = COALESCE(updated_at, fecha, datetime('now')) WHERE updated_at IS NULL OR updated_at = ''")
        conn.commit()
    except Exception as e:
        logger.warning(f"[SYNC] No se pudieron asegurar columnas de sincronización: {e}")

def _clave_registro(fila):
    """Clave natural de un registro (ignora id/sync_uid): sirve para detectar duplicados por contenido."""
    return tuple(_sval(v).strip().lower() for v in fila)

def _insertar_fila_sync(conn, r):
    """Inserta una fila completa de registros en la BD destino."""
    values = tuple(_sval(getattr(r, c)) for c in _COLUMNAS_REGISTRO)
    conn.execute(
        "INSERT INTO registros (%s, sync_uid, updated_at, borrado) VALUES (%s)" % (
            ", ".join(_COLUMNAS_REGISTRO),
            ", ".join(["?"] * (len(_COLUMNAS_REGISTRO) + 3)),
        ),
        values + (_sval(getattr(r, "sync_uid", "")), _sval(getattr(r, "updated_at", "")), _borrado_val(getattr(r, "borrado", 0))),
    )

def _actualizar_fila_sync(conn, r):
    """Actualiza la fila en la BD destino con los datos de la fila origen."""
    set_cols = ", ".join(c + " = ?" for c in _COLUMNAS_REGISTRO)
    values = tuple(_sval(getattr(r, c)) for c in _COLUMNAS_REGISTRO)
    conn.execute(
        "UPDATE registros SET %s, sync_uid = ?, updated_at = ?, borrado = ? WHERE sync_uid = ?" % set_cols,
        values + (_sval(getattr(r, "sync_uid", "")), _sval(getattr(r, "updated_at", "")), _borrado_val(getattr(r, "borrado", 0)), _sval(getattr(r, "sync_uid", ""))),
    )

def _borrado_val(v):
    return 1 if _sval(v) in ("1", "True", "true") else 0

def _merge_registros_una_via(src_df, dst_df, dst_conn):
    """
    Propaga a la BD destino los registros de origen que faltan o están más
    actualizados (por updated_at). Los borrados se propagan como tombstones.
    """
    cambios = 0
    por_uid_src = {}
    por_uid_dst = {}
    for r in src_df.itertuples(index=False):
        uid = _sval(getattr(r, "sync_uid", ""))
        if uid:
            por_uid_src[uid] = r
    for r in dst_df.itertuples(index=False):
        uid = _sval(getattr(r, "sync_uid", ""))
        if uid:
            por_uid_dst[uid] = r

    claves_dst = set(_clave_registro(_sval(getattr(r, c)) for c in _COLUMNAS_REGISTRO) for r in por_uid_dst.values())

    for uid, ro in por_uid_src.items():
        rd = por_uid_dst.get(uid)
        if rd is None:
            # No existe en destino: insertar, salvo que ya haya una fila con el mismo contenido
            clave_o = _clave_registro(_sval(getattr(ro, c)) for c in _COLUMNAS_REGISTRO)
            if clave_o in claves_dst:
                continue
            _insertar_fila_sync(dst_conn, ro)
            cambios += 1
        else:
            ts_o = _sval(ro.updated_at)
            ts_d = _sval(rd.updated_at)
            if ts_o > ts_d:
                _actualizar_fila_sync(dst_conn, ro)
                cambios += 1
    return cambios

def _sincronizar_registros(origen, destino):
    """
    Sincroniza la tabla 'registros' entre dos BDs: crea los que faltan,
    actualiza los editados y propaga los borrados (última escritura gana).
    """
    if _mismo_archivo(origen, destino) or not os.path.exists(origen) or not os.path.exists(destino):
        return 0
    try:
        con_o = sqlite3.connect(origen, timeout=60)
        con_d = sqlite3.connect(destino, timeout=60)
        _asegurar_columnas_sync(con_o)
        _asegurar_columnas_sync(con_d)
        sel = ", ".join(_SYNC_COLUMNS)
        df_o = pd.read_sql_query("SELECT %s FROM registros" % sel, con_o)
        df_d = pd.read_sql_query("SELECT %s FROM registros" % sel, con_d)
        n = _merge_registros_una_via(df_o, df_d, con_d)
        con_d.commit()
        con_o.close()
        con_d.close()
        if n:
            logger.info(f"[SYNC] Registros sincronizados: {n} cambio(s) ({os.path.basename(origen)} -> {os.path.basename(destino)})")
        return n
    except Exception as e:
        logger.warning(f"[SYNC] No se pudieron sincronizar registros: {e}")
        return 0

def _mismo_archivo(a, b):
    try:
        return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))
    except Exception:
        return False

def _intentar_copiar(origen, destino, descripcion, max_intentos=3):
    """Copia un archivo con reintentos y logging detallado"""
    if not os.path.exists(origen):
        logger.warning(f"[SYNC] No se puede sincronizar '{descripcion}': origen no existe ({origen})")
        return False
    # Si origen y destino son el mismo archivo (BD central en red), omitir
    if _mismo_archivo(origen, destino):
        logger.info(f"[SYNC] {descripcion}: mismo archivo, se omite copia")
        return True
    for intento in range(1, max_intentos + 1):
        try:
            os.makedirs(os.path.dirname(destino), exist_ok=True)
            shutil.copy2(origen, destino)
            logger.info(f"[SYNC] {descripcion} sincronizado: {origen} -> {destino}")
            return True
        except (PermissionError, OSError) as e:
            if intento < max_intentos:
                espera = 0.5 * intento
                logger.warning(f"[SYNC] Reintento {intento}/{max_intentos} copiando {descripcion}: {e}")
                time.sleep(espera)
            else:
                logger.error(f"[SYNC] Error copiando {descripcion} después de {max_intentos} intentos: {e}")
        except Exception as e:
            logger.error(f"[SYNC] Error inesperado copiando {descripcion}: {e}")
            break
    return False

def _fusionar_tabla(origen, destino, tabla):
    """Agrega filas nuevas usando únicamente columnas compatibles entre ambas bases."""
    if _mismo_archivo(origen, destino) or not os.path.exists(origen) or not os.path.exists(destino):
        return 0
    try:
        con = sqlite3.connect(destino, timeout=60)
        con.execute("ATTACH DATABASE ? AS src", (origen,))
        dest_cols = [
            row[1] for row in con.execute(f'PRAGMA table_info("{tabla}")').fetchall()
        ]
        src_cols = {
            row[1]
            for row in con.execute(f'PRAGMA src.table_info("{tabla}")').fetchall()
        }
        common_cols = [col for col in dest_cols if col in src_cols]
        if not common_cols:
            con.execute("DETACH DATABASE src")
            con.close()
            return 0

        columns_sql = ", ".join(f'"{col}"' for col in common_cols)
        cur = con.execute(
            f'INSERT OR IGNORE INTO "{tabla}" ({columns_sql}) '
            f'SELECT {columns_sql} FROM src."{tabla}"'
        )
        con.commit()
        n = cur.rowcount
        con.execute("DETACH DATABASE src")
        con.close()
        if n:
            logger.info(f"[SYNC] Fusión {tabla}: {n} fila(s) nuevas ({os.path.basename(origen)} -> {os.path.basename(destino)})")
        return n or 0
    except Exception as e:
        logger.warning(f"[SYNC] No se pudo fusionar tabla '{tabla}': {e}")
        return 0

def _sincronizar_bidireccional(ruta_local, ruta_red):
    """Fusiona tablas y registros en ambos sentidos (crea, actualiza y propaga borrados)."""
    total = 0
    # Red -> Local
    for tabla in _TABLAS_CON_CLAVE_UNICA:
        total += _fusionar_tabla(ruta_red, ruta_local, tabla)
    total += _sincronizar_registros(ruta_red, ruta_local)
    # Local -> Red
    for tabla in _TABLAS_CON_CLAVE_UNICA:
        total += _fusionar_tabla(ruta_local, ruta_red, tabla)
    total += _sincronizar_registros(ruta_local, ruta_red)
    return total

def _buscar_bd_local_offline():
    """
    Busca una BD local que pudo quedar con datos mientras el equipo estuvo sin red.
    Puede estar en LOCALAPPDATA + ActividadesData (fallback de config) o junto al exe.
    """
    candidatos = []
    alt = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
    candidatos.append(os.path.join(alt, "ActividadesData", "actividades.db"))
    try:
        from config import EXE_DIR
        if EXE_DIR:
            candidatos.append(os.path.join(EXE_DIR, "actividades.db"))
    except Exception:
        pass
    resultado = []
    for c in candidatos:
        if os.path.exists(c):
            resultado.append(c)
    return resultado

@retry_operation(max_retries=3, base_delay=0.5)
def sincronizar_red_a_local():
    """
    Sincroniza datos al abrir la aplicación:
    1. Fusiona con la red cualquier BD local que haya quedado con datos sin conexión.
    2. Copia la BD y Excel desde la red (MASTER_DIR) al directorio local.
    Se ejecuta al iniciar la aplicación.
    """
    if DATABASE_URL or not MASTER_DIR or not os.path.exists(MASTER_DIR):
        return False
    
    red_db = os.path.join(MASTER_DIR, "actividades.db")
    exito = False
    
    # 1. Fusionar BD locales que quedaron con datos (equipo estuvo sin red)
    for local_db in _buscar_bd_local_offline():
        if not _mismo_archivo(local_db, red_db) and not _mismo_archivo(local_db, DB_FILE):
            n = _sincronizar_bidireccional(local_db, red_db)
            if n:
                exito = True
                logger.info(f"[SYNC] Datos sin conexión fusionados con la red: {n} elemento(s) desde {local_db}")
    
    # 2. Fusionar la BD local activa con la red (si son archivos distintos)
    if not _mismo_archivo(DB_FILE, red_db):
        n = _sincronizar_bidireccional(DB_FILE, red_db)
        if n:
            exito = True
    
    # 3. Copiar Excel de red -> local (solo si no es el mismo archivo)
    red_xlsx = os.path.join(MASTER_DIR, "actividades.xlsx")
    if os.path.exists(red_xlsx) and not _mismo_archivo(red_xlsx, EXCEL_FILE):
        if _intentar_copiar(red_xlsx, EXCEL_FILE, "Excel (red -> local)"):
            exito = True
    
    if exito:
        logger.info("[SYNC] Sincronización de apertura completada")
    return exito

@retry_operation(max_retries=3, base_delay=0.5)
def sincronizar_db_a_master():
    """
    Sincroniza después de cada escritura:
    Fusiona la BD local con la central de red (por registro/usuario, sin sobrescribir).
    """
    if DATABASE_URL or not MASTER_DIR or not os.path.exists(MASTER_DIR):
        return False
    
    red_db = os.path.join(MASTER_DIR, "actividades.db")
    if not os.path.exists(red_db):
        logger.warning("[SYNC] No existe la BD central en red, los datos quedan en local")
        return False
    
    # Si la BD activa ES la central (modo normal), no hay nada que fusionar
    if _mismo_archivo(DB_FILE, red_db):
        return True
    
    n = _sincronizar_bidireccional(DB_FILE, red_db)
    exito_xlsx = _intentar_copiar(EXCEL_FILE, os.path.join(MASTER_DIR, "actividades.xlsx"), "Excel (local -> red)")
    
    if n or exito_xlsx:
        logger.info("[SYNC] Sincronización por registros completada")
    return True

def sincronizar_excel():
    """Exporta todos los registros de la BD al archivo Excel local."""
    # En PostgreSQL el Excel es un formato de salida, no una fuente de verdad.
    if DATABASE_URL:
        return True

    try:
        df = cargar_registros()
        df_export = df.drop(columns=['ID']) if 'ID' in df.columns else df
        cols_final = [c for c in COLUMNAS if c != 'ID']
        df_export = df_export[cols_final]
        
        intentos = 3
        exito = False
        while intentos > 0:
            try:
                os.makedirs(os.path.dirname(EXCEL_FILE), exist_ok=True)
                df_export.to_excel(EXCEL_FILE, index=False, engine='openpyxl')
                logger.info(f"Excel exportado local: {EXCEL_FILE}")
                exito = True
                break
            except PermissionError:
                intentos -= 1
                if intentos == 0:
                    logger.warning(f"No se pudo exportar Excel {EXCEL_FILE}: archivo abierto.")
                time.sleep(0.5)
            except Exception as ex:
                logger.error(f"Error exportando Excel: {ex}")
                break
        
        # Sync a red (no crítico, no debe impedir la operación principal)
        try:
            sincronizar_db_a_master()
        except Exception:
            pass
        
        return exito
    except Exception as e:
        logger.error(f"Error en sincronizar_excel: {e}")
        return False

def importar_desde_excel(file_path=None):
    """Importa y combina registros desde un archivo Excel externo (Maestro)"""
    if not file_path:
        file_path = EXCEL_FILE
        
    if not os.path.exists(file_path):
        logger.warning(f"[WARNING] No se puede importar: {file_path} no existe.")
        return 0
        
    try:
        logger.info(f"[RELOAD] Iniciando sincronización desde: {file_path}")
        df = pd.read_excel(file_path, engine='openpyxl')
        
        # Limpieza y Mapeo Flexible de Columnas
        df.columns = [c.upper().strip() for c in df.columns]
        mapeo = {
            'ACTIVIDAD': 'TIPO DE ACTIVIDAD',
            'TIPO ACTIVIDAD': 'TIPO DE ACTIVIDAD',
            'UBICACION': 'DEPENDENCIA',
            'LUGAR': 'DEPENDENCIA',
            'SOLICITANTE': 'SOLICITANTE',
            'MEDIO': 'MEDIO DE SOLICITUD'
        }
        df = df.rename(columns=mapeo)
        
        # Asegurar columnas esperadas
        for col in COLUMNAS:
            if col not in df.columns:
                df[col] = ""
                
        count = 0
        with db_session() as conn:
            cursor = get_cursor(conn)
            for _, row in df.iterrows():
                try:
                    fecha = str(row.get('FECHA', ''))
                    fecha_atencion = str(row.get('FECHA ATENCIÓN', ''))
                    values = (
                        str(row.get('USUARIO', 'admin')),
                        str(row.get('TIPO DE ACTIVIDAD', '')),
                        fecha,
                        str(row.get('DEPENDENCIA', '')),
                        str(row.get('SOLICITANTE', '')),
                        str(row.get('TIPO DE SOLICITUD', '')),
                        str(row.get('MEDIO DE SOLICITUD', '')),
                        str(row.get('DESCRIPCIÓN', '')),
                        str(row.get('CUMPLIDO', '')),
                        fecha_atencion,
                        str(row.get('OBSERVACIONES', ''))
                    )
                    
                    # Comprobación de duplicado por clave de negocio
                    cursor.execute(fix_query('''
                        SELECT 1 FROM registros 
                        WHERE usuario=? AND tipo_actividad=? AND fecha=? AND descripcion=? 
                        LIMIT 1
                    '''), (values[0], values[1], values[2], values[7]))
                    
                    if cursor.fetchone():
                        continue
                        
                    cursor.execute(fix_query('''
                        INSERT INTO registros (
                            usuario, tipo_actividad, fecha, dependencia, solicitante,
                            tipo_solicitud, medio_solicitud, descripcion, cumplido,
                            fecha_atencion, observaciones, sync_uid, updated_at, borrado
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    '''), values + (uuid.uuid4().hex, _ahora(), 0))
                    count += 1
                except Exception as e:
                    logger.error(f"Error importando fila: {e}")
                    
        if count > 0:
            logger.info(f"✅ Sincronización completada: Agregados {count} registros nuevos.")
            clear_cache()
        return count
    except Exception as e:
        logger.error(f"[ERROR] Error crítico importando desde Excel: {e}")
        return 0

@retry_operation(max_retries=3)
@medir_tiempo
def cargar_registros(usuario=None):
    try:
        conn = get_db_connection()
        filtro = []
        params = []
        
        # Ocultar registros eliminados lógicamente
        if DATABASE_URL:
            filtro.append("COALESCE(borrado, 0) = 0")
        else:
            try:
                cur = conn.execute("PRAGMA table_info(registros)")
                cols = {r[1] for r in cur.fetchall()}
                if "borrado" in cols:
                    filtro.append("COALESCE(borrado, 0) = 0")
            except Exception:
                pass
        
        # v6.9: Filtro estricto por usuario para la tabla principal
        if usuario:
            filtro.append("usuario = ?")
            params.append(usuario)
            
        query = "SELECT * FROM registros"
        if filtro:
            query += " WHERE " + " AND ".join(filtro)
            
        if DATABASE_URL:
            query = query.replace('?', '%s')
            
        df = pd.read_sql_query(query, conn, params=params)
        conn.close()
        
        # Mapeo de columnas SQL a nombres de Excel para compatibilidad
        col_map = {
            "id": "ID",
            "usuario": "USUARIO",
            "tipo_actividad": "TIPO DE ACTIVIDAD",
            "fecha": "FECHA",
            "dependencia": "DEPENDENCIA",
            "solicitante": "SOLICITANTE",
            "tipo_solicitud": "TIPO DE SOLICITUD",
            "medio_solicitud": "MEDIO DE SOLICITUD",
            "descripcion": "DESCRIPCIÓN",
            "cumplido": "CUMPLIDO",
            "fecha_atencion": "FECHA ATENCIÓN",
            "observaciones": "OBSERVACIONES"
        }
        df.rename(columns=col_map, inplace=True)
        # Asegurar columnas faltantes
        for col in COLUMNAS:
            if col not in df.columns:
                df[col] = ""
                
        return df.fillna('')
    except Exception as e:
        logger.error(f"Error cargando registros SQL: {e}")
        return pd.DataFrame(columns=COLUMNAS)

@retry_operation(max_retries=3)
@medir_tiempo
def guardar_registro(data):
    try:
        sync_uid = uuid.uuid4().hex
        ahora = _ahora()
        with db_session() as conn:
            cursor = get_cursor(conn)
            
            query = '''
                INSERT INTO registros (
                    usuario, tipo_actividad, fecha, dependencia, solicitante,
                    tipo_solicitud, medio_solicitud, descripcion, cumplido,
                    fecha_atencion, observaciones, sync_uid, updated_at, borrado
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            '''
            
            insert_values = (
                data.get("USUARIO"),
                data.get("TIPO DE ACTIVIDAD"),
                data.get("FECHA"),
                data.get("DEPENDENCIA"),
                data.get("SOLICITANTE"),
                data.get("TIPO DE SOLICITUD"),
                data.get("MEDIO DE SOLICITUD"),
                data.get("DESCRIPCIÓN"),
                data.get("CUMPLIDO"),
                data.get("FECHA ATENCIÓN"),
                data.get("OBSERVACIONES"),
                sync_uid, ahora, 0
            )
            
            if DATABASE_URL:
                # Postgres requiere RETURNING id para obtener el ID insertado
                query_pg = query.replace('?', '%s') + " RETURNING id"
                cursor.execute(query_pg, insert_values)
                nuevo_id = cursor.fetchone()['id']
            else:
                # SQLite usa lastrowid
                cursor.execute(query, insert_values)
                nuevo_id = cursor.lastrowid
        
        return nuevo_id
    except Exception as e:
        logger.error(f"Error guardando registro SQL: {e}")
        return None
    finally:
        # Sincronizar con Excel después de guardar (no debe afectar el resultado ni causar reintentos)
        try:
            sincronizar_excel()
        except Exception as e:
            logger.warning(f"Error sincronizando Excel (no crítico, registro ya guardado en BD): {e}")

@retry_operation(max_retries=3)
@medir_tiempo
def eliminar_registro(id_registro, usuario):
    try:
        with db_session() as conn:
            cursor = get_cursor(conn)
            
            # Verificar propiedad
            if usuario != "admin":
                cursor.execute(fix_query("SELECT usuario FROM registros WHERE id = ?"), (id_registro,))
                row = cursor.fetchone()
                if not row or row['usuario'] != usuario:
                    return False

            # Borrado lógico: se marca la fila y la sincronización propaga la eliminación a la red
            cursor.execute(fix_query("UPDATE registros SET borrado = 1, updated_at = ? WHERE id = ?"), (_ahora(), id_registro))

        return True
    except Exception as e:
        logger.error(f"Error eliminando registro SQL: {e}")
        return False
    finally:
        try:
            sincronizar_excel()
        except Exception:
            pass

@retry_operation(max_retries=3)
@medir_tiempo
def actualizar_registro(id_registro, data, usuario):
    try:
        with db_session() as conn:
            cursor = get_cursor(conn)
            
            # Verificar propiedad
            cursor.execute(fix_query("SELECT usuario FROM registros WHERE id = ?"), (id_registro,))
            row = cursor.fetchone()
            if not row:
                return False
                
            if usuario != "admin" and row['usuario'] != usuario:
                return False
                
            # Construir UPDATE dinámico
            inv_col_map = {
                "USUARIO": "usuario",
                "TIPO DE ACTIVIDAD": "tipo_actividad",
                "FECHA": "fecha",
                "DEPENDENCIA": "dependencia",
                "SOLICITANTE": "solicitante",
                "TIPO DE SOLICITUD": "tipo_solicitud",
                "MEDIO DE SOLICITUD": "medio_solicitud",
                "DESCRIPCIÓN": "descripcion",
                "CUMPLIDO": "cumplido",
                "FECHA ATENCIÓN": "fecha_atencion",
                "OBSERVACIONES": "observaciones"
            }
            
            fields = []
            values = []
            for key, value in data.items():
                if key in inv_col_map:
                    if key == 'USUARIO' and usuario != 'admin':
                        continue
                    fields.append(f"{inv_col_map[key]} = ?")
                    values.append(value)
            
            # Marcar actualización para que la sincronización propague el cambio
            fields.append("updated_at = ?")
            values.append(_ahora())
            fields.append("borrado = 0")
            
            if not fields:
                return True
                
            values.append(id_registro)
            query = f"UPDATE registros SET {', '.join(fields)} WHERE id = ?"
            query = fix_query(query)

            cursor.execute(query, values)
            
        clear_cache()
        return True
    except Exception as e:
        logger.error(f"Error actualizando registro SQL: {e}")
        return False
    finally:
        try:
            sincronizar_excel()
        except Exception:
            pass
