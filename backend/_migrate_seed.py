import os, sys
os.chdir(r"C:\Users\AICOE 5\Downloads\Farm_Assist.Application\backend")
sys.path.insert(0, os.getcwd())
from app.config import settings
from app.database.connection import engine, Base
from app.database.schema_upgrade import run_additive_migrations
run_additive_migrations(settings.DATABASE_URL)
Base.metadata.create_all(bind=engine)
print("MIGRATION + CREATE_ALL DONE")
from app.database.connection import SessionLocal
from app.database.seed_schemes import seed
db = SessionLocal()
try:
    print(seed(db))
finally:
    db.close()
print("SEED DONE")

