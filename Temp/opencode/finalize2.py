import sqlite3

m = sqlite3.connect(r"C:\Users\AICOE 5\AppData\Local\Temp\opencode\final.db")
m.execute("PRAGMA foreign_keys=OFF")

# products.seller_id -> NULL when the seller row is absent
nn = {c[1] for c in m.execute('PRAGMA table_info("products")') if c[3] == 1}
n = 0
if "seller_id" not in nn:
    for pid, sid in m.execute("SELECT id, seller_id FROM products").fetchall():
        if sid and not m.execute("SELECT COUNT(*) FROM sellers WHERE id=?", (sid,)).fetchone()[0]:
            m.execute("UPDATE products SET seller_id=NULL WHERE id=?", (pid,))
            n += 1
print(f"products.seller_id cleared: {n}")

# drop the last few unrecoverable content rows
for child, parent in [("community_answers", "community_posts"),
                      ("community_answers", "users"),
                      ("farmer_profiles", "users")]:
    cc = [c[1] for c in m.execute(f'PRAGMA table_info("{child}")')]
    fk = {f[3]: f[2] for f in m.execute(f'PRAGMA foreign_key_list("{child}")')}
    pcol = next((c for c, p in fk.items() if p == parent), None)
    if not pcol:
        continue
    ids = [x[0] for x in m.execute(f'SELECT id FROM "{child}"').fetchall()]
    killed = 0
    for rid in ids:
        val = m.execute(f'SELECT "{pcol}" FROM "{child}" WHERE id=?', (rid,)).fetchone()[0]
        if val and not m.execute(f'SELECT COUNT(*) FROM "{parent}" WHERE id=?', (val,)).fetchone()[0]:
            m.execute(f'DELETE FROM "{child}" WHERE id=?', (rid,))
            killed += 1
    print(f"  {child} -> {parent}: removed {killed}")

m.commit()
print("integrity_check:", m.execute("PRAGMA integrity_check").fetchall()[:3])
fv = m.execute("PRAGMA foreign_key_check").fetchall()
print(f"FINAL fk violations: {len(fv)}  (base had 9)")
for x in fv:
    print("   ", x)
m.close()
