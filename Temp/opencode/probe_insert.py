import shutil
import sqlite3

src = r"C:\Users\AICOE 5\AppData\Local\Temp\opencode\merged_final.db"
tmp = r"C:\Users\AICOE 5\AppData\Local\Temp\opencode\probe.db"
shutil.copyfile(src, tmp)

rec = sqlite3.connect(r"C:\Users\AICOE 5\AppData\Local\Temp\opencode\farm_recovered.db")
m = sqlite3.connect(tmp)
m.execute("PRAGMA foreign_keys=OFF")

cols = [c[1] for c in rec.execute('PRAGMA table_info("community_posts")')]
cl = ",".join(chr(34) + c + chr(34) for c in cols)
row = rec.execute(
    "SELECT * FROM community_posts WHERE id='c409421d-be65-4b61-9141-0b0d224c23ca'"
).fetchone()
print("recovered row:", dict(zip(cols, row)))

# plain INSERT so the constraint violation is reported instead of swallowed
try:
    m.execute(f'INSERT INTO community_posts ({cl}) VALUES ({",".join("?" * len(cols))})', row)
    print("plain INSERT: SUCCEEDED")
except Exception as e:
    print("plain INSERT FAILED:", type(e).__name__, e)

print("user_id resolves in merged users?",
      m.execute("SELECT COUNT(*) FROM users WHERE id=?", (dict(zip(cols, row))["user_id"],)).fetchone()[0])

print("=== indexes/triggers on community_posts ===")
for r in m.execute("SELECT type, name, sql FROM sqlite_master WHERE tbl_name='community_posts'"):
    print("  ", r[0], r[1], (r[2] or "")[:160])

print("=== how many recovered posts are missing from merged? ===")
missing = rec.execute(
    "SELECT p.id FROM community_posts p "
    "WHERE NOT EXISTS (SELECT 1 FROM main.community_posts q WHERE q.id=p.id)"
).fetchall() if False else None
ids = [x[0] for x in rec.execute("SELECT id FROM community_posts")]
mids = {x[0] for x in m.execute("SELECT id FROM community_posts")}
miss = [i for i in ids if i not in mids]
print(f"  recovered={len(ids)} missing_from_merged={len(miss)}")

# why do they fail? try one that is missing
if miss:
    r2 = rec.execute("SELECT * FROM community_posts WHERE id=?", (miss[0],)).fetchone()
    try:
        m.execute(f'INSERT INTO community_posts ({cl}) VALUES ({",".join("?" * len(cols))})', r2)
        print(f"  missing post {miss[0]} plain INSERT ok -> so it WAS skippable by OR IGNORE on conflict")
    except Exception as e:
        print(f"  missing post {miss[0]} FAILED: {e}")
m.close(); rec.close()
