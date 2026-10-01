import shutil
import sqlite3

BASE = r"C:\Users\AICOE 5\AppData\Local\Temp\opencode\db_5025cf0.db"
REC = r"C:\Users\AICOE 5\AppData\Local\Temp\opencode\farm_recovered.db"
OUT = r"C:\Users\AICOE 5\AppData\Local\Temp\opencode\merged_v6.db"

shutil.copyfile(BASE, OUT)
b = sqlite3.connect(OUT)
r = sqlite3.connect(REC)
b.execute("PRAGMA foreign_keys=OFF")
r.execute("PRAGMA foreign_keys=OFF")


def cols(con, t):
    return [x[1] for x in con.execute(f'PRAGMA table_info("{t}")')]


def has(con, t):
    return con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (t,)).fetchone() is not None


def fkmap(con, t):
    """column index -> parent table"""
    out = {}
    for f in con.execute(f'PRAGMA foreign_key_list("{t}")'):
        out[f[3]] = f[2]
    return out


# business keys; UPDATE = overwrite base row in place (keep base UUID)
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

# ------------------------------------------------------------ 1. id maps
idmap = {}
for t, keys in list(UPDATE.items()) + list(MAPONLY.items()):
    if not (has(b, t) and has(r, t)) or "id" not in cols(b, t):
        continue
    bc = cols(b, t)
    idx = {}
    for k in keys:
        if k in bc:
            d = {}
            for row in b.execute(f'SELECT id, "{k}" FROM "{t}" WHERE "{k}" IS NOT NULL'):
                d.setdefault(str(row[1]), []).append(row[0])
            idx[k] = d
    m = {}
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
                break
    if m:
        idmap[t] = m
        print(f"  map {t:24} {len(m):6}")


def remap(t, d, common):
    """rewrite FK values of a recovered row dict onto base UUIDs"""
    fk = fkmap(r, t)
    out = dict(d)
    for col, parent in fk.items():
        if col in common and out.get(col) in idmap.get(parent, {}):
            out[col] = idmap[parent][out[col]]
    return out


# ------------------------------------------- 2. upsert every recovered table
stats = {}
# users first so identity is settled before content rows
order = ["users"] + [t for t in sorted(rec_tables) if t != "users"]

for t in order:
    nrec = r.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
    if not nrec or not has(b, t):
        continue
    rc, bc = cols(r, t), cols(b, t)
    common = [c for c in rc if c in bc]
    if "id" not in common:
        continue
    cl = ",".join(chr(34) + c + chr(34) for c in common)
    ph = ",".join("?" * len(common))
    m = idmap.get(t, {})
    is_upd = t in UPDATE
    nup = nins = nskip = 0
    nonid = [c for c in common if c != "id"]
    sets = ",".join(f'"{c}"=?' for c in nonid)

    for row in r.execute(f'SELECT {cl} FROM "{t}"'):
        d = remap(t, dict(zip(common, row)), common)
        if d["id"] in m:
            if is_upd:
                b.execute(f'UPDATE "{t}" SET {sets} WHERE id=?',
                          [d[c] for c in nonid] + [m[d["id"]]])
                nup += 1
            else:
                nskip += 1
        else:
            b.execute(f'INSERT OR IGNORE INTO "{t}" ({cl}) VALUES ({ph})',
                      [d[c] for c in common])
            nins += 1
    stats[t] = (nup, nins, nskip)

b.commit()
print("--- upsert (updated / inserted / skipped-dup) ---")
for t in ["users", "community_posts", "marketplace_listings", "marketplace_sales",
          "marketplace_enquiries", "marketplace_orders", "messages", "conversations",
          "community_likes", "products", "notifications"]:
    if t in stats:
        print(f"  {t:24} {stats[t]}")

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
          "conversations", "livestock", "farms", "soil_records", "irrigation_records"]:
    print(f"  {t}: {b.execute(f'SELECT COUNT(*) FROM \"{t}\"').fetchone()[0]}")
b.close()
r.close()
