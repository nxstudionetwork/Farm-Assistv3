import sqlite3

rec = sqlite3.connect(r"C:\Users\AICOE 5\AppData\Local\Temp\opencode\farm_recovered.db")
m = sqlite3.connect(r"C:\Users\AICOE 5\AppData\Local\Temp\opencode\merged_v6.db")

print("=== the 8 products that are in recovered but not base ===")
rc = [c[1] for c in rec.execute('PRAGMA table_info("products")')]
recids = {x[0] for x in rec.execute("SELECT id FROM products")}
baseids = {x[0] for x in m.execute("SELECT id FROM products")}
new = [i for i in recids if i not in baseids]
for i in new:
    d = dict(zip(rc, rec.execute("SELECT * FROM products WHERE id=?", (i,)).fetchone()))
    cat = d.get("category_id")
    sel = d.get("seller_id")
    print(f"  name={d.get('name')!r} product_id={d.get('product_id')} active={d.get('is_active')}")
    print(f"     category_id={cat} resolves={m.execute('SELECT COUNT(*) FROM product_categories WHERE id=?', (cat,)).fetchone()[0] if cat else 'NULL'}")
    print(f"     seller_id  ={sel} resolves={m.execute('SELECT COUNT(*) FROM sellers WHERE id=?', (sel,)).fetchone()[0] if sel else 'NULL'}")

print("=== product_crops violations: which products? ===")
v = m.execute("PRAGMA foreign_key_check").fetchall()
pc = [x for x in v if x[0] == "product_crops"]
pids = set()
cc = [c[1] for c in m.execute('PRAGMA table_info("product_crops")')]
for _, rowid, _, _ in pc[:200]:
    row = m.execute("SELECT * FROM product_crops WHERE rowid=?", (rowid,)).fetchone()
    d = dict(zip(cc, row))
    pids.add(d.get("product_id"))
print(f"  {len(pc)} violations across {len(pids)} distinct product_ids")
print(f"  of those, in recovered products: {sum(1 for p in pids if p in recids)}")
print(f"  in merged products: {sum(1 for p in pids if p in baseids)}")
rec.close(); m.close()
