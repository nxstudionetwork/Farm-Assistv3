import sqlite3

for label, path in [
    ("base 5025cf0", r"C:\Users\AICOE 5\AppData\Local\Temp\opencode\db_5025cf0.db"),
    ("recovered", r"C:\Users\AICOE 5\AppData\Local\Temp\opencode\farm_recovered.db"),
    ("merged", r"C:\Users\AICOE 5\AppData\Local\Temp\opencode\merged.db"),
]:
    con = sqlite3.connect(path)
    con.execute("PRAGMA foreign_keys=OFF")
    n = len(con.execute("PRAGMA foreign_key_check").fetchall())
    print(f"{label}: fk violations = {n}")
    con.close()
