import sqlite3

base = sqlite3.connect(r"C:\Users\AICOE 5\AppData\Local\Temp\opencode\db_5025cf0.db")
print("=== UNIQUE indexes (business keys) per table ===")
for t in ["community_posts", "community_comments", "community_groups", "community_likes",
          "community_saves", "community_answers", "community_group_members",
          "marketplace_listings", "marketplace_sales", "marketplace_orders",
          "marketplace_enquiries", "messages", "conversations", "crops",
          "livestock", "farm_plots", "soil_records", "irrigation_records",
          "products", "equipment_metadata", "sellers", "farmers", "notifications"]:
    try:
        idx = [r[0] for r in base.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name=? AND sql LIKE '%UNIQUE%'", (t,))]
        cols = [c[1] for c in base.execute(f'PRAGMA table_info("{t}")')]
        bk = [c for c in cols if c.endswith("_id") and c not in ("id", "user_id")]
        n = base.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
        print(f"  {t:26} rows={n:6}  keycols={bk}  uniq_idx={idx}")
    except Exception as e:
        print(f"  {t}: ERR {e}")
base.close()
