import sys
import sqlite3

BACKEND = r"C:\Users\AICOE 5\Downloads\Farm_Assist.Application\backend"
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from app.database.schema_upgrade import run_additive_migrations

db = r"C:\Users\AICOE 5\AppData\Local\Temp\opencode\final.db"
run_additive_migrations("sqlite:///" + db.replace("\\", "/"))
print("migrations applied")

c = sqlite3.connect(db)
print("integrity_check:", c.execute("PRAGMA integrity_check").fetchall()[:2])
print("fk violations:", len(c.execute("PRAGMA foreign_key_check").fetchall()))

print("--- the recovered purchase records ---")
for r in c.execute("SELECT sale_id, buyer_name, total_amount, status, created_at FROM marketplace_sales ORDER BY created_at"):
    print("  SALE", r)
for r in c.execute("SELECT listing_id, title, price, status FROM marketplace_listings"):
    print("  LISTING", r)
for r in c.execute("SELECT id, buyer_name, status, created_at FROM marketplace_enquiries ORDER BY created_at"):
    print("  ENQUIRY", r)
c.close()
