import sys
import os

# Asegurar que podemos importar desde el directorio actual
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import DB_FILE, USERS_FILE, DATA_DIR, DIRS_SEARCH
from database import cargar_usuarios

print(f"Directorio de Datos: {DATA_DIR}")
print(f"Archivo de Base de Datos (DB_FILE): {DB_FILE}")
print(f"Archivo de Usuarios (USERS_FILE): {USERS_FILE}")
print(f"Directorios de Búsqueda: {DIRS_SEARCH}")

try:
    data = cargar_usuarios()
    print(f"\nUsuarios encontrados en el sistema: {data.get('usuarios', [])}")
except Exception as e:
    print(f"\nError al cargar usuarios: {e}")

# Verificar si el archivo de base de datos existe
if os.path.exists(DB_FILE):
    import sqlite3
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tablas = [row[0] for row in cursor.fetchall()]
        print(f"Tablas en la BD: {tablas}")
        
        if 'usuarios' in tablas:
            cursor.execute("SELECT username FROM usuarios")
            users_db = [row[0] for row in cursor.fetchall()]
            print(f"Usuarios en la tabla 'usuarios': {users_db}")
        else:
            print("La tabla 'usuarios' NO EXISTE en esta base de datos.")
        conn.close()
    except Exception as e:
        print(f"Error accediendo directamente a SQLite: {e}")
else:
    print(f"El archivo {DB_FILE} NO EXISTE.")
