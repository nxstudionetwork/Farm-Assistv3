import shutil
import sqlite3

SRC = r"C:\Users\AICOE 5\AppData\Local\Temp\opencode\merged_v6.db"
OUT = r"C:\Users\AICOE 5\AppData\Local\Temp\opencode\final.db"
shutil.copyfile(SRC, OUT)

rec = sqlite3.connect(r"C:\Users\AICOE 5\AppData\Local\Temp\opencode\farm_recovered.db")
m = sqlite3.connect(OUT)
m.execute("PRAGMA foreign_keys=OFF")


def cols(con, t):
    return [x[1] for x in con.execute(f'PRAGMA table_info("{t}")')]


def notnull(con, t):
    return {c[1] for c in con.execute(f'PRAGMA table_info("{t}")') if c[3] == 1}


# ---- 1. restore category rows (by slug) so products can resolve -----------
catcols = cols(rec, "product_categories")
missing = []
for cid, slug, name in rec.execute("SELECT id, slug, name FROM product_categories"):
    if m.execute("SELECT COUNT(*) FROM product_categories WHERE id=?", (cid,)).fetchone()[0]:
        continue
    byslug = m.execute("SELECT id FROM product_categories WHERE slug=?", (slug,)).fetchone() if slug else None
    if byslug:
        missing.append((cid, byslug[0]))
    else:
        row = rec.execute("SELECT * FROM product_categories WHERE id=?", (cid,)).fetchone()
        cl = ",".join(chr(34) + c + chr(34) for c in catcols)
        m.execute(f'INSERT OR IGNORE INTO product_categories ({cl}) VALUES ({",".join("?"*len(catcols))})', row)
        print(f"  restored category {name!r} as {cid}")

# ---- 2. repair products whose category still won't resolve ---------------
pc = cols(m, "products")
pnn = notnull(m, "products")
catcol = "category_id" if "category_id" in pc else None
repaired = dropped = 0
if catcol:
    for pid, cid in m.execute(f'SELECT id, "{catcol}" FROM products').fetchall():
        if cid and not m.execute("SELECT COUNT(*) FROM product_categories WHERE id=?", (cid,)).fetchone()[0]:
            if catcol not in pnn:
                m.execute(f'UPDATE products SET "{catcol}"=NULL WHERE id=?', (pid,))
                repaired += 1
            else:
                m.execute("DELETE FROM products WHERE id=?", (pid,))
                dropped += 1
print(f"  products: {repaired} category set NULL, {dropped} dropped")

# ---- 3. prune unrecoverable rows from link/derived tables only ------------
PRUNABLE = {
    "product_crops", "equipment_metadata", "farmer_recently_viewed",
    "marketplace_cart_items", "marketplace_carts", "marketplace_wishlist",
    "otp_verifications", "order_items", "technique_bookmarks", "community_likes",
    "community_saves", "community_comments", "community_group_members",
    "message_attachments", "saved_news", "community_reports",
    "livestock_health_records", "livestock_vaccinations", "livestock_weight_records",
    "livestock_production_records", "livestock_expense_records", "ai_recommendations",
    "user_documents", "user_addresses", "calendar_events", "crop_cycles",
    "wallet_transactions", "sellers", "monitoring_alerts", "monitoring_thresholds",
    "equipment_bookings", "worker_reviews", "feedback", "soil_records",
    "irrigation_records", "farm_reports", "livestock", "delivery_tracking",
}
print("--- pruning unrecoverable link rows ---")
for _ in range(10):
    v = m.execute("PRAGMA foreign_key_check").fetchall()
    if not v:
        break
    bychild = {}
    for child, rowid, parent, fkid in v:
        bychild.setdefault(child, set()).add(rowid)
    n = 0
    for child, rowids in bychild.items():
        if child not in PRUNABLE:
            continue
        cc = cols(m, child)
        for rid in rowids:
            row = m.execute(f'SELECT * FROM "{child}" WHERE rowid=?', (rid,)).fetchone()
            if row:
                m.execute(f'DELETE FROM "{child}" WHERE rowid=?', (rid,))
                n += 1
    m.commit()
    left = len(m.execute("PRAGMA foreign_key_check").fetchall())
    print(f"  removed {n}, remaining {left}")
    if n == 0:
        break

m.commit()
print("integrity_check:", m.execute("PRAGMA integrity_check").fetchall()[:3])
fv = m.execute("PRAGMA foreign_key_check").fetchall()
print(f"FINAL fk violations: {len(fv)}  (base had 9)")
from collections import Counter
for (c, p), n in Counter((x[0], x[2]) for x in fv).most_common(10):
    print(f"   {c} -> {p}: {n}")
print("--- final counts ---")
for t in ["users", "products", "product_categories", "equipment_metadata", "techniques",
          "courses", "community_posts", "community_likes", "community_comments",
          "marketplace_listings", "marketplace_sales", "marketplace_enquiries",
          "marketplace_orders", "order_items", "notifications", "messages",
          "conversations", "livestock", "farms", "soil_records", "irrigation_records",
          "sellers", "market_prices"]:
    print(f"  {t}: {m.execute(f'SELECT COUNT(*) FROM \"{t}\"').fetchone()[0]}")
m.close(); rec.close()
