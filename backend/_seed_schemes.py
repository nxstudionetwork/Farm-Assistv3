import os, sys
os.chdir(r"C:\Users\AICOE 5\Downloads\Farm_Assist.Application\backend")
sys.path.insert(0, os.getcwd())
import logging
logging.getLogger("sqlalchemy.engine").setLevel(logging.CRITICAL)
from app.database.connection import SessionLocal
from app.database.seed_schemes import seed
db = SessionLocal()
try:
    print(seed(db))
finally:
    db.close()

