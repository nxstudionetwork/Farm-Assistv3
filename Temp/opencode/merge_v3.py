import shutil
import sqlite3

BASE = r"C:\Users\AICOE 5\AppData\Local\Temp\opencode\db_5025cf0.db"
REC = r"C:\Users\AICOE 5\AppData\Local\Temp\opencode\farm_recovered.db"
OUT = r"C:\Users\AICOE 5\AppData\Local\Temp\opencode\merged3.db"

shutil.copyfile(BASE, OUT)
b = sqlite3.connect(OUT)
r = sqlite3.connect(REC)
b.execute("PRAGMA foreign_keys=OFF")
r.execute("PRAGMA foreign_keys=OFF")


def cols(con, t):
    return [x[1] for x in con.execute(f'PRAGMA table_info("{t}")')]


def exists(con, t):
    return con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (t,)).fetchone() is not None


def pk_cols(con, t):
    out = [x[1] for x in con.execute(f'PRAGMA table_info("{t}")') if x[5]]
    return out or [cols(con, t)[0]]


rec_tables = [x[0] for x in r.execute("SELECT name FROM sqlite_master WHERE type='table'")]
rec_tables = [t for t in rec_tables if not t.startswith("sqlite_") and t != "lost_and_found"]

# ---- users: update base rows in place, keyed on farmer_id then phone ----
ruc = cols(r, "users")
by_farmer, by_phone = {}, {}
for uid, fid in b.execute("SELECT id, farmer_id FROM users WHERE farmer_id IS NOT NULL"):
    by_farmer.setdefault(fid, []).append(uid)
for uid, ph in b.execute("SELECT id, phone_number FROM users WHERE phone_number IS NOT NULL"):
    by_phone.setdefault(ph, []).append(uid)

id_map, upd, newu = [], [], []
for row in r.execute(f'SELECT {",".join(chr(34)+c+chr(34) for c in ruc)} FROM users'):
    rec = dict(zip(ruc, row))
    tgt = None
    if rec.get("farmer_id") and len(by_farmer.get(rec["farmer_id"], [])) == 1:
        tgt = by_farmer[rec["farmer_id"]][0]
    elif rec.get("phone_number") and len(by_phone.get(rec["phone_number"], [])) == 1:
        tgt = by_phone[rec["phone_number"]][0]
    if tgt:
        id_map.append((rec["id"], tgt))
        sets = [f'"{c}"=?' for c in ruc if c != "id"]
        upd.append((sets, [rec[c] for c in ruc if c != "id"] + [tgt]))
    else:
        newu.append(tuple(rec[c] for c in ruc))
for sets, v in upd:
    b.execute(f'UPDATE users SET {",".join(sets)} WHERE id=?', v)
for v in newu:
    b.execute(f'INSERT OR IGNORE INTO users ({",".join(chr(34)+c+chr(34) for c in ruc)}) VALUES ({",".join("?"*len(ruc))})', v)
id_map = dict(id_map)
print(f"users: {len(upd)} updated, {len(newu)} new, {len(id_map)} uuid remapped")

# ---- provenance: which PKs came from recovered ----
prov = {}

fkcache = {}


def user_fk(con, t):
    if t not in fkcache:
        fkcache[t] = [f[3] for f in con.execute(f'PRAGMA foreign_key_list("{t}")') if f[2] == "users"]
    return fkcache[t]


for t in sorted(rec_tables):
    if t == "users":
        continue
    if not r.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]:
        continue
    if not exists(b, t):
        continue
    rc, bc = cols(r, t), cols(b, t)
    common = [c for c in rc if c in bc]
    if not common:
        continue
    pkc = [c for c in pk_cols(b, t) if c in common]
    fki = {c: common.index(c) for c in user_fk(r, t) if c in common}
    cl = ",".join(chr(34)+c+chr(34) for c in common)
    ph = ",".join("?" * len(common))
    for row in r.execute(f'SELECT {cl} FROM "{t}"'):
        vals = list(row)
        for c, i in fki.items():
            if vals[i] in id_map:
                vals[i] = id_map[vals[i]]
        b.execute(f'INSERT OR IGNORE INTO "{t}" ({cl}) VALUES ({ph})', vals)
        prov.setdefault(t, set()).add(tuple(vals[common.index(c)] for c in pkc))

b.commit()

# ---- prune only recovered-origin rows that dangle ----
print("--- pruning dangling recovered rows ---")
for _ in range(6):
    viol = b.execute("PRAGMA foreign_key_check").fetchall()
    if not viol:
        break
    bychild = {}
    for child, rowid, parent, fkid in viol:
        bychild.setdefault(child, set()).add((rowid, parent))
    removed = 0
    for child, refs in bychild.items():
        if not exists(b, child):
            continue
        pk = pk_cols(b, child)
        keep = prov.get(child, set())
        if not keep or len(pk) != 1:
            continue
        idmap = {str(k[0]): k[0] for k in keep}
        for rowid, _parent in refs:
            got = b.execute(f'SELECT "{pk[0]}" FROM "{child}" WHERE rowid=?', (rowid,)).fetchone()
            if not got:
                continue
            if str(got[0]) in idmap:
                b.execute(f'DELETE FROM "{child}" WHERE "{pk[0]}"=?', (got[0],))
                removed += 1
    b.commit()
    print(f"  pass: removed {removed}, remaining {len(b.execute('PRAGMA foreign_key_check').fetchall())}")
    if removed == 0:
        break

print("integrity_check:", b.execute("PRAGMA integrity_check").fetchall()[:3])
fv = b.execute("PRAGMA foreign_key_check").fetchall()
print(f"final fk violations: {len(fv)}")
for x in fv[:15]:
    print("   ", x)
for t in ["users", "products", "techniques", "courses", "marketplace_sales", "marketplace_listings", "notifications", "livestock", "community_posts"]:
    print(f"  {t}: {b.execute(f'SELECT COUNT(*) FROM \"{t}\"').fetchone()[0]}")
b.close()
r.close()
