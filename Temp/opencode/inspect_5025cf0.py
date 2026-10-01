import sqlite3

con = sqlite3.connect(r"C:\Users\AICOE 5\AppData\Local\Temp\opencode\db_5025cf0.db")
print("--- users in 5025cf0 with phone 6301268629 or name Harsha ---")
for r in con.execute("SELECT id, farmer_id, full_name, phone_number, created_at FROM users WHERE phone_number LIKE '%6301268629%' OR full_name LIKE '%Harsha%'"):
    print(r)

print("--- listings in 5025cf0 ---")
for r in con.execute("SELECT id, title, quantity, price, user_id, status FROM marketplace_listings"):
    print(r)

print("--- sales in 5025cf0 ---")
for r in con.execute("SELECT id, sale_id, buyer_name, total_amount, status, created_at FROM marketplace_sales"):
    print(r)
con.close()
