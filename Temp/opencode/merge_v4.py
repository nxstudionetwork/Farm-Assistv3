import shutil
import sqlite3

BASE = r"C:\Users\AICOE 5\AppData\Local\Temp\opencode\db_5025cf0.db"
REC = r"C:\Users\AICOE 5\AppData\Local\Temp\opencode\farm_recovered.db"
OUT = r"C:\Users\AICOE 5\AppData\Local\Temp\opencode\merged_final.db"

shutil.copyfile(BASE, OUT)
b = sqlite3.connect(OUT)
r = sqlite3.connect(REC)
b.execute("PRAGMA foreign_keys=OFF")
r.execute("PRAGMA foreign_keys=OFF")


def cols(con, t):
    return [x[1] for x in con.execute(f'PRAGMA table_info("{t}")')]


def has(con, t):
    return con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (t,)).fetchone() is not None


# business keys used to recognise "same entity, different UUID" across snapshots
BIZKEY = {
    "users": ["farmer_id", "phone_number"],
    "marketplace_categories": ["slug", "name"],
    "product_categories": ["slug", "name"],
    "products": ["product_id"],
    "farmers": ["farmer_id"],
    "sellers": ["user_id", "gst_number", "phone"],
}

rec_tables = [x[0] for x in r.execute("SELECT name FROM sqlite_master WHERE type='table'")]
rec_tables = [t for t in rec_tables if not t.startswith("sqlite_") and t != "lost_and_found"]

# ---------------------------------------------------------------- maps
idmap = {}          # parent table -> {recovered_id: base_id}
base_rows = {}      # parent table -> {recovered_id: base_row_dict}  (for in-place UPDATE)

for t, keys in BIZKEY.items():
    if not (has(b, t) and has(r, t)):
        continue
    bc = cols(b, t)
    if "id" not in bc:
        continue
    idx = {}
    for k in keys:
        if k not in bc:
            continue
        d = {}
        for row in b.execute(f'SELECT id, "{k}" FROM "{t}" WHERE "{k}" IS NOT NULL'):
            d.setdefault(str(row[1]), []).append(row[0])
        idx[k] = d
    m, rowsmap = {}, {}
    rc = cols(r, t)
    for row in r.execute(f'SELECT {",".join(chr(34)+c+chr(34) for c in rc)} FROM "{t}"'):
        d = dict(zip(rc, row))
        rid = d["id"]
        if rid in m:
            continue
        for k in keys:
            if k not in rc or d.get(k) is None:
                continue
            cand = idx.get(k, {}).get(str(d[k]), [])
            if len(cand) == 1:
                m[rid] = cand[0]
                rowsmap[rid] = (cand[0], d)
                break
    if m:
        idmap[t] = m
        base_rows[t] = rowsmap
        print(f"map {t}: {len(m)} ids remapped")

# ------------------------------------------- users: update base row in place
n_upd = 0
for rid, (bid, d) in base_rows.get("users", {}).items():
    sets = [f'"{c}"=?' for c in cols(r, "users") if c != "id"]
    b.execute(f'UPDATE users SET {",".join(sets)} WHERE id=?',
              [d[c] for c in cols(r, "users") if c != "id"] + [bid])
    n_upd += 1
print(f"users updated in place: {n_upd}")


def fk_map(t):
    """column -> parent table, for the recovered table t"""
    out = {}
    for f in r.execute(f'PRAGMA foreign_key_list("{t}")'):
        out[f[3]] = f[2]
    return out


# ------------------------------------------------- insert everything else
prov = {}
for t in sorted(rec_tables):
    if t == "users":
        continue
    if not r.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]:
        continue
    if not has(b, t):
        print(f"  !! {t} absent in base, skipped")
        continue
    rc, bc = cols(r, t), cols(b, t)
    common = [c for c in rc if c in bc]
    if not common:
        continue
    fks = {c: p for c, p in fk_map(t).items() if c in common}
    pkc = [c[1] for c in b.execute(f'PRAGMA table_info("{t}")') if c[5]] or [common[0]]
    pkc = [c for c in pkc if c in common]
    cl = ",".join(chr(34)+c+chr(34) for c in common)
    ph = ",".join("?" * len(common))
    sql = f'INSERT OR IGNORE INTO "{t}" ({cl}) VALUES ({ph})'
    added = 0
    for row in r.execute(f'SELECT {cl} FROM "{t}"'):
        vals = list(row)
        for c, i in {c: common.index(c) for c in fks}.items():
            p = fks[c]
            mm = idmap.get(p)
            if mm and vals[i] in mm:
                vals[i] = mm[vals[i]]
        b.execute(sql, vals)
        if len(pkc) == 1:
            prov.setdefault(t, {})[str(vals[common.index(pkc[0])])] = vals[common.index(pkc[0])]
        added += 1
    print(f"  {t}: {added}")
b.commit()

# ------------------------- prune dangles, but ONLY from disposable tables
PRUNABLE = {
    "farmer_recently_viewed", "marketplace_cart_items", "marketplace_carts",
    "marketplace_wishlist", "otp_verifications", "message_attachments",
    "saved_news", "community_reports", "technique_bookmarks", "livestock",
    "livestock_health_records", "livestock_vaccinations", "livestock_weight_records",
    "livestock_production_records", "livestock_expense_records",
}
print("--- pruning dangles (disposable tables only) ---")
for _ in range(8):
    viol = b.execute("PRAGMA foreign_key_check").fetchall()
    if not viol:
        break
    bychild = {}
    for child, rowid, parent, fkid in viol:
        bychild.setdefault(child, set()).add(rowid)
    removed = 0
    for child, rowids in bychild.items():
        if child not in PRUNABLE or not has(b, child):
            continue
        pkc = [c[1] for c in b.execute(f'PRAGMA table_info("{child}")') if c[5]] or [cols(b, child)[0]]
        if len(pkc) != 1:
            continue
        keep = prov.get(child, {})
        for rid in rowids:
            got = b.execute(f'SELECT "{pkc[0]}" FROM "{child}" WHERE rowid=?', (rid,)).fetchone()
            if got and str(got[0]) in keep:
                b.execute(f'DELETE FROM "{child}" WHERE "{pkc[0]}"=?', (got[0],))
                removed += 1
    b.commit()
    left = len(b.execute('PRAGMA foreign_key_check').fetchall())
    print(f"  removed {removed}, remaining {left}")
    if removed == 0:
        break

print("integrity_check:", b.execute("PRAGMA integrity_check").fetchall()[:3])
fv = b.execute("PRAGMA foreign_key_check").fetchall()
print(f"FINAL fk violations: {len(fv)} (base had 9)")
for x in fv[:20]:
    print("   ", x)
print("--- key counts ---")
for t in ["users", "products", "product_categories", "marketplace_categories", "techniques",
          "courses", "marketplace_listings", "marketplace_sales", "marketplace_enquiries",
          "marketplace_orders", "notifications", "messages", "conversations",
          "livestock", "community_posts", "community_likes", "farms"]:
    print(f"  {t}: {b.execute(f'SELECT COUNT(*) FROM \"{t}\"').fetchone()[0]}")
b.close()
r.close()
