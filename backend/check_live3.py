import sys, os
sys.path.insert(0, "backend")
os.environ.pop("DATABASE_URL", None)
from sqlalchemy import text
from app.database.connection import engine
with engine.connect() as conn:
    rows = conn.execute(text("SELECT c.slug, COUNT(p.id) AS n FROM products p JOIN product_categories c ON p.category_id=c.id WHERE p.is_active=1 GROUP BY c.slug ORDER BY c.slug")).fetchall()
    for slug, n in rows:
        print(f"{slug}: {n}")
    print("TOTAL ACTIVE:", conn.execute(text("SELECT COUNT(*) FROM products WHERE is_active=1")).scalar())
    print("TOTAL PRODUCTS:", conn.execute(text("SELECT COUNT(*) FROM products")).scalar())
