import sqlite3, os
for p in ["farm_assist.db", "../farm_assist.db"]:
    if os.path.exists(p):
        print("DB:", p, os.path.getsize(p))
        c = sqlite3.connect(p)
        cur = c.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = sorted([r[0] for r in cur.fetchall()])
        print(tables)
        for t in tables:
            if "farmbuzz" in t or t == "users":
                try:
                    cur.execute(f"SELECT count(*) FROM {t}")
                    print(t, "count=", cur.fetchone()[0])
                except Exception as e:
                    print(t, "err", e)
        c.close()
