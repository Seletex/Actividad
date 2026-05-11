"""
MÃ³dulo de configuraciÃ³n y logging para la aplicaciÃ³n.
Solo contiene constantes, valores por defecto y configuraciÃ³n de logging.
Las plantillas HTML estÃ¡n en templates.py
"""

import os
import sys
import json
import shutil
import logging
from logging.handlers import RotatingFileHandler

def setup_logging():
    """Configura el sistema de logging para monitoreo de rendimiento"""
    # Determinar directorio base: si es .exe, usar directorio del ejecutable
    if getattr(sys, 'frozen', False):
        _base = os.path.dirname(sys.executable)
    else:
        _base = os.path.dirname(os.path.abspath(__file__))
    
    # Intentar crear logs en el directorio del exe, si no se puede usar Documents
    log_dir = os.path.join(_base, "logs")
    try:
        os.makedirs(log_dir, exist_ok=True)
    except Exception:
        # Fallback a documentos del usuario
        log_dir = os.path.join(os.path.expanduser("~"), "Documents", "Actividades", "logs")
        try:
            os.makedirs(log_dir, exist_ok=True)
        except Exception:
            log_dir = "logs"  # último recurso
    print(f"Directorio de logs: {log_dir}")
    if not os.path.exists(log_dir):
        try:
            os.makedirs(log_dir, exist_ok=True)
        except:
            pass
    
    # Handler para errores especificos
    error_handler = RotatingFileHandler(
        os.path.join(log_dir, 'errores.log') if os.path.exists(log_dir) else 'errores.log',
        maxBytes=5*1024*1024,
        backupCount=5
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            RotatingFileHandler(
                os.path.join(log_dir, 'rendimiento.log') if os.path.exists(log_dir) else 'rendimiento.log',
                maxBytes=10*1024*1024,
                backupCount=5,
                encoding='utf-8'
            ),
            error_handler,
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)

# Inicializar logger de inmediato
try:
    logger = setup_logging()
    logger.info("--- INICIO DE CONFIGURACIÃ“N ---")
except Exception as e:
    print(f"Error configurando logging inicial: {e}")
    logger = logging.getLogger(__name__)

# =============================================================================
# CONSTANTES DE CONFIGURACIÃ“N
# =============================================================================

# Directorio base absoluto (donde estÃ¡ este archivo config.py)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

if getattr(sys, 'frozen', False):
    DEFAULT_DATA_DIR = os.path.dirname(sys.executable)
else:
    DEFAULT_DATA_DIR = BASE_DIR

def _is_writable_dir(path):
    try:
        test_path = os.path.join(path, ".write_test")
        with open(test_path, "w", encoding="utf-8") as f:
            f.write("ok")
        os.remove(test_path)
        return True
    except Exception:
        return False

MASTER_DIR = None

def _resolve_data_dir():
    """
    Resuelve el directorio de datos. 
    Forzamos que use siempre el directorio donde está la aplicación para evitar 
    desincronizaciones en red.
    """
    env_dir = os.environ.get("ACTIVIDADES_DATA_DIR")
    if env_dir and os.path.isdir(env_dir):
        return env_dir
    return DEFAULT_DATA_DIR

DATA_DIR = _resolve_data_dir()
print(f"Directorio de datos: {DATA_DIR}")

def buscar_archivo(nombre, directorios_prioridad):
    """Busca un archivo en varios directorios y devuelve la ruta absoluta del primero que exista."""
    for d in directorios_prioridad:
        if not d: continue
        ruta = os.path.normpath(os.path.join(d, nombre))
        if os.path.exists(ruta):
            logger.info(f"Archivo '{nombre}' encontrado en: {ruta}")
            return ruta
    
    # Si no se encuentra, devolver la ruta en el primer directorio por defecto
    ruta_defecto = os.path.normpath(os.path.join(directorios_prioridad[0], nombre))
    logger.warning(f"Archivo '{nombre}' NO ENCONTRADO. Usando ruta por defecto: {ruta_defecto}")
    return ruta_defecto

def _copy_if_exists(src_dir, filename):
    try:
        src = os.path.join(src_dir, filename)
        dst = os.path.join(DATA_DIR, filename)
        if os.path.exists(src) and not os.path.exists(dst):
            shutil.copy2(src, dst)
    except Exception:
        pass

def _ensure_templates():
    candidates = [BASE_DIR, os.path.dirname(BASE_DIR)]
    try:
        cwd = os.getcwd()
        candidates.extend([cwd, os.path.dirname(cwd)])
    except Exception:
        pass
    files = ["INFORME DE ACTIVIDADES - copia.xlsx", "InformeFinal.XLSX"]
    for fn in files:
        for cand in candidates:
            _copy_if_exists(cand, fn)

_ensure_templates()

def _dirs_search():
    dirs = []
    tmpl_env = os.environ.get("ACTIVIDADES_TEMPLATES_DIR")
    if tmpl_env and os.path.isdir(tmpl_env):
        dirs.append(tmpl_env)
    dirs.extend([DATA_DIR, os.path.dirname(DATA_DIR), BASE_DIR])
    try:
        cwd = os.getcwd()
        dirs.extend([cwd, os.path.dirname(cwd)])
    except Exception:
        pass
    seen = set()
    uniq = []
    for d in dirs:
        if d and d not in seen:
            uniq.append(d)
            seen.add(d)
    return uniq

DIRS_SEARCH = _dirs_search()

CONFIG_FILE = os.path.join(DATA_DIR, "config_actividades.json")
EXCEL_FILE = os.path.join(DATA_DIR, "actividades.xlsx")
DB_FILE = os.path.join(DATA_DIR, "actividades.db")

try:
    _legacy_db = os.path.join(DEFAULT_DATA_DIR, "actividades.db")
    if _legacy_db != DB_FILE and os.path.exists(_legacy_db) and not os.path.exists(DB_FILE):
        shutil.copy2(_legacy_db, DB_FILE)
except Exception:
    pass

