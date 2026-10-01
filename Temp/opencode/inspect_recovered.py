import sqlite3

con = sqlite3.connect(r"C:\Users\AICOE 5\AppData\Local\Temp\opencode\farm_recovered.db")
print("--- users in recovered ---")
for r in con.execute("SELECT id, farmer_id, full_name, phone_number, created_at FROM users"):
    print(r)
print("--- marketplace_listings in recovered ---")
for r in con.execute("SELECT id, title, quantity, price, user_id, status FROM marketplace_listings"):
    print(r)
print("--- marketplace_sales in recovered ---")
for r in con.execute("SELECT id, sale_id, buyer_name, total_amount, status, created_at FROM marketplace_sales"):
    print(r)
con.close()
