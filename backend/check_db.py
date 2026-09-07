import sqlite3
conn = sqlite3.connect("farm_assist.db")
cols = [r[1] for r in conn.execute("PRAGMA table_info(feedback)").fetchall()]
print("Feedback columns:", cols)
conn.close()
