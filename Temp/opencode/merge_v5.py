import shutil
import sqlite3

BASE = r"C:\Users\AICOE 5\AppData\Local\Temp\opencode\db_5025cf0.db"
REC = r"C:\Users\AICOE 5\AppData\Local\Temp\opencode\farm_recovered.db"
OUT = r"C:\Users\AICOE 5\AppData\Local\Temp\opencode\merged_v5.db"

shutil.copyfile(BASE, OUT)
b = sqlite3.connect(OUT)
r = sqlite3.connect(REC)
b.execute("PRAGMA foreign_keys=OFF")
r.execute("PRAGMA foreign_keys=OFF")


def cols(con, t):
    return [x[1] for x in con.execute(f'PRAGMA table_info("{t}")')]


def has(con, t):
    return con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (t,)).fetchone() is not None


# table -> business key column(s). UPDATE = recovered row overwrites base row in place
# (base UUID kept so children stay valid). MAPONLY = only build id map, never overwrite.
UPDATE = {
    "users": ["farmer_id", "phone_number"],
    "community_posts": ["post_id"],
    "community_groups": ["community_id"],
    "community_answers": ["answer_id"],
    "marketplace_listings": ["listing_id"],
    "marketplace_sales": ["sale_id"],
    "marketplace_orders": ["order_id"],
    "messages": ["message_id"],
    "conversations": ["conversation_id"],
    "crops": ["crop_id"],
    "livestock": ["animal_id"],
    "farm_plots": ["plot_id"],
    "notifications": ["notification_id"],
    "sellers": ["seller_id"],
    "equipment_metadata": ["product_id"],
}
MAPONLY = {
    "products": ["product_id"],
    "product_categories": ["slug", "name"],
    "marketplace_categories": ["slug", "name"],
}

rec_tables = [x[0] for x in r.execute("SELECT name FROM sqlite_master WHERE type='table'")]
rec_tables = [t for t in rec_tables if not t.startswith("sqlite_") and t != "lost_and_found"]

# ---------------------------------------------------- build id maps
idmap, upd = {}, {}
for t, keys in list(UPDATE.items()) + list(MAPONLY.items()):
    if not (has(b, t) and has(r, t)):
        continue
    bc = cols(b, t)
    if "id" not in bc:
        continue
    idx = {}
    for k in keys:
        if k in bc:
            d = {}
            for row in b.execute(f'SELECT id, "{k}" FROM "{t}" WHERE "{k}" IS NOT NULL'):
                d.setdefault(str(row[1]), []).append(row[0])
            idx[k] = d
    m, pairs = {}, []
    rc = cols(r, t)
    for row in r.execute(f'SELECT {",".join(chr(34)+c+chr(34) for c in rc)} FROM "{t}"'):
        d = dict(zip(rc, row))
        if d["id"] in m:
            continue
        for k in keys:
            if k not in rc or d.get(k) is None:
                continue
            cand = idx.get(k, {}).get(str(d[k]), [])
            if len(cand) == 1:
                m[d["id"]] = cand[0]
                if t in UPDATE:
                    pairs.append((cand[0], d))
                break
    if m:
        idmap[t] = m
        print(f"  map {t:24} {len(m):6} ids")
    if t in UPDATE and pairs:
        upd[t] = pairs

# ------------------------------------------- update-in-place (keep base UUID)
for t, pairs in upd.items():
    bc = cols(b, t)
    nonid = [c for c in cols(r, t) if c != "id" and c in bc]
    if not nonid:
        continue
    sets = ",".join(f'"{c}"=?' for c in nonid)
    n = 0
    for bid, d in pairs:
        b.execute(f'UPDATE "{t}" SET {sets} WHERE id=?', [d[c] for c in nonid] + [bid])
        n += 1
    print(f"  updated {t}: {n}")

# ------------------------------------------- insert remaining recovered rows
skipped = {}
for t in sorted(rec_tables):
    if t in UPDATE or t in MAPONLY:
        continue
    n = rec_n = r.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
    if not rec_n or not has(b, t):
        continue
    rc, bc = cols(r, t), cols(b, t)
    common = [c for c in rc if c in bc]
    if not common:
        continue
    fk = {}
    for f in r.execute(f'PRAGMA foreign_key_list("{t}")'):
        if f[3] in common:
            fk[common.index(f[3])] = f[2]
    cl = ",".join(chr(34) + c + chr(34) for c in common)
    ph = ",".join("?" * len(common))
    before = b.total_changes
    for row in r.execute(f'SELECT {cl} FROM "{t}"'):
        vals = list(row)
        for i, parent in fk.items():
            mm = idmap.get(parent)
            if mm and vals[i] in mm:
                vals[i] = mm[vals[i]]
        b.execute(f'INSERT OR IGNORE INTO "{t}" ({cl}) VALUES ({ph})', vals)
    got = b.total_changes - before
    if got != rec_n:
        skipped[t] = rec_n - got
b.commit()

print("--- inserted ---")
for t, n in sorted(skipped.items(), key=lambda x: -x[1])[:15]:
    print(f"  {t}: {n} rows already present (deduped)")

print("integrity_check:", b.execute("PRAGMA integrity_check").fetchall()[:3])
fv = b.execute("PRAGMA foreign_key_check").fetchall()
print(f"FINAL fk violations: {len(fv)}   (base = 9)")
from collections import Counter
for (c, p), n in Counter((x[0], x[2]) for x in fv).most_common(12):
    print(f"   {c} -> {p}: {n}")
print("--- key counts ---")
for t in ["users", "products", "community_posts", "community_likes", "community_comments",
          "community_groups", "marketplace_listings", "marketplace_sales",
          "marketplace_enquiries", "marketplace_orders", "notifications", "messages",
          "conversations", "livestock", "farms", "soil_records"]:
    print(f"  {t}: {b.execute(f'SELECT COUNT(*) FROM \"{t}\"').fetchone()[0]}")
b.close()
r.close()
