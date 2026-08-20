import sys, os, random
sys.path.insert(0, os.path.dirname(__file__))
from app.database.connection import engine, SessionLocal, Base
from app.models import *
from app.utils.auth import hash_password, generate_farmer_id, generate_id
from datetime import datetime, date

def to_dt(d):
    if isinstance(d, str):
        return datetime.strptime(d, "%Y-%m-%d")
    return d

def seed_database():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if db.query(User).first():
            print("Already seeded. Drop DB to re-seed.")
            return

        print("Seeding comprehensive mock data...")

        # === USER ===
        user = User(
            full_name="Rajesh Kumar", phone_number="+919876543210",
            email="rajesh@farmassist.com", password_hash=hash_password("1234"),
            preferred_language="en", role="farmer", is_verified=True, is_active=True,
        )
        db.add(user); db.flush()
        user.farmer_id = generate_farmer_id(db)
        db.add(FarmerProfile(
            user_id=user.id, farmer_id=user.farmer_id, gender="male",
            occupation="Farmer", farming_experience="10+ years",
            preferred_crops="Rice,Wheat,Cotton,Chilli",
        ))
        db.add(UserAddress(
            user_id=user.id, address_line="Farm House, Near Canal",
            village="Rajampur", mandal="Nalgonda", district="Nalgonda",
            state="Telangana", country="India", pincode="508001",
            latitude=17.0575, longitude=79.2820, is_primary=True,
        ))
        db.flush()

        # === FARMS ===
        farms_data = [
            ("Rajesh Green Farm", "Mixed Farming", "Red Soil", "Canal + Borewell", "Drip", 25.0),
            ("Rajesh Paddy Fields", "Paddy Farm", "Alluvial", "Borewell", "Flood", 10.0),
        ]
        farm_objs = []
        for name, ftype, soil, water, irrig, area in farms_data:
            f = Farm(user_id=user.id, farm_name=name, village="Rajampur",
                mandal="Nalgonda", district="Nalgonda", state="Telangana",
                latitude=17.0575, longitude=79.2820, total_area=area,
                area_unit="Acres", soil_type=soil, water_source=water,
                irrigation_method=irrig, farm_type=ftype)
            db.add(f); db.flush()
            f.farm_id = generate_id("FA-FARM", db, Farm)
            farm_objs.append(f)

        # === PLOTS ===
        plots_data = [("North Field",12.0,17.058,79.2825,"Red Soil"),("South Field",13.0,17.057,79.2815,"Black Soil"),("East Block",10.0,17.059,79.283,"Loamy")]
        plot_objs = []
        for i,(name,area,lat,lng,soil) in enumerate(plots_data):
            p = FarmPlot(farm_id=farm_objs[0].id, plot_name=name, area=area,
                latitude=lat, longitude=lng, soil_type=soil,
                plot_id=f"FA-PLT-{str(i+1).zfill(6)}")
            db.add(p); plot_objs.append(p)
        db.flush()

        # === CROPS ===
        crops_raw = [("Rice","Sona Masuri","Cereal","Kharif",120),("Wheat","HD-3086","Cereal","Rabi",150),
            ("Cotton","Bt Cotton","Cash Crop","Kharif",180),("Maize","Hybrid-900","Cereal","Kharif",100),
            ("Groundnut","TMV-7","Oilseed","Kharif",110),("Chilli","Guntur Special","Spice","Kharif",150),
            ("Turmeric","Erode","Spice","Kharif",240),("Soybean","JS-335","Oilseed","Kharif",105)]
        crop_objs = []
        for i,(n,v,c,s,d) in enumerate(crops_raw):
            cr = Crop(name=n,variety=v,category=c,season=s,growth_duration_days=d,crop_id=f"FA-CRP-{str(i+1).zfill(6)}")
            db.add(cr); crop_objs.append(cr)
        db.flush()

        # === CROP CYCLES ===
        cycles_raw = [
            (0,0,0,"2026-06-15","2026-10-15","Flowering","active"),
            (0,1,2,"2026-05-01","2026-10-30","Boll Formation","active"),
            (0,2,5,"2026-06-20","2026-11-20","Vegetative","active"),
            (1,None,0,"2026-07-01","2026-11-01","Sowing","active"),
        ]
        cycle_objs = []
        for fi,pi,ci,sow,exp,stage,st in cycles_raw:
            cy = CropCycle(farm_id=farm_objs[fi].id, plot_id=plot_objs[pi].id if pi is not None else None,
                crop_id=crop_objs[ci].id, sowing_date=sow, expected_harvest_date=exp,
                current_stage=stage, seed_quantity=25.0, seed_unit="kg", status=st)
            db.add(cy); cycle_objs.append(cy)
        db.flush()
        for i,cy in enumerate(cycle_objs):
            cy.cycle_id = f"FA-CYC-{str(i+1).zfill(6)}"
        db.flush()

        # === TASKS ===
        tasks_raw = [
            (0,"Apply NPK fertilizer","Apply 3 bags NPK to rice field","Fertilizer","2026-07-30","high","pending"),
            (0,"Weed removal","Manual weeding in north field","Weeding","2026-08-02","medium","pending"),
            (0,"Pest spray","Spray neem oil for aphids","Pest Control","2026-08-05","high","pending"),
            (1,"Cotton irrigation","Run drip for 2 hours","Irrigation","2026-07-29","high","pending"),
            (1,"Top dressing","Apply urea to cotton","Fertilizer","2026-08-01","medium","completed"),
            (2,"Seedling transplanting","Transplant chilli seedlings","Seeding","2026-07-28","high","pending"),
            (2,"Mulching","Apply organic mulch","Soil Management","2026-08-10","low","pending"),
        ]
        for i,(ci,title,desc,cat,due,pri,st) in enumerate(tasks_raw):
            db.add(CropTask(crop_cycle_id=cycle_objs[ci].id, title=title, description=desc,
                category=cat, due_date=due, priority=pri, status=st,
                task_id=f"FA-TSK-{str(i+1).zfill(6)}"))

        # === JOURNAL ===
        journal_raw = [
            (0,0,"Sowing completed","Sowed Sona Masuri rice seeds in 12 acres","2026-06-15"),
            (0,0,"First irrigation","Flooded field with canal water 48hrs","2026-06-20"),
            (0,1,"Bt Cotton sowing","Planted Bt cotton 90cm spacing","2026-05-01"),
            (0,None,"Soil testing","pH 6.5, NPK adequate","2026-04-15"),
            (0,2,"Chilli nursery ready","2000 seedlings ready","2026-06-10"),
        ]
        for fi,pi,act,notes,dt in journal_raw:
            db.add(FarmJournal(user_id=user.id, farm_id=farm_objs[fi].id,
                plot_id=plot_objs[pi].id if pi is not None else None,
                activity=act, notes=notes, entry_date=to_dt(dt)))

        # === EXPENSES ===
        exp_raw = [
            ("Seeds purchase - Rice","Seeds",5000),("NPK Fertilizer 3 bags","Fertilizer",4500),
            ("Labor wages - sowing","Labor",8000),("Neem oil pesticide","Pest Control",2000),
            ("Drip irrigation maintenance","Irrigation",1500),("Tractor diesel","Equipment",3000),
            ("Weeding labor","Labor",4000),("Bt Cotton seeds","Seeds",6000),
            ("Urea 5 bags","Fertilizer",2500),("Chilli seeds","Seeds",1500),
        ]
        for i,(desc,cat,amt) in enumerate(exp_raw):
            db.add(Expense(user_id=user.id, farm_id=farm_objs[0].id, category=cat,
                amount=amt, description=desc, vendor="Local Store", payment_method="Cash",
                expense_date=to_dt(f"2026-07-{random.randint(1,28):02d}"),
                expense_id=f"FA-EXP-{str(i+1).zfill(6)}"))

        # === INCOME ===
        inc_raw = [
            ("Rice sale - 15 tons","Crop Sale",450000),("Wheat sale - 8 tons","Crop Sale",160000),
            ("Cotton sale - 5 tons","Cash Crop",250000),("Groundnut sale","Oilseed Sale",80000),
            ("Equipment rental income","Equipment Rental",25000),
        ]
        for i,(desc,cat,amt) in enumerate(inc_raw):
            db.add(Income(user_id=user.id, farm_id=farm_objs[0].id, category=cat,
                amount=amt, description=desc, buyer="Mandi trader",
                payment_method="Bank Transfer",                 income_date=to_dt(f"2026-{random.randint(1,6):02d}-{random.randint(1,28):02d}"),
                income_id=f"FA-INC-{str(i+1).zfill(6)}"))

        # === WORKERS ===
        workers_raw = [
            ("Suresh Reddy","+919876543211","Rajampur","Nalgonda",["Plowing","Harvesting"],8,500,3000,4.5),
            ("Venkat Rao","+919876543212","Warangal","Warangal",["Spraying","Fertilizer"],5,400,2500,4.2),
            ("Prakash Singh","+919876543213","Karimnagar","Karimnagar",["Plowing","Driving"],12,600,4000,4.7),
            ("Ravi Kumar","+919876543214","Medak","Medak",["Harvesting","Weeding"],6,450,2800,4.0),
            ("Anil Sharma","+919876543215","Shadnagar","Mahabubnagar",["Spraying","Sowing"],4,350,2200,4.3),
            ("Mohan Lal","+919876543216","Khammam","Khammam",["Plowing","Driving"],10,550,3500,4.6),
            ("Jagdish Patel","+919876543217","Nizamabad","Nizamabad",["Harvesting","Spraying"],7,420,2600,4.1),
        ]
        for i,(name,phone,vil,dist,skills,exp,hr,dr,rating) in enumerate(workers_raw):
            db.add(Worker(full_name=name, phone_number=phone, village=vil, district=dist,
                state="Telangana", skills=skills, experience_years=exp,
                hourly_rate=hr, daily_rate=dr, rating=rating,
                total_reviews=random.randint(5,50), is_verified=True, is_available=True,
                worker_id=f"FA-WRK-{str(i+1).zfill(6)}"))

        # === GOVT SCHEMES ===
        schemes_raw = [
            ("PM-KISAN","PM-KISAN Samman Nidhi","Income support Rs 6000/year to small farmers",
             "Small and marginal farmers","Rs 6000/year in 3 installments","Income Support","2026-12-31"),
            ("PMFBY","PM Fasal Bima Yojana","Crop insurance against natural calamities",
             "All farmers","Covers crop loss up to insured amount","Insurance","2026-07-31"),
            ("PMKSY","PM Krishi Sinchayee Yojana","Micro irrigation with subsidy",
             "All farmers","55% subsidy on drip/sprinkler","Subsidy","2026-09-30"),
            ("KCC","Kisan Credit Card","Easy credit at concessional rates",
             "All farmers","Crop loan at 4% interest","Credit","2026-12-31"),
            ("SMAM","Sub-Mission Agricultural Mechanization","Subsidy on farm machinery",
             "All farmers","40-50% subsidy on equipment","Subsidy","2026-08-31"),
            ("RKVY","Rashtriya Krishi Vikas Yojana","Agriculture growth through investment",
             "All stakeholders","Grants for infrastructure","Grant","2026-06-30"),
            ("NFBS","National Food Security Mission","Increase wheat/rice/pulses productivity",
             "All farmers","Input subsidies and tech support","Subsidy","2026-09-30"),
            ("eNAM","Electronic National Agri Market","Online trading for farm commodities",
             "All farmers","Better price discovery","Market Access",None),
            ("PMKMY","PM Kisan Maandhan Yojana","Pension for small/marginal farmers",
             "Farmers aged 18-40","Rs 3000/month pension after 60","Pension","2026-12-31"),
        ]
        for i,(name,full,desc,elig,benefits,cat,deadline) in enumerate(schemes_raw):
            db.add(GovernmentScheme(scheme_id=f"FA-SCH-{str(i+1).zfill(6)}",
                name=name, description=f"{full}: {desc}", eligibility=elig,
                benefits=benefits, state="All India", category=cat,
                documents_required=["Aadhaar Card","Bank Account","Land Records"],
                application_deadline=deadline, status="active"))

        # === PRODUCTS ===
        cats = {}
        for cn in ["Fertilizers","Seeds","Pesticides","Equipment","Irrigation","Organic"]:
            c = ProductCategory(name=cn, slug=cn.lower())
            db.add(c); cats[cn] = c
        db.flush()

        prods_raw = [
            ("DAP Fertilizer","Premium DAP for all crops",1200,1400,"bag",50,"Fertilizers"),
            ("Urea - Neem Coated","High nitrogen neem coated urea",300,350,"bag",100,"Fertilizers"),
            ("NPK 10-26-26","Balanced NPK for oilseeds",850,1000,"bag",30,"Fertilizers"),
            ("Sona Masuri Seeds","High yielding rice seeds 5kg",180,220,"packet",200,"Seeds"),
            ("Bt Cotton Seeds","Premium Bt cotton 450g",800,950,"packet",75,"Seeds"),
            ("Chilli Seeds Guntur","Premium Guntur chilli 100g",350,400,"packet",120,"Seeds"),
            ("Tomato Seeds Hybrid","Arka Rakshak 10g",150,180,"packet",150,"Seeds"),
            ("Neem Oil 5L","Cold pressed organic pest control",250,320,"bottle",150,"Pesticides"),
            ("Imidacloprid 17.8SL","Systemic insecticide",380,420,"bottle",80,"Pesticides"),
            ("Mancozeb 75WP","Contact fungicide for blight",280,320,"packet",90,"Pesticides"),
            ("Drip Kit 1 Acre","Complete drip system with filter",15000,18000,"set",10,"Irrigation"),
            ("Sprinkler Set 0.5A","Rain gun sprinkler system",8000,10000,"set",15,"Irrigation"),
            ("Tractor Plough 3T","Heavy duty tractor plough",25000,30000,"piece",5,"Equipment"),
            ("Sprayer 16L Battery","Battery knapsack sprayer",3500,4200,"piece",20,"Equipment"),
            ("Vermicompost 50kg","Premium organic vermicompost",400,500,"bag",60,"Organic"),
            ("Panchagavya 1L","Organic growth promoter",180,220,"bottle",40,"Organic"),
        ]
        for i,(name,desc,price,orig,unit,stock,cat) in enumerate(prods_raw):
            db.add(Product(product_id=f"FA-PRD-{str(i+1).zfill(6)}", name=name,
                description=desc, price=price, original_price=orig, unit=unit,
                stock_quantity=stock, rating=round(random.uniform(3.8,4.8),1),
                total_reviews=random.randint(5,100), is_active=True, category_id=cats[cat].id))

        # === EQUIPMENT ===
        equip_raw = [
            ("John Deere 5310","Tractor","John Deere","5310","57 HP tractor AC cabin",2500,500),
            ("Mahindra Arjun 605","Tractor","Mahindra","605 DI","60 HP 2WD tractor",2000,400),
            ("Kubota Harvester","Harvester","Kubota","DC-70+","Mini combine harvester",5000,1000),
            ("Soil Cultivator","Cultivator","Shaktiman","9T","9-tyne cultivator",1200,250),
            ("Seed Drill 9T","Seeder","Dasmesh","911","Seed drill with fertilizer box",1500,300),
        ]
        for i,(name,typ,brand,model,desc,dr,hr) in enumerate(equip_raw):
            db.add(Equipment(equipment_id=f"FA-EQP-{str(i+1).zfill(6)}", name=name,
                type=typ, brand=brand, model=model, description=desc,
                daily_rate=dr, hourly_rate=hr, owner_id=user.id, is_available=True,
                location="Nalgonda, Telangana"))

        # === EXPERTS ===
        experts_raw = [
            ("Dr. Lakshmi Devi","Crop Science","PhD Agriculture",15,"Hyderabad",500,4.8,245),
            ("Dr. Venkateshwar Rao","Soil Science","PhD Soil Science",20,"Warangal",400,4.6,189),
            ("Dr. Anitha Reddy","Plant Protection","PhD Entomology",12,"Nalgonda",600,4.7,312),
            ("Prof. Srinivasa Rao","Water Management","PhD Irrigation",18,"Karimnagar",450,4.5,156),
            ("Dr. Kavitha Sharma","Organic Farming","MSc Organic Agri",10,"Hyderabad",350,4.4,203),
        ]
        for i,(name,spec,qual,exp,loc,fee,rating,reviews) in enumerate(experts_raw):
            db.add(Expert(expert_id=f"FA-EXPT-{str(i+1).zfill(6)}", full_name=name,
                speciality=spec, qualification=qual, experience_years=exp,
                location=loc, consultation_fee=fee, rating=rating,
                total_consultations=reviews, is_available=True))

        # === COMMUNITY POSTS ===
        posts_raw = [
            ("My rice crop is looking great this season! Used new variety seeds from the marketplace.","tip"),
            ("Anyone else facing aphid problems in Nalgonda district? Need advice.","question"),
            ("Sold my cotton at Rs 6500/quintal at the local mandi. Good prices this year!","share"),
            ("Government subsidy for drip irrigation is really helpful. Applied through KCC.","info"),
            ("New organic farming techniques I tried this season - results are promising!","tip"),
        ]
        for i,(content,ptyp) in enumerate(posts_raw):
            db.add(CommunityPost(post_id=f"FA-POST-{str(i+1).zfill(6)}",
                user_id=user.id, content=content, post_type=ptyp,
                likes_count=random.randint(2,25), comments_count=random.randint(0,10),
                shares_count=random.randint(0,5), is_active=True))

        # === NOTIFICATIONS ===
        notif_raw = [
            ("Weather Alert","Heavy rainfall expected in Nalgonda in next 3 days","weather","rain"),
            ("Task Reminder","Apply NPK fertilizer to rice field tomorrow","task","fertilizer"),
            ("Scheme Update","PM-KISAN 14th installment credited to bank account","scheme","money"),
            ("Market Price","Rice price increased to Rs 3200/quintal at Hyderabad mandi","market","trending"),
            ("Pest Alert","Aphid infestation reported in nearby villages - take precautions","pest","warning"),
            ("System Welcome","Welcome to Farm Assist! Complete your profile for better recommendations","system","info"),
        ]
        for i,(title,msg,ntyp,icon) in enumerate(notif_raw):
            db.add(Notification(notification_id=f"FA-NOT-{str(i+1).zfill(6)}",
                user_id=user.id, title=title, message=msg,
                notification_type=ntyp, icon=icon,
                is_read=random.choice([True,False])))

        # === LOANS ===
        db.add(Loan(loan_id="FA-LOAN-000001", user_id=user.id,
            bank_name="State Bank of India", loan_amount=500000,
            interest_rate=7.0, tenure_months=60, emi_amount=9900,
            outstanding_amount=350000, status="active"))

        # === BUDGETS ===
        for cat,amt in [("Seeds",20000),("Fertilizer",15000),("Labor",30000),("Pest Control",10000),("Irrigation",8000)]:
            db.add(Budget(user_id=user.id, farm_id=farm_objs[0].id,
                category=cat, amount=amt, period="monthly", year=2026, month=7))

        db.commit()
        print("Seed complete!")
        print(f"  Login: +919876543210 / PIN: 1234")
        print(f"  Farmer ID: {user.farmer_id}")
        print(f"  Farms: {db.query(Farm).count()}")
        print(f"  Plots: {db.query(FarmPlot).count()}")
        print(f"  Crops: {db.query(Crop).count()}")
        print(f"  Crop Cycles: {db.query(CropCycle).count()}")
        print(f"  Tasks: {db.query(CropTask).count()}")
        print(f"  Expenses: {db.query(Expense).count()}")
        print(f"  Income: {db.query(Income).count()}")
        print(f"  Workers: {db.query(Worker).count()}")
        print(f"  Schemes: {db.query(GovernmentScheme).count()}")
        print(f"  Products: {db.query(Product).count()}")
        print(f"  Equipment: {db.query(Equipment).count()}")
        print(f"  Experts: {db.query(Expert).count()}")
        print(f"  Community Posts: {db.query(CommunityPost).count()}")
        print(f"  Notifications: {db.query(Notification).count()}")

    except Exception as e:
        db.rollback()
        print(f"Error: {e}")
        import traceback; traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    seed_database()