def _resolve_usuarios_file():
    candidates = []
    for d in DIRS_SEARCH:
        p = os.path.join(d, "usuarios.json")
        if os.path.exists(p):
            candidates.append(p)
    if not candidates:
        return os.path.join(DATA_DIR, "usuarios.json")
    def score(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            users = data.get('usuarios', []) or []
            placeholders = {'usuario1','usuario2','usuario3'}
            real = [u for u in users if u and u.lower() not in placeholders]
            return (len(real), os.path.getmtime(path))
        except Exception:
            return (0, 0)
    best = max(candidates, key=score)
    # Copiar al DATA_DIR para estandarizar accesos futuros
    try:
        dst = os.path.join(DATA_DIR, "usuarios.json")
        if os.path.abspath(best) != os.path.abspath(dst):
            shutil.copy2(best, dst)
            return dst
    except Exception:
        pass
    return best

USERS_FILE = _resolve_usuarios_file()

def _ensure_data_file(filename):
    dst = os.path.join(DATA_DIR, filename)
    if not os.path.exists(dst):
        for cand in DIRS_SEARCH:
            src = os.path.join(cand, filename)
            if os.path.exists(src):
                try:
                    shutil.copy2(src, dst)
                except Exception:
                    pass
                break

_ensure_data_file("config_actividades.json")
_ensure_data_file("usuarios.json")

# Plantillas con bÃºsqueda robusta
TEMPLATE_EXCEL = buscar_archivo("INFORME DE ACTIVIDADES - copia.xlsx", DIRS_SEARCH)
TEMPLATE_INFORME_FINAL = buscar_archivo("InformeFinal.XLSX", DIRS_SEARCH)

# =============================================================================
# MANTENIMIENTO DE PLANTILLAS Y OTROS
# =============================================================================

# Si en desarrollo existe una plantilla en el repo, copiarla a la carpeta
# de datos la primera vez si no existe allÃ­.
_repo_template = os.path.join(BASE_DIR, "INFORME DE ACTIVIDADES - copia.xlsx")
try:
    if os.path.exists(_repo_template) and not os.path.exists(os.path.join(DATA_DIR, "INFORME DE ACTIVIDADES - copia.xlsx")):
        shutil.copy2(_repo_template, os.path.join(DATA_DIR, "INFORME DE ACTIVIDADES - copia.xlsx"))
except Exception:
    pass

DATABASE_URL = os.environ.get("DATABASE_URL") # URL de base de datos para Render (PostgreSQL)

# Columnas del Excel
COLUMNAS = [
    "ID", "USUARIO", "TIPO DE ACTIVIDAD", "FECHA", "DEPENDENCIA", "SOLICITANTE",
    "TIPO DE SOLICITUD", "MEDIO DE SOLICITUD", "DESCRIPCIÃ“N", "CUMPLIDO",
    "FECHA ATENCIÃ“N", "OBSERVACIONES"
]

# =============================================================================
# VALORES POR DEFECTO
# =============================================================================

ACTIVIDADES_DEFAULT = [
    "Brindar apoyo en la atenciÃ³n de requerimientos tÃ©cnicos de primer nivel a los usuarios de la AdministraciÃ³n Municipal, atendiendo incidentes relacionados con el funcionamiento de equipos de cÃ³mputo, impresoras, configuraciÃ³n de software y otros perifÃ©ricos.",
    "Apoyar en el mantenimiento preventivo bÃ¡sico de equipos tecnolÃ³gicos, realizando tareas como limpieza, revisiÃ³n de cables, conectores y perifÃ©ricos, con el objetivo de mantener en condiciones Ã³ptimas los recursos informÃ¡ticos de la entidad.",
    "Colaborar en el control y actualizaciÃ³n del inventario de activos tecnolÃ³gicos, incluyendo equipos de cÃ³mputo, dispositivos de red, perifÃ©ricos y demÃ¡s recursos asignados a las dependencias, segÃºn los procedimientos establecidos por la oficina de sistemas.",
    "Apoyar en tareas logÃ­sticas relacionadas con la infraestructura tecnolÃ³gica, tales como instalaciÃ³n, traslado o reubicaciÃ³n de equipos de cÃ³mputo, dispositivos de red y demÃ¡s componentes tecnolÃ³gicos, bajo supervisiÃ³n del personal del Ã¡rea.",
    "Realizar seguimiento a solicitudes y requerimientos tecnolÃ³gicos de los usuarios, documentando novedades, avances y necesidades adicionales, y comunicÃ¡ndolas oportunamente a los responsables correspondientes.",
    "Apoyar en la documentaciÃ³n tÃ©cnica del Ã¡rea, incluyendo la organizaciÃ³n y archivo de documentos, informes de soporte y demÃ¡s registros, de acuerdo con las directrices internas y del Sistema de GestiÃ³n de Calidad.",
    "Colaborar en la implementaciÃ³n y seguimiento de medidas bÃ¡sicas de seguridad informÃ¡tica, tales como el monitoreo de alertas bÃ¡sicas, cierre adecuado de sesiones y cumplimiento de rutinas establecidas para el uso seguro de los recursos tecnolÃ³gicos.",
    "Otro"
]

UBICACIONES_DEFAULT = [
    "ALCALDÃA", "ALMACEN MUNICIPAL", "ARCHIVO GENERAL", "BIBLIOTECAS", "CASA DE JUSTICIA",
    "CATASTRO", "CENTRO DÃA", "COMUNICACIONES", "CONCEJO MUNICIPAL", "CONTABILIDAD",
    "CONTRATACION", "CONTROL INTERNO", "DEPARTAMENTO GENERAL", "DEPARTAMENTO JURIDICO",
    "DESARROLLO COMUNITARIO", "DESARROLLO ECONOMICO", "EDUCACION Y CULTURA",
    "EJECUCIONES FISCALES", "GESTION HUMANA", "GESTIÃ“N PREDIAL", "GOBIERNO",
    "HACIENDA", "IMPUESTOS", "INFRAESTRUCTURA", "NOMINA", "OFICINA DE SISTEMAS",
    "PARQUE EDUCATIVO", "PERSONERÃA", "PLANEACIÃ“N", "PRESUPUESTO", "PROYECCIÃ“N SOCIAL",
    "SAIMYR", "SEGURIDAD Y SALUD EN EL TRABAJO", "SIGIN Y GINAT", "SISBEN", "TESORERIA"
]

TIPOS_SOLICITUD_DEFAULT = [
    "MANTENIMIENTO PREVENTIVO",
    "MANTENIMIENTO CORRECTIVE",
    "ASESORIA Y ASISTENCIA",
    "CAPACITACIÃ“N",
    "APOYO TECNOLÃ“GICO",
    "INSTALACIONES NUEVAS"
]

MEDIOS_SOLICITUD_DEFAULT = [
    "INTRANET",
    "LLAMADA TELEFONICA",
    "E-MAIL"
]

DEFAULT_USERS = {
    "usuarios": ["admin", "usuario1", "usuario2", "usuario3"],
    "configuraciones": {}
}

# =============================================================================
# CONFIGURACIÃ“N DE CACHE
# =============================================================================

_CACHE = {}
_CACHE_TIMEOUT = 30  # segundos


