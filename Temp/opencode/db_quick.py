import sys, sqlite3, io

path = sys.argv[1]
con = sqlite3.connect(path)
try:
    q = con.execute("PRAGMA quick_check").fetchone()[0]
    print(f"{path}\n  quick_check={q}")
    if q == "ok":
        for tbl in ("users","marketplace_listings","marketplace_sales","products","notifications","marketplace_enquiries"):
            try:
                c = con.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
                print(f"    {tbl}={c}")
            except Exception as e:
                print(f"    {tbl}=ERR:{e}")
        try:
            m = con.execute("SELECT MAX(created_at) FROM messages").fetchone()[0]
            print(f"    latest_message={m}")
        except Exception:
            pass
except Exception as e:
    print(f"{path}\n  ERR={e}")
con.close()