import sqlite3
from collections import Counter

for label, p in [
    ("BASE", r"C:\Users\AICOE 5\AppData\Local\Temp\opencode\db_5025cf0.db"),
    ("MERGED_FINAL", r"C:\Users\AICOE 5\AppData\Local\Temp\opencode\merged_final.db"),
]:
    con = sqlite3.connect(p)
    con.execute("PRAGMA foreign_keys=OFF")
    v = con.execute("PRAGMA foreign_key_check").fetchall()
    c = Counter((row[0], row[2]) for row in v)
    print(f"=== {label}: {len(v)} violations ===")
    for (child, parent), n in c.most_common(15):
        cnt = con.execute(f'SELECT COUNT(*) FROM "{child}"').fetchone()[0]
        print(f"  {child} -> {parent}: {n}   (table has {cnt} rows)")
    con.close()
