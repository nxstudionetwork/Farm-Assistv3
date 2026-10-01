import sqlite3

base = r"C:\Users\AICOE 5\AppData\Local\Temp\opencode\db_5025cf0.db"
merged = r"C:\Users\AICOE 5\AppData\Local\Temp\opencode\merged.db"
rec = r"C:\Users\AICOE 5\AppData\Local\Temp\opencode\farm_recovered.db"

def tables(con):
    return {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}

def counts(con):
    out = {}
    for t in tables(con):
        if t.startswith("sqlite_") or t == "lost_and_found":
            continue
        out[t] = con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
    return out

bc, mc, rc = counts(sqlite3.connect(base)), counts(sqlite3.connect(merged)), counts(sqlite3.connect(rec))

print("=== tables where merged < base (REGRESSION) ===")
bad = 0
for t in sorted(bc):
    if mc.get(t, 0) < bc[t]:
        print(f"  {t}: base={bc[t]} merged={mc.get(t)}")
        bad += 1
print("  none" if not bad else f"  {bad} regressions")

print("=== tables where merged > base (gained) ===")
for t in sorted(bc):
    if mc.get(t, 0) > bc[t]:
        print(f"  {t}: base={bc[t]} merged={mc[t]} (+{mc[t]-bc[t]})")

print("=== foreign_key_check on merged ===")
fk = sqlite3.connect(merged)
fk.execute("PRAGMA foreign_keys=OFF")
res = fk.execute("PRAGMA foreign_key_check").fetchall()
print(f"  violations: {len(res)}")
for r in res[:25]:
    print("   ", r)
fk.close()
