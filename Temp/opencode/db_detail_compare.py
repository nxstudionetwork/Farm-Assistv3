import sys, sqlite3

def summarize(path):
    print("=" * 60)
    print("FILE:", path)
    con = sqlite3.connect(path)
    try:
        tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()]
        print(f"Total tables: {len(tables)}")
        for t in ["users", "farmer_profiles", "farms", "crops", "products", "marketplace_listings", "marketplace_sales", "notifications", "courses", "techniques", "agricultural_services", "equipment"]:
            if t in tables:
                c = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                print(f"  {t}: {c}")
            else:
                print(f"  {t}: NOT FOUND")
        # Check latest timestamps
        for t, col in [("users", "created_at"), ("messages", "created_at"), ("notifications", "created_at"), ("community_posts", "created_at")]:
            if t in tables:
                try:
                    m = con.execute(f"SELECT MAX({col}) FROM {t}").fetchone()[0]
                    print(f"  max {t}.{col}: {m}")
                except Exception as e:
                    print(f"  max {t}.{col}: err {e}")
    finally:
        con.close()

summarize(sys.argv[1])
summarize(sys.argv[2])
