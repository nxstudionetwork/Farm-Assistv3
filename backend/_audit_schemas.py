import sqlite3

db_path = r'C:\Users\AICOE 5\Downloads\Farm_Assist.Application\backend\farm_assist.db'
conn = sqlite3.connect(db_path)
cur = conn.cursor()

cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = [r[0] for r in cur.fetchall()]
print("=== ALL TABLES ===")
for t in tables:
    print(t)

focus = ['government_schemes', 'saved_schemes', 'scheme_applications', 'scheme_documents']
for t in focus:
    print(f"\n=== {t} ===")
    try:
        cur.execute(f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{t}'")
        row = cur.fetchone()
        if row:
            print("CREATE SQL:")
            print(row[0])
        else:
            print("Table not found!")
            continue
        cur.execute(f'SELECT COUNT(*) FROM [{t}]')
        print(f"ROW COUNT: {cur.fetchone()[0]}")
        cur.execute(f'PRAGMA table_info([{t}])')
        cols = cur.fetchall()
        print("COLUMNS:")
        for c in cols:
            print(f"  {c[1]:30s} {c[2]:20s} pk={c[5]} notnull={c[3]} default={c[4]}")
    except Exception as e:
        print(f"Error: {e}")

conn.close()
