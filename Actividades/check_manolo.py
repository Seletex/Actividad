import sqlite3
import pandas as pd

db_path = 'C:/Users/apoyosistemas/Documents/GitDesk/Actividad/Actividades/actividades.db'
excel_path = 'C:/Users/apoyosistemas/Documents/GitDesk/Actividad/Actividades/actividades.xlsx'

print("--- DB RECORDS FOR MANOLO ---")
conn = sqlite3.connect(db_path)
records = conn.execute("SELECT count(*) FROM registros WHERE LOWER(usuario) LIKE '%manolo%'").fetchone()
print(f"Total in DB: {records[0]}")
recent = conn.execute("SELECT id, usuario, fecha, descripcion FROM registros WHERE LOWER(usuario) LIKE '%manolo%' ORDER BY fecha DESC LIMIT 5").fetchall()
for r in recent:
    print(r)
    
print("\n--- EXCEL RECORDS FOR MANOLO ---")
try:
    df = pd.read_excel(excel_path)
    manolo_rows = df[df['USUARIO'].astype(str).str.contains('Manolo', case=False, na=False)]
    print(f"Total in Excel: {len(manolo_rows)}")
    if len(manolo_rows) > 0:
        print(manolo_rows[['USUARIO', 'FECHA', 'TIPO DE ACTIVIDAD', 'DESCRIPCIN']].head(5))
except Exception as e:
    print("Error reading excel:", e)
