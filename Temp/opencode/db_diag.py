import sys, sqlite3

path = sys.argv[1]
con = sqlite3.connect(path)
print("file:", path)
try:
    print("quick_check:", con.execute("PRAGMA quick_check").fetchall())
except Exception as e:
    print("quick_check ERR:", e)
try:
    print("integrity_check:", con.execute("PRAGMA integrity_check").fetchall()[:5])
except Exception as e:
    print("integrity ERR:", e)
try:
    rows = con.execute("SELECT name, type FROM sqlite_master ORDER BY type, name").fetchall()
    print("objects:", len(rows))
    for r in rows[:80]:
        print("  ", r)
except Exception as e:
    print("master ERR:", e)
con.close()