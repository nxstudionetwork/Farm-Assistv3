import sqlite3

rec = sqlite3.connect(r"C:\Users\AICOE 5\AppData\Local\Temp\opencode\farm_recovered.db")
base = sqlite3.connect(r"C:\Users\AICOE 5\AppData\Local\Temp\opencode\db_5025cf0.db")
mg = sqlite3.connect(r"C:\Users\AICOE 5\AppData\Local\Temp\opencode\merged_final.db")

print("=== do recovered community_posts rows actually insert? (NOT NULL check) ===")
cols = [c[1] for c in rec.execute('PRAGMA table_info("community_posts")')]
nn = [c[1] for c in rec.execute('PRAGMA table_info("community_posts")') if c[3] == 1]
print("  NOT NULL cols:", nn)
bad = 0
for c in nn:
    n = rec.execute(f'SELECT COUNT(*) FROM community_posts WHERE "{c}" IS NULL').fetchone()[0]
    if n:
        print(f"    {c} IS NULL in {n} recovered rows")
        bad += n
print("  total rows blocked by NOT NULL:", bad)

print("=== sample dangling community_likes ===")
d = mg.execute("PRAGMA foreign_key_check").fetchall()
lk = [x for x in d if x[0] == "community_likes"][:3]
lc = [c[1] for c in mg.execute('PRAGMA table_info("community_likes")')]
for x in lk:
    row = mg.execute("SELECT * FROM community_likes WHERE rowid=?", (x[1],)).fetchone()
    pid = dict(zip(lc, row)).get("post_id")
    print(f"  like rowid={x[1]} post_id={pid}")
    print(f"    in merged posts : {mg.execute('SELECT COUNT(*) FROM community_posts WHERE id=?', (pid,)).fetchone()[0]}")
    print(f"    in recovered    : {rec.execute('SELECT COUNT(*) FROM community_posts WHERE id=?', (pid,)).fetchone()[0]}")
    print(f"    in base         : {base.execute('SELECT COUNT(*) FROM community_posts WHERE id=?', (pid,)).fetchone()[0]}")

print("=== counts: recovered vs merged community_posts ===")
print("  recovered posts:", rec.execute("SELECT COUNT(*) FROM community_posts").fetchone()[0])
print("  merged posts   :", mg.execute("SELECT COUNT(*) FROM community_posts").fetchone()[0])
print("  base posts     :", base.execute("SELECT COUNT(*) FROM community_posts").fetchone()[0])
print("  recovered likes:", rec.execute("SELECT COUNT(*) FROM community_likes").fetchone()[0])
print("  recovered likes w/ valid post:",
      rec.execute("SELECT COUNT(*) FROM community_likes l JOIN community_posts p ON l.post_id=p.id").fetchone()[0])
rec.close(); base.close(); mg.close()
