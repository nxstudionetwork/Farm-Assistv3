import sys, sqlite3

for path in sys.argv[1:]:
    try:
        con = sqlite3.connect(path)
        users = con.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        listings = con.execute("SELECT COUNT(*) FROM marketplace_listings").fetchone()[0]
        products = con.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        notif = con.execute("SELECT COUNT(*) FROM notifications").fetchone()[0]
        sales = con.execute("SELECT COUNT(*) FROM marketplace_sales").fetchone()[0]
        max_msg = con.execute("SELECT MAX(created_at) FROM messages").fetchone()[0]
        print(f"{path}")
        print(f"  users={users} listings={listings} products={products} notif={notif} sales={sales}")
        print(f"  latest message={max_msg}")
        con.close()
    except Exception as e:
        print(path, "ERR", e)