import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backend'))
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backend'))
from app.database.connection import SessionLocal
from app.models.user import User, FarmerProfile
from app.models.farm import Farm

db = SessionLocal()
junk = ['12345', '9000000001', '9000000002', '9000000003', '9000000004', '9000000005', '9000000006', '9000000007', '9000000008']
users = db.query(User).filter(User.phone_number.in_(junk)).all()
print("found junk:", [u.phone_number for u in users])
for u in users:
    db.query(FarmerProfile).filter(FarmerProfile.user_id == u.id).delete()
    db.query(Farm).filter(Farm.user_id == u.id).delete()
    db.delete(u)
db.commit()
db.close()
print("cleaned")
