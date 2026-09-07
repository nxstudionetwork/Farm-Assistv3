import sqlite3
conn = sqlite3.connect('farm_assist.db')
c = conn.cursor()

# Users
c.execute("SELECT id, farmer_id, full_name, phone_number, email, profile_image FROM users")
for r in c.fetchall():
    print(f"User: id={r[0]}, farmer_id={r[1]}, name={r[2]}, phone={r[3]}, email={r[4]}, img={r[5]}")

# Farmer profiles
try:
    c.execute("PRAGMA table_info(farmer_profiles)")
    print("\nFARMER_PROFILES columns:", [(r[1], r[2]) for r in c.fetchall()])
    c.execute("SELECT * FROM farmer_profiles LIMIT 5")
    for r in c.fetchall():
        print(f"  FP: {r}")
except Exception as e:
    print(f"farmer_profiles error: {e}")

# User addresses
try:
    c.execute("PRAGMA table_info(user_addresses)")
    print("\nUSER_ADDRESSES columns:", [(r[1], r[2]) for r in c.fetchall()])
    c.execute("SELECT * FROM user_addresses LIMIT 5")
    for r in c.fetchall():
        print(f"  UA: {r}")
except Exception as e:
    print(f"user_addresses error: {e}")

# Farm documents
try:
    c.execute("PRAGMA table_info(farm_documents)")
    print("\nFARM_DOCUMENTS columns:", [(r[1], r[2]) for r in c.fetchall()])
    c.execute("SELECT * FROM farm_documents LIMIT 5")
    for r in c.fetchall():
        print(f"  FD: {r}")
except Exception as e:
    print(f"farm_documents error: {e}")

# Farms
try:
    c.execute("SELECT id, farm_id, user_id, farm_name, total_area, area_unit FROM farms")
    for r in c.fetchall():
        print(f"Farm: id={r[0]}, farm_id={r[1]}, user_id={r[2]}, name={r[3]}, area={r[4]} {r[5]}")
except Exception as e:
    print(f"farms error: {e}")

# Farm plots
try:
    c.execute("SELECT id, plot_id, farm_id, plot_name, area FROM farm_plots")
    for r in c.fetchall():
        print(f"Plot: id={r[0]}, plot_id={r[1]}, farm_id={r[2]}, name={r[3]}, area={r[4]}")
except Exception as e:
    print(f"farm_plots error: {e}")

# Login history
try:
    c.execute("PRAGMA table_info(login_history)")
    print("\nLOGIN_HISTORY columns:", [(r[1], r[2]) for r in c.fetchall()])
    c.execute("SELECT * FROM login_history ORDER BY created_at DESC LIMIT 5")
    for r in c.fetchall():
        print(f"  LH: {r}")
except Exception as e:
    print(f"login_history error: {e}")

# Farm journal
try:
    c.execute("PRAGMA table_info(farm_journal)")
    print("\nFARM_JOURNAL columns:", [(r[1], r[2]) for r in c.fetchall()])
except Exception as e:
    print(f"farm_journal error: {e}")

# Transactions (for wallet activity)
try:
    c.execute("SELECT COUNT(*) FROM transactions")
    print(f"\nTransactions count: {c.fetchone()[0]}")
    c.execute("SELECT COUNT(*) FROM wallet_transactions")
    print(f"Wallet transactions count: {c.fetchone()[0]}")
except Exception as e:
    print(f"transactions error: {e}")

# Notifications
try:
    c.execute("PRAGMA table_info(notifications)")
    print("\nNOTIFICATIONS columns:", [(r[1], r[2]) for r in c.fetchall()])
except Exception as e:
    print(f"notifications error: {e}")

# Scheme documents
try:
    c.execute("PRAGMA table_info(scheme_documents)")
    print("\nSCHEME_DOCUMENTS columns:", [(r[1], r[2]) for r in c.fetchall()])
except Exception as e:
    print(f"scheme_documents error: {e}")

conn.close()
