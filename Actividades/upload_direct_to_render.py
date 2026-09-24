# -*- coding: utf-8 -*-
import sqlite3
import psycopg2
from psycopg2.extras import execute_values
import sys

def main():
    pg_url = 'postgresql://actividades_db_ne02_user:wv2ifYfkakGXoJ4qjEfbRW5PZC88cNRH@dpg-daop2bek1f9s7385ucug-a.oregon-postgres.render.com/actividades_db_ne02'
    sqlite_path = 'actividades.db'

    print("Conectando a bases de datos...", flush=True)
    sq_conn = sqlite3.connect(sqlite_path)
    sq_conn.row_factory = sqlite3.Row
    pg_conn = psycopg2.connect(pg_url)
    pg_cur = pg_conn.cursor()

    # 1. Migrar usuarios
    users = [dict(r) for r in sq_conn.execute('SELECT username, password_hash, password_salt, debe_cambiar_contrasena FROM usuarios').fetchall()]
    print(f"Usuarios en SQLite: {len(users)}", flush=True)
    for u in users:
        pg_cur.execute('''
            INSERT INTO usuarios (username, password_hash, password_salt, debe_cambiar_contrasena)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (username) DO UPDATE SET 
                password_hash = COALESCE(EXCLUDED.password_hash, usuarios.password_hash),
                password_salt = COALESCE(EXCLUDED.password_salt, usuarios.password_salt),
                debe_cambiar_contrasena = EXCLUDED.debe_cambiar_contrasena
        ''', (u['username'], u['password_hash'], u['password_salt'], u['debe_cambiar_contrasena']))
    pg_conn.commit()

    # 2. Migrar actividades personales
    acts = [dict(r) for r in sq_conn.execute('SELECT username, actividad FROM actividades_personales').fetchall()]
    print(f"Actividades personales en SQLite: {len(acts)}", flush=True)
    for a in acts:
        pg_cur.execute('''
            INSERT INTO actividades_personales (username, actividad)
            VALUES (%s, %s)
            ON CONFLICT (username, actividad) DO NOTHING
        ''', (a['username'], a['actividad']))
    pg_conn.commit()

    # 3. Migrar configuracion_usuario
    confs = [dict(r) for r in sq_conn.execute('SELECT username, clave, valor FROM configuracion_usuario').fetchall()]
    print(f"Configuraciones en SQLite: {len(confs)}", flush=True)
    for c in confs:
        pg_cur.execute('''
            INSERT INTO configuracion_usuario (username, clave, valor)
            VALUES (%s, %s, %s)
            ON CONFLICT (username, clave) DO UPDATE SET valor = EXCLUDED.valor
        ''', (c['username'], c['clave'], c['valor']))
    pg_conn.commit()

    # 4. Migrar listas globales
    lists = [dict(r) for r in sq_conn.execute('SELECT tipo, valor FROM listas_globales').fetchall()]
    print(f"Listas globales en SQLite: {len(lists)}", flush=True)
    for l in lists:
        pg_cur.execute('''
            INSERT INTO listas_globales (tipo, valor)
            VALUES (%s, %s)
            ON CONFLICT (tipo, valor) DO NOTHING
        ''', (l['tipo'], l['valor']))
    pg_conn.commit()

    # 5. Migrar registros usando execute_values (súper rápido)
    regs = [dict(r) for r in sq_conn.execute('SELECT id, usuario, tipo_actividad, fecha, dependencia, solicitante, tipo_solicitud, medio_solicitud, descripcion, cumplido, fecha_atencion, observaciones FROM registros').fetchall()]
    print(f"Registros en SQLite: {len(regs)}", flush=True)

    query = '''
        INSERT INTO registros (id, usuario, tipo_actividad, fecha, dependencia, solicitante, tipo_solicitud, medio_solicitud, descripcion, cumplido, fecha_atencion, observaciones)
        VALUES %s
        ON CONFLICT (id) DO UPDATE SET
            usuario = EXCLUDED.usuario,
            tipo_actividad = EXCLUDED.tipo_actividad,
            fecha = EXCLUDED.fecha,
            dependencia = EXCLUDED.dependencia,
            solicitante = EXCLUDED.solicitante,
            tipo_solicitud = EXCLUDED.tipo_solicitud,
            medio_solicitud = EXCLUDED.medio_solicitud,
            descripcion = EXCLUDED.descripcion,
            cumplido = EXCLUDED.cumplido,
            fecha_atencion = EXCLUDED.fecha_atencion,
            observaciones = EXCLUDED.observaciones
    '''
    tuples = [
        (
            r['id'], r['usuario'], r['tipo_actividad'], r['fecha'], r['dependencia'],
            r['solicitante'], r['tipo_solicitud'], r['medio_solicitud'], r['descripcion'],
            r['cumplido'], r['fecha_atencion'], r['observaciones']
        )
        for r in regs
    ]

    # Enviar en bloques de 300
    batch_size = 300
    for i in range(0, len(tuples), batch_size):
        chunk = tuples[i:i+batch_size]
        execute_values(pg_cur, query, chunk)
        pg_conn.commit()
        print(f"  Insertados registros {i} a {min(i+batch_size, len(tuples))}...", flush=True)

    # Ajustar secuencia autoincremental
    pg_cur.execute("SELECT setval(pg_get_serial_sequence('registros', 'id'), COALESCE((SELECT max(id) FROM registros), 1));")
    pg_conn.commit()

    print("¡Sincronización completada con éxito a Render PostgreSQL!", flush=True)

    pg_cur.close()
    pg_conn.close()
    sq_conn.close()

if __name__ == '__main__':
    main()
