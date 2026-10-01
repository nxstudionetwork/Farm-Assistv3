import sys
import sqlite3

BACKEND = r"C:\Users\AICOE 5\Downloads\Farm_Assist.Application\backend"
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from app.database.schema_upgrade import run_additive_migrations

db_file = r"C:\Users\AICOE 5\AppData\Local\Temp\opencode\merged.db"
db_url = "sqlite:///" + db_file.replace("\\", "/")

print("Running additive migrations on merged...")
run_additive_migrations(db_url)
print("Additive migrations done!")

con = sqlite3.connect(db_file)
print("quick_check:", con.execute("PRAGMA quick_check").fetchall())
print("integrity_check:", con.execute("PRAGMA integrity_check").fetchall()[:3])
con.close()
