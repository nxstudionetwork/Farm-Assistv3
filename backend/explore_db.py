import sqlite3
conn = sqlite3.connect('farm_assist.db')
c = conn.cursor()
c.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in c.fetchall()]
print("TABLES:", tables)

# User columns
try:
    c.execute("PRAGMA table_info(users)")
    print("\nUSERS columns:", [(r[1], r[2]) for r in c.fetchall()])
except:
    print("No users table")

# Farm columns
for tbl in ['farms', 'farm_plots', 'crops']:
    try:
        c.execute(f"PRAGMA table_info({tbl})")
        print(f"\n{tbl} columns:", [(r[1], r[2]) for r in c.fetchall()])
    except:
        print(f"\nNo {tbl} table")

# Check if documents table exists
if 'documents' in tables:
    c.execute("PRAGMA table_info(documents)")
    print("\nDOCUMENTS columns:", [(r[1], r[2]) for r in c.fetchall()])
else:
    print("\nNo documents table exists")

# Count users
c.execute("SELECT id, farmer_id, name, phone, email FROM users")
for r in c.fetchall():
    print(f"\nUser: id={r[0]}, farmer_id={r[1]}, name={r[2]}, phone={r[3]}, email={r[4]}")

# Count farms
try:
    c.execute("SELECT id, farmer_id, farm_name, total_area, area_unit FROM farms")
    for r in c.fetchall():
        print(f"Farm: id={r[0]}, farmer_id={r[1]}, name={r[2]}, area={r[3]} {r[4]}")
except:
    pass

conn.close()
