# -*- coding: utf-8 -*-
"""
sincronizar_total.py
====================
Script de sincronizacion consolidada de la base de datos de actividades.

PROBLEMA QUE RESUELVE:
    La funcion sincronizar_db_a_master() del programa esta deshabilitada
    porque MASTER_DIR = None en config.py. Cada equipo que ejecuta una
    copia local del exe escribe en su propia BD y esa informacion nunca
    vuelve a la BD central del servidor de red.

SOLUCION:
    Este script recolecta los registros de todas las BD y del Excel maestro,
    los consolida por clave natural (usuario + fecha + solicitante + observaciones)
    y los distribuye a todas las BD y Excel exportados.

USO:
    python sincronizar_total.py            # vista previa (no escribe nada)
    python sincronizar_total.py --aplicar  # hace backups y sincroniza de verdad
"""

import argparse
import os
import shutil
import sqlite3
import sys
import io
from datetime import datetime

import pandas as pd

# ---------------------------------------------------------------------------
# SALIDA CON UTF-8 EN CONSOLA WINDOWS
# ---------------------------------------------------------------------------
if sys.stdout.encoding and 'cp' in sys.stdout.encoding.lower():
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    except Exception:
        pass

# ---------------------------------------------------------------------------
# RUTAS DE LAS BD Y EXCEL A SINCRONIZAR
# ---------------------------------------------------------------------------
RUTA_PROYECTO  = r"C:\Users\apoyosistemas\Documents\GitDesk\Actividad\Actividades"
RUTA_SERVIDOR  = r"\\192.168.10.2\d$\ACTIVIDADES\Actividades\dist"
RUTA_LOCAL_EXE = r"C:\Users\apoyosistemas\Documents\GitDesk\Actividad\Actividades\dist\GestorActividades"
RUTA_APPDATA   = os.path.join(os.environ.get("LOCALAPPDATA", ""), "ActividadesData")

BD_SOURCES = [
    (os.path.join(RUTA_PROYECTO, "actividades.db"), "PROYECTO web"),
    (os.path.join(RUTA_SERVIDOR, "actividades.db"), "SERVIDOR dist"),
    (os.path.join(RUTA_LOCAL_EXE, "actividades.db"), "LOCAL dist (exe)"),
    (os.path.join(RUTA_APPDATA, "actividades.db"), "COPIA AppData"),
]

EXCEL_SOURCES = [
    (os.path.join(RUTA_PROYECTO, "actividades.xlsx"), "PROYECTO excel"),
    (os.path.join(RUTA_SERVIDOR, "actividades.xlsx"), "SERVIDOR dist excel"),
    (os.path.join(RUTA_LOCAL_EXE, "actividades.xlsx"), "LOCAL dist excel"),
    (r"C:\Users\apoyosistemas\Documents\actividades (11).xlsx", "RESPALDO JuanB (11)"),
    (r"C:\Users\apoyosistemas\Documents\actividades (12).xlsx", "RESPALDO Freddy (12)"),
]

ENCABEZADOS = [
    "USUARIO", "TIPO DE ACTIVIDAD", "FECHA", "DEPENDENCIA", "SOLICITANTE",
    "TIPO DE SOLICITUD", "MEDIO DE SOLICITUD", "DESCRIPCIÓN", "CUMPLIDO",
    "FECHA ATENCIÓN", "OBSERVACIONES"
]

COLS_SQL = ["usuario", "tipo_actividad", "fecha", "dependencia", "solicitante",
            "tipo_solicitud", "medio_solicitud", "descripcion", "cumplido",
            "fecha_atencion", "observaciones"]

# ---------------------------------------------------------------------------
# UTILIDADES
# ---------------------------------------------------------------------------

def s(x):
    return str(x) if pd.notna(x) else ''


def norm_fecha(f):
    s = str(f)[:19]
    return s + ' 00:00:00' if len(s) == 10 else s

def clave(usuario, fecha, solicitante, observaciones):
    return (
        (usuario or '').strip().upper(),
        norm_fecha(fecha),
        (solicitante or '').strip().upper()[:40],
        (observaciones or '').strip().upper()[:60],
    )


def es_registro_prueba(fila):
    """Excluye registros de prueba conocidos (admin Test Bot de 2023)."""
    u = (fila.get('usuario') or '').strip().upper()
    f = str(fila.get('fecha') or '')[:19]
    return u == 'ADMIN' and f.startswith('2023-10') and 'TEST' in (fila.get('solicitante') or '').upper()


