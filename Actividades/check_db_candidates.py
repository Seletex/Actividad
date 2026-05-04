import sqlite3
import os
import sys

# Simular DIRS_SEARCH
dirs = [
    r'\\192.168.10.2\d$\ACTIVIDADES',
    r'\\192.168.10.2\d$\ACTIVIDADES\Actividades'
]

def _db_score(p):
    try:
        cnt = 0
        with sqlite3.connect(p) as _c:
            _cur = _c.cursor()
            _cur.execute("SELECT COUNT(*) FROM registros")
            cnt = int(_cur.fetchone()[0])
    except Exception as e:
        print(f"Error scoring {p}: {e}")
        cnt = 0
    try:
        mtime = os.path.getmtime(p)
        size = os.path.getsize(p)
    except Exception:
        mtime, size = 0, 0
    return (cnt, mtime, size)

def check_candidates():
    candidates = []
    for d in dirs:
        for name in ("actividades.db", "database.db"):
            p = os.path.join(d, name)
            if os.path.exists(p):
                score = _db_score(p)
                print(f"Candidate: {p}")
                print(f"  Score (records, mtime, size): {score}")
                
                # Check users in this candidate
                try:
                    with sqlite3.connect(p) as conn:
                        conn.row_factory = sqlite3.Row
                        cur = conn.cursor()
                        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='usuarios'")
                        if cur.fetchone():
                            cur.execute("SELECT username FROM usuarios")
                            users = [row['username'] for row in cur.fetchall()]
                            print(f"  Users: {users}")
                        else:
                            print("  Table 'usuarios' NOT FOUND")
                except Exception as e:
                    print(f"  Error checking users: {e}")
                print("-" * 40)

if __name__ == '__main__':
    check_candidates()
