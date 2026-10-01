import sqlite3

base = sqlite3.connect(r"C:\Users\AICOE 5\AppData\Local\Temp\opencode\db_5025cf0.db")
rec = sqlite3.connect(r"C:\Users\AICOE 5\AppData\Local\Temp\opencode\farm_recovered.db")

print("=== marketplace_categories schema ===")
print([(c[1], c[2], c[3]) for c in base.execute('PRAGMA table_info("marketplace_categories")')])
print("base categories:")
for r in base.execute("SELECT id, name, slug FROM marketplace_categories"):
    print("  ", r)
print("recovered categories:")
for r in rec.execute("SELECT id, name, slug FROM marketplace_categories"):
    print("  ", r)

print("=== is recovered category 8630d474 present in base? ===")
print(base.execute("SELECT COUNT(*) FROM marketplace_categories WHERE id='8630d474-7a41-416b-9b31-a5adc21047b1'").fetchone())
print("base row with same name/slug:")
print(rec.execute("SELECT id,name,slug FROM marketplace_categories WHERE id='8630d474-7a41-416b-9b31-a5adc21047b1'").fetchone())
print("=== products UNIQUE indexes ===")
for r in base.execute("SELECT name, sql FROM sqlite_master WHERE type='index' AND tbl_name='products'"):
    print("  ", r)
base.close()
rec.close()