def leer_bd(ruta):
    """Lee todos los registros de una BD sqlite y devuelve lista de dicts."""
    filas = []
    if not os.path.exists(ruta):
        return filas, False
    try:
        conn = sqlite3.connect(ruta, timeout=60)
        conn.row_factory = sqlite3.Row
        tabs = [t[0] for t in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        if 'registros' not in tabs:
            conn.close()
            return filas, False
        for r in conn.execute("SELECT * FROM registros"):
            filas.append({c: r[c] for c in COLS_SQL})
        conn.close()
        return filas, True
    except Exception as e:
        print(f"    [AVISO] No se pudo leer BD {ruta}: {e}")
        return filas, False


def leer_excel(ruta):
    """Lee un Excel de actividades y devuelve lista de dicts con COLS_SQL."""
    filas = []
    if not os.path.exists(ruta):
        return filas, False
    try:
        df = pd.read_excel(ruta, engine='openpyxl')
        cols_upper = {str(c).upper().strip(): c for c in df.columns}
        if 'USUARIO' not in cols_upper:
            return filas, False
        col_fa = None
        for k in cols_upper:
            if 'FECHA' in k and 'ATENCION' in k:
                col_fa = cols_upper[k]
                break
        mapeo = {
            'USUARIO': 'usuario',
            'TIPO DE ACTIVIDAD': 'tipo_actividad',
            'FECHA': 'fecha',
            'DEPENDENCIA': 'dependencia',
            'SOLICITANTE': 'solicitante',
            'TIPO DE SOLICITUD': 'tipo_solicitud',
            'MEDIO DE SOLICITUD': 'medio_solicitud',
            'DESCRIPCIÓN': 'descripcion',
            'CUMPLIDO': 'cumplido',
            'FECHA ATENCIÓN': 'fecha_atencion',
            'OBSERVACIONES': 'observaciones',
        }
        for _, r in df.iterrows():
            fila = {}
            for excel_col, sql_col in mapeo.items():
                c = cols_upper.get(excel_col.upper())
                fila[sql_col] = s(r[c]) if c else ''
            fila['usuario'] = s(r[cols_upper['USUARIO']]).strip() or 'admin'
            fila['fecha'] = str(pd.Timestamp(r[cols_upper['FECHA']]))[:19] if pd.notna(r[cols_upper['FECHA']]) else ''
            if col_fa and pd.notna(r.get(col_fa)):
                fila['fecha_atencion'] = str(pd.Timestamp(r[col_fa]))[:19]
            filas.append(fila)
        return filas, True
    except Exception as e:
        print(f"    [AVISO] No se pudo leer Excel {ruta}: {e}")
        return filas, False


def escribir_bd(ruta, filas, aplicar):
    """Escribe el conjunto completo de registros en una BD, sin perder ids."""
    if not aplicar:
        return 0
    conn = sqlite3.connect(ruta)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    existentes = set()
    filas_bd = []
    for r in cur.execute("SELECT * FROM registros"):
        d = {c: r[c] for c in COLS_SQL}
        filas_bd.append(d)
        existentes.add(clave(d['usuario'], d['fecha'], d['solicitante'], d['observaciones']))
    insertados = 0
    for fila in filas:
        k = clave(fila['usuario'], fila['fecha'], fila['solicitante'], fila['observaciones'])
        if k in existentes:
            continue
        cur.execute("""INSERT INTO registros
            (usuario, tipo_actividad, fecha, dependencia, solicitante, tipo_solicitud,
             medio_solicitud, descripcion, cumplido, fecha_atencion, observaciones)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (fila['usuario'], fila['tipo_actividad'], fila['fecha'], fila['dependencia'],
             fila['solicitante'], fila['tipo_solicitud'], fila['medio_solicitud'],
             fila['descripcion'], fila['cumplido'], fila['fecha_atencion'], fila['observaciones']))
        existentes.add(k)
        insertados += 1
    conn.commit()
    conn.close()
    return insertados


def escribir_excel(ruta, filas, aplicar):
    """Genera el Excel exportado con las filas dadas."""
    if aplicar:
        mapa_sql_encab = dict(zip(COLS_SQL, ENCABEZADOS))
        df = pd.DataFrame(
            [{mapa_sql_encab.get(k, k): v for k, v in fila.items()} for fila in filas]
        )
        for c in ENCABEZADOS:
            if c not in df.columns:
                df[c] = ''
        df = df[ENCABEZADOS].fillna('')
        df.to_excel(ruta, index=False, engine='openpyxl')
    return len(filas)


def backup(ruta):
    """Copia de respaldo con timestamp."""
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    bp = f"{ruta}.backup_{ts}"
    shutil.copy2(ruta, bp)
    return bp


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Sincronizador consolidado de actividades")
    ap.add_argument("--aplicar", action="store_true",
                    help="Hace backups y sincroniza de verdad (por defecto solo vista previa)")
    args = ap.parse_args()
    aplicar = args.aplicar

    print("=" * 70)
    print("SINCRONIZADOR TOTAL DE ACTIVIDADES")
    print("Modo:", "APLICAR (escribe)" if aplicar else "VISTA PREVIA (no escribe nada)")
    print("=" * 70)

    # 1. Recolectar todas las filas disponibles
    consolidado = {}    # clave -> dict
    origen_por_clave = {}
    total_origenes = 0
    reporte = []

    print("\n[1/4] Recolectando registros de todas las fuentes...")
    fuentes = [("BD", p, n) for p, n in BD_SOURCES] + [("EXCEL", p, n) for p, n in EXCEL_SOURCES]
    for tipo, ruta, nombre in fuentes:
        if tipo == "BD":
            filas, ok = leer_bd(ruta)
        else:
            filas, ok = leer_excel(ruta)
        if not ok:
            reporte.append((nombre, tipo, 0, "NO ACCESIBLE / SIN TABLA"))
            continue
        for fila in filas:
            if es_registro_prueba(fila):
                continue
            k = clave(fila['usuario'], fila['fecha'], fila['solicitante'], fila['observaciones'])
            if k not in consolidado:
                consolidado[k] = dict(fila)
                origen_por_clave[k] = nombre
        reporte.append((nombre, tipo, len(filas), "OK"))
    total_origenes = len(consolidado)

    for nombre, tipo, n, estado in reporte:
        print(f"    {tipo:5s} | {n:5d} | {nombre}")
    print(f"\n  TOTAL registros unicos consolidados: {total_origenes}")

    # 2. Comparación por BD destino
    print("\n[2/4] Comparando con cada BD destino...")
    por_bd = []
    for ruta, nombre in BD_SOURCES:
        filas_bd, ok = leer_bd(ruta)
        if not ok:
            fal = len(consolidado)
            por_bd.append((ruta, nombre, 0, fal))
            print(f"    {nombre}: NO ACCESIBLE (se crearia con {fal} registros)")
            continue
        presentes = set(clave(f['usuario'], f['fecha'], f['solicitante'], f['observaciones']) for f in filas_bd)
        faltan = [(k, v) for k, v in consolidado.items() if k not in presentes]
        por_bd.append((ruta, nombre, len(filas_bd), len(faltan)))
        print(f"    {nombre}: {len(filas_bd)} en BD, faltan {len(faltan)}")

    # 3. Backups + escritura
    modo_txt = "backups y" if aplicar else "sin"
    print(f"\n[3/4] Escritura (con {modo_txt} cambios):")
    total_insert = 0
    for ruta, nombre, n_bd, n_faltan in por_bd:
        if n_faltan == 0:
            print(f"    {nombre}: ya sincronizado (0 faltantes)")
            continue
        if aplicar:
            try:
                bp = backup(ruta)
                ins = escribir_bd(ruta, [v for _, v in consolidado.items()], True)
                print(f"    {nombre}: backup {os.path.basename(bp)} -> +{ins} registros")
                total_insert += ins
            except Exception as e:
                print(f"    {nombre}: ERROR {e}")
        else:
            print(f"    {nombre}: faltan {n_faltan} registros (vista previa, no se escribe)")

    # 4. Excel exportados: deben reflejar la BD completa (todas las filas,
    #    incluyendo duplicados internos), igual que hace sincronizar_excel().
    filas_bd_completa, _ok_bd = leer_bd(BD_SOURCES[0][0])
    print("\n[4/4] Regenerando Excel exportados...")
    for ruta, nombre in EXCEL_SOURCES[:3]:
        n = escribir_excel(ruta, filas_bd_completa, aplicar)
        estado = f"OK ({n} filas)" if aplicar else f"se generaria con {n} filas"
        print(f"    {nombre}: {estado}")

    print("\n" + "=" * 70)
    if aplicar:
        print(f"LISTO: se insertaron {total_insert} registros nuevos en total.")
    else:
        print("VISTA PREVIA completada. Use  --aplicar  para sincronizar de verdad.")
    print("=" * 70)


if __name__ == "__main__":
    main()