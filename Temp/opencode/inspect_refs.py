import sqlite3

rec = sqlite3.connect(r"C:\Users\AICOE 5\AppData\Local\Temp\opencode\farm_recovered.db")
base = sqlite3.connect(r"C:\Users\AICOE 5\AppData\Local\Temp\opencode\db_5025cf0.db")

for t in ["marketplace_listings", "marketplace_sales", "marketplace_enquiries"]:
    print("=" * 50)
    print(t)
    print("  FKs:", [(f[3], f[2]) for f in rec.execute(f'PRAGMA foreign_key_list("{t}")')])
    cols = [c[1] for c in rec.execute(f'PRAGMA table_info("{t}")')]
    for row in rec.execute(f'SELECT * FROM "{t}"'):
        d = dict(zip(cols, row))
        keys = {k: v for k, v in d.items() if k.endswith("_id") and v}
        print("   ", {k: d[k] for k in ("id", "title", "sale_id", "buyer_name", "total_amount", "status") if k in d})
        for k, v in keys.items():
            # does it resolve in recovered?
            inrec = rec.execute(f'SELECT COUNT(*) FROM users WHERE id=?', (v,)).fetchone()[0] if k in ("user_id", "seller_id", "buyer_id") else None
            inbase_products = base.execute('SELECT COUNT(*) FROM products WHERE id=?', (v,)).fetchone()[0]
            inbase_list = base.execute('SELECT COUNT(*) FROM marketplace_listings WHERE id=?', (v,)).fetchone()[0]
            print(f"       {k}={v}  usersInRec={inrec} productInBase={inbase_products} listingInBase={inbase_list}")
rec.close()
base.close()
