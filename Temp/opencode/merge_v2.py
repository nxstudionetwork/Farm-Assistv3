import shutil
import sqlite3

BASE = r"C:\Users\AICOE 5\AppData\Local\Temp\opencode\db_5025cf0.db"
REC = r"C:\Users\AICOE 5\AppData\Local\Temp\opencode\farm_recovered.db"
OUT = r"C:\Users\AICOE 5\AppData\Local\Temp\opencode\merged2.db"

shutil.copyfile(BASE, OUT)

b = sqlite3.connect(OUT)
r = sqlite3.connect(REC)
b.execute("PRAGMA foreign_keys=OFF")
r.execute("PRAGMA foreign_keys=OFF")


def cols(con, t):
    return [x[1] for x in con.execute(f'PRAGMA table_info("{t}")')]


def exists(con, t):
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (t,)
    ).fetchone() is not None


rec_tables = [
    x[0] for x in r.execute("SELECT name FROM sqlite_master WHERE type='table'")
]
rec_tables = [t for t in rec_tables if not t.startswith("sqlite_") and t != "lost_and_found"]

# ---------------------------------------------------------------- 1. users
# Recovered users are the SAME logical people as base users (same farmer_id)
# but with a different PK and newer field values. Update the base row in place
# so every child row that references the base UUID stays valid.
rec_user_cols = cols(r, "users")
base_by_farmer = {}
for uid, fid in b.execute("SELECT id, farmer_id FROM users WHERE farmer_id IS NOT NULL"):
    base_by_farmer.setdefault(fid, []).append(uid)
base_by_phone = {}
for uid, ph in b.execute("SELECT id, phone_number FROM users WHERE phone_number IS NOT NULL"):
    base_by_phone.setdefault(ph, []).append(uid)

id_map = {}
updates, inserts = [], []
for row in r.execute(f'SELECT {",".join(chr(34)+c+chr(34) for c in rec_user_cols)} FROM users'):
    rec = dict(zip(rec_user_cols, row))
    rec_id = rec["id"]
    target = None
    if rec.get("farmer_id") and len(base_by_farmer.get(rec["farmer_id"], [])) == 1:
        target = base_by_farmer[rec["farmer_id"]][0]
    elif rec.get("phone_number") and len(base_by_phone.get(rec["phone_number"], [])) == 1:
        target = base_by_phone[rec["phone_number"]][0]

    if target:
        id_map[rec_id] = target
        sets, vals = [], []
        for c in rec_user_cols:
            if c == "id":
                continue
            sets.append(f'"{c}"=?')
            vals.append(rec[c])
        updates.append((sets, [target] + vals))
    else:
        inserts.append(tuple(rec[c] for c in rec_user_cols))

for sets, vals in updates:
    b.execute(f'UPDATE users SET {",".join(sets)} WHERE id=?', vals)
for vals in inserts:
    ph = ",".join("?" * len(rec_user_cols))
    b.execute(
        f'INSERT OR IGNORE INTO users ({",".join(chr(34)+c+chr(34) for c in rec_user_cols)}) VALUES ({ph})',
        vals,
    )
print(f"users: {len(updates)} updated in place, {len(inserts)} inserted new, {len(id_map)} UUIDs remapped")

# ------------------------------------------------- 2. every other table
user_fk_cache = {}


def user_fk_cols(con, t):
    """columns of t that reference users(id)"""
    if t not in user_fk_cache:
        got = []
        for fk in con.execute(f'PRAGMA foreign_key_list("{t}")'):
            if fk[2] == "users":
                got.append(fk[3])
        user_fk_cache[t] = got
    return user_fk_cache[t]


remapped_rows = 0
for t in sorted(rec_tables):
    if t == "users":
        continue
    n = r.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
    if not n:
        continue
    if not exists(b, t):
        print(f"  !! {t} missing in base - skipped")
        continue

    rc, bc = cols(r, t), cols(b, t)
    common = [c for c in rc if c in bc]
    if not common:
        continue
    fkcols = [c for c in user_fk_cols(r, t) if c in common]
    fk_idx = {c: common.index(c) for c in fkcols}

    collist = ",".join(chr(34) + c + chr(34) for c in common)
    ph = ",".join("?" * len(common))
    sql = f'INSERT OR IGNORE INTO "{t}" ({collist}) VALUES ({ph})'

    added = 0
    for row in r.execute(f'SELECT {collist} FROM "{t}"'):
        vals = list(row)
        for c, i in fk_idx.items():
            if vals[i] in id_map:
                vals[i] = id_map[vals[i]]
                remapped_rows += 1
        b.execute(sql, vals)
        added += 1
    print(f"  {t}: {added}/{n}")

b.commit()
print(f"total user-FK values remapped: {remapped_rows}")
print("integrity_check:", b.execute("PRAGMA integrity_check").fetchall()[:3])
fk = b.execute("PRAGMA foreign_key_check").fetchall()
print(f"fk violations: {len(fk)}")
for x in fk[:20]:
    print("   ", x)
b.close()
r.close()
