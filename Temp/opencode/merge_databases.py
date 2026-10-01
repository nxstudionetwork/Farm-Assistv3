import sqlite3

src_path = r"C:\Users\AICOE 5\AppData\Local\Temp\opencode\farm_recovered.db"
base_path = r"C:\Users\AICOE 5\AppData\Local\Temp\opencode\db_5025cf0.db"
out_path = r"C:\Users\AICOE 5\AppData\Local\Temp\opencode\merged.db"

# First, copy base_path to out_path
import shutil
shutil.copyfile(base_path, out_path)

src_con = sqlite3.connect(src_path)
out_con = sqlite3.connect(out_path)

# Find all tables in src that have > 0 rows
tables_with_rows = []
for (tname,) in src_con.execute("SELECT name FROM sqlite_master WHERE type='table'"):
    if tname.startswith("sqlite_") or tname == "lost_and_found":
        continue
    try:
        cnt = src_con.execute(f"SELECT COUNT(*) FROM \"{tname}\"").fetchone()[0]
        if cnt > 0:
            tables_with_rows.append((tname, cnt))
    except Exception:
        pass

print("Tables with rows in recovered:", len(tables_with_rows))

for tname, cnt in sorted(tables_with_rows, key=lambda x: x[0]):
    # check if table exists in out_con
    exists = out_con.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?", (tname,)).fetchone()[0]
    if not exists:
        print(f"Table {tname} does not exist in target! Creating schema...")
        sql = src_con.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (tname,)).fetchone()[0]
        if sql:
            out_con.execute(sql)
    
    # get column names
    src_cols = [r[1] for r in src_con.execute(f"PRAGMA table_info(\"{tname}\")").fetchall()]
    out_cols = [r[1] for r in out_con.execute(f"PRAGMA table_info(\"{tname}\")").fetchall()]
    
    common_cols = [c for c in src_cols if c in out_cols]
    if not common_cols:
        continue
    
    col_str = ", ".join(f"\"{c}\"" for c in common_cols)
    placeholders = ", ".join(["?"] * len(common_cols))
    
    rows = src_con.execute(f"SELECT {col_str} FROM \"{tname}\"").fetchall()
    
    # Use INSERT OR REPLACE so latest records from recovered overwrite stale ones
    query = f"INSERT OR REPLACE INTO \"{tname}\" ({col_str}) VALUES ({placeholders})"
    inserted = 0
    for r in rows:
        try:
            out_con.execute(query, r)
            inserted += 1
        except Exception as e:
            # fallback to INSERT OR IGNORE
            try:
                out_con.execute(f"INSERT OR IGNORE INTO \"{tname}\" ({col_str}) VALUES ({placeholders})", r)
                inserted += 1
            except Exception as e2:
                print(f"Error inserting into {tname}: {e2}")
    print(f"Merged {tname}: {inserted}/{cnt} rows")

out_con.commit()

# Check quick_check on merged
q = out_con.execute("PRAGMA quick_check").fetchall()
print("quick_check on merged:", q)

out_con.close()
src_con.close()
