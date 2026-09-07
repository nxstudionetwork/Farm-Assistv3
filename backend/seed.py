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

        from app.database.seed_services import seed_agricultural_services
        seed_agricultural_services(db)

        from app.database.seed_techniques import seed_techniques
        seed_techniques(db)

        # === LEARNING CENTER - AGRICULTURE COURSES ===
        print("Seeding Learning Center courses...")
        
        # Course categories mapping
        category_map = {
            "Crop Management": "Crop Management",
            "Soil Health": "Soil Health",
            "Organic Farming": "Organic Farming",
            "Pest Management": "Pest Management",
            "Irrigation": "Irrigation",
            "Farm Technology": "Farm Technology",
            "Livestock": "Livestock",
            "Horticulture": "Horticulture",
            "Sustainable Farming": "Sustainable Farming",
            "Farm Finance": "Farm Finance",
            "Modern Farming": "Modern Farming",
            "Government Schemes": "Government Schemes"
        }
        
        # Generate 45+ comprehensive agriculture courses with lessons
        course_data = [
            # Crop Management Courses
            {
                "title": "Organic Farming Basics",
                "description": "Learn practical organic farming techniques to improve soil health and crop yields without synthetic chemicals.",
                "category": category_map["Organic Farming"],
                "level": "beginner",
                "duration_weeks": 4,
                "language": "English",
                "instructor": "Dr. Kavitha Sharma",
                "image_url": "https://images.unsplash.com/photo-1500382017468-9049fed747ef?w=400",
                "lessons": [
                    {"title": "Introduction to Organic Farming", "duration": 15, "content": "Understanding the principles of organic farming and its benefits for soil health and environment."},
                    {"title": "Soil Preparation and Composting", "duration": 20, "content": "How to prepare your soil naturally and create effective compost piles."},
                    {"title": "Natural Pest Control Methods", "duration": 18, "content": "Identifying pests and using natural predators, neem oil, and companion planting."},
                    {"title": "Organic Fertilizers and Soil Amendments", "duration": 15, "content": "Types of organic fertilizers and how to apply them for maximum benefit."},
                    {"title": "Crop Rotation Strategies", "duration": 12, "content": "Planning crop rotations to maintain soil fertility and prevent diseases."},
                    {"title": "Weed Management in Organic Farming", "duration": 14, "content": "Effective organic methods for controlling weeds without chemicals."},
                    {"title": "Harvesting and Post-Harvest Handling", "duration": 16, "content": "Best practices for harvesting crops and handling them to maintain quality."}
                ]
            },
            {
                "title": "Rice Cultivation Techniques",
                "description": "Master the art of rice farming from seed selection to harvest with modern and traditional methods.",
                "category": category_map["Crop Management"],
                "level": "intermediate",
                "duration_weeks": 6,
                "language": "English",
                "instructor": "Prof. Srinivas Rao",
                "image_url": "https://images.unsplash.com/photo-1590912731627-57b645103a42?w=400",
                "lessons": [
                    {"title": "Rice Varieties and Selection", "duration": 15, "content": "Choosing the right rice variety for your region and soil type."},
                    {"title": "Land Preparation for Rice", "duration": 18, "content": "Proper field leveling and water management for rice cultivation."},
                    {"title": "Nursery Management", "duration": 14, "content": "Establishing and maintaining healthy rice nurseries."},
                    {"title": "Transplanting Techniques", "duration": 16, "content": "Best practices for manual and mechanical transplanting."},
                    {"title": "Water Management in Rice Fields", "duration": 20, "content": "Irrigation scheduling and water-saving techniques for rice."},
                    {"title": "Pest and Disease Management", "duration": 18, "content": "Identifying and controlling common rice pests and diseases."},
                    {"title": "Fertilizer Application in Rice", "duration": 15, "content": "Balanced fertilizer application for optimal rice growth."},
                    {"title": "Harvesting and Threshing", "duration": 12, "content": "Proper timing and techniques for rice harvesting and threshing."}
                ]
            },
            {
                "title": "Wheat Farming Best Practices",
                "description": "Comprehensive guide to wheat cultivation covering all aspects from sowing to storage.",
                "category": category_map["Crop Management"],
                "level": "beginner",
                "duration_weeks": 5,
                "language": "English",
                "instructor": "Dr. Lakshmi Devi",
                "image_url": "https://images.unsplash.com/photo-1567191899446-433c3c9405b3?w=400",
                "lessons": [
                    {"title": "Wheat Varieties for Different Regions", "duration": 15, "content": "Selecting appropriate wheat varieties based on climate and soil."},
                    {"title": "Soil Preparation for Wheat", "duration": 14, "content": "Tillage methods and soil testing for wheat cultivation."},
                    {"title": "Seed Treatment and Sowing", "duration": 16, "content": "Proper seed treatment and sowing techniques for maximum germination."},
                    {"title": "Irrigation Management", "duration": 18, "content": "Water requirements at different growth stages of wheat."},
                    {"title": "Nutrient Management", "duration": 15, "content": "Balanced fertilizer application for healthy wheat growth."},
                    {"title": "Pest and Disease Control", "duration": 17, "content": "Identifying and managing common wheat pests and diseases."},
                    {"title": "Harvesting and Storage", "duration": 12, "content": "Timing, methods, and storage techniques to prevent grain loss."}
                ]
            },
            {
                "title": "Cotton Cultivation Guide",
                "description": "Complete guide to cotton farming including modern techniques and traditional wisdom.",
                "category": category_map["Crop Management"],
                "level": "intermediate",
                "duration_weeks": 8,
                "language": "English",
                "instructor": "Dr. Venkateshwar Rao",
                "image_url": "https://images.unsplash.com/photo-1599781283821-16814f78b5a0?w=400",
                "lessons": [
                    {"title": "Cotton Varieties and Hybrid Selection", "duration": 18, "content": "Choosing high-yielding cotton varieties suitable for your region."},
                    {"title": "Land Preparation and Planting", "duration": 16, "content": "Soil preparation and planting techniques for cotton."},
                    {"title": "Water Management in Cotton", "duration": 20, "content": "Irrigation scheduling and water stress management."},
                    {"title": "Nutrient Requirements", "duration": 15, "content": "Essential nutrients for cotton and their application methods."},
                    {"title": "Pest Management", "duration": 22, "content": "Identifying and controlling major cotton pests including bollworms."},
                    {"title": "Disease Prevention and Control", "duration": 18, "content": "Common cotton diseases and their management strategies."},
                    {"title": "Harvesting and Ginning", "duration": 14, "content": "Proper harvesting techniques and ginning process."},
                    {"title": "Post-Harvest Processing", "duration": 12, "content": "Storage and processing of cotton to maintain quality."}
                ]
            },
            {
                "title": "Maize Farming Techniques",
                "description": "Learn modern maize cultivation practices for higher yields and better quality.",
                "category": category_map["Crop Management"],
                "level": "beginner",
                "duration_weeks": 4,
                "language": "English",
                "instructor": "Dr. Lakshmi Devi",
                "image_url": "https://images.unsplash.com/photo-1625246333195-78d9c38ad449?w=400",
                "lessons": [
                    {"title": "Maize Varieties and Selection", "duration": 14, "content": "Choosing high-yielding maize varieties for different agro-climatic zones."},
                    {"title": "Soil Preparation and Sowing", "duration": 16, "content": "Land preparation and sowing methods for maize cultivation."},
                    {"title": "Irrigation Management", "duration": 15, "content": "Water requirements and irrigation scheduling for maize."},
                    {"title": "Fertilizer Application", "duration": 14, "content": "Balanced fertilizer program for optimal maize growth."},
                    {"title": "Pest and Disease Management", "duration": 18, "content": "Identifying and controlling common maize pests and diseases."},
                    {"title": "Harvesting and Storage", "duration": 12, "content": "Proper harvesting techniques and storage methods to prevent losses."}
                ]
            },
            
            # Soil Health Courses
            {
                "title": "Soil Testing and Analysis",
                "description": "Learn how to test your soil, interpret results, and make informed decisions for better crop yields.",
                "category": category_map["Soil Health"],
                "level": "beginner",
                "duration_weeks": 3,
                "language": "English",
                "instructor": "Dr. Venkateshwar Rao",
                "image_url": "https://images.unsplash.com/photo-1574323347407-f5e1ad6d020b?w=400",
                "lessons": [
                    {"title": "Understanding Soil Composition", "duration": 15, "content": "Soil texture, structure, and composition explained."},
                    {"title": "Soil Sampling Techniques", "duration": 14, "content": "How to collect soil samples for accurate testing."},
                    {"title": "Interpreting Soil Test Results", "duration": 18, "content": "Understanding pH, NPK, and micronutrient levels."},
                    {"title": "Soil pH Management", "duration": 15, "content": "Adjusting soil pH for different crops."},
                    {"title": "Organic Matter Management", "duration": 16, "content": "Improving soil organic matter through various practices."},
                    {"title": "Soil Erosion Prevention", "duration": 12, "content": "Techniques to prevent soil erosion and maintain fertility."}
                ]
            },
            {
                "title": "Composting and Vermicomposting",
                "description": "Master the art of composting and vermicomposting to create rich organic fertilizer for your farm.",
                "category": category_map["Soil Health"],
                "level": "beginner",
                "duration_weeks": 2,
                "language": "English",
                "instructor": "Dr. Kavitha Sharma",
                "image_url": "https://images.unsplash.com/photo-1551836022-deb4988cc6c0?w=400",
                "lessons": [
                    {"title": "Introduction to Composting", "duration": 12, "content": "Basic principles and benefits of composting."},
                    {"title": "Compost Pile Construction", "duration": 14, "content": "Building effective compost piles with proper carbon-nitrogen ratio."},
                    {"title": "Vermicomposting Basics", "duration": 15, "content": "Setting up a worm farm and maintaining healthy worms."},
                    {"title": "Compost Tea Preparation", "duration": 12, "content": "Making and using compost tea for foliar application."},
                    {"title": "Troubleshooting Compost Issues", "duration": 10, "content": "Solving common composting problems like odor and pests."}
                ]
            },
            {
                "title": "Soil Fertility Management",
                "description": "Learn how to maintain and improve soil fertility through natural and sustainable methods.",
                "category": category_map["Soil Health"],
                "level": "intermediate",
                "duration_weeks": 4,
                "language": "English",
                "instructor": "Dr. Venkateshwar Rao",
                "image_url": "https://images.unsplash.com/photo-1599393974932-9a3b1a3a1a3a?w=400",
                "lessons": [
                    {"title": "Soil Nutrient Cycles", "duration": 16, "content": "Understanding nitrogen, phosphorus, and potassium cycles in soil."},
                    {"title": "Green Manuring", "duration": 14, "content": "Using green manure crops to improve soil fertility."},
                    {"title": "Biofertilizers", "duration": 15, "content": "Types of biofertilizers and their application methods."},
                    {"title": "Crop Residue Management", "duration": 12, "content": "Proper management of crop residues for soil health."},
                    {"title": "Soil Microorganisms", "duration": 18, "content": "Role of beneficial soil microbes in nutrient cycling."}
                ]
            },
            
            # Organic Farming Courses
            {
                "title": "Natural Farming Techniques",
                "description": "Learn Subhash Palekar's natural farming methods for chemical-free agriculture.",
                "category": category_map["Organic Farming"],
                "level": "intermediate",
                "duration_weeks": 5,
                "language": "English",
                "instructor": "Dr. Kavitha Sharma",
                "image_url": "https://images.unsplash.com/photo-1466611653911-95081537e5b7?w=400",
                "lessons": [
                    {"title": "Introduction to Natural Farming", "duration": 18, "content": "Principles and philosophy of natural farming."},
                    {"title": "Jeewamrit Preparation", "duration": 15, "content": "Making and using jeewamrit for soil and plant health."},
                    {"title": "Beejamrit Application", "duration": 12, "content": "Seed treatment with beejamrit for better germination."},
                    {"title": "Mulching Techniques", "duration": 14, "content": "Using organic mulches to conserve moisture and suppress weeds."},
                    {"title": "Pest Management in Natural Farming", "duration": 16, "content": "Natural methods to control pests without chemicals."},
                    {"title": "Natural Farming Economics", "duration": 12, "content": "Cost-benefit analysis of natural farming vs conventional."}
                ]
            },
            {
                "title": "Biofertilizers and Biopesticides",
                "description": "Comprehensive guide to using biofertilizers and biopesticides for sustainable agriculture.",
                "category": category_map["Organic Farming"],
                "level": "beginner",
                "duration_weeks": 3,
                "language": "English",
                "instructor": "Dr. Anitha Reddy",
                "image_url": "https://images.unsplash.com/photo-1580489944761-15a19d654956?w=400",
                "lessons": [
                    {"title": "Introduction to Biofertilizers", "duration": 14, "content": "Types of biofertilizers and their benefits."},
                    {"title": "Rhizobium Inoculants", "duration": 12, "content": "Using rhizobium for legume crops."},
                    {"title": "Azotobacter and Azospirillum", "duration": 12, "content": "Nitrogen-fixing bacteria for non-legume crops."},
                    {"title": "Phosphate Solubilizing Microorganisms", "duration": 14, "content": "Improving phosphorus availability to plants."},
                    {"title": "Biopesticides Overview", "duration": 15, "content": "Types of biopesticides and their application methods."},
                    {"title": "Trichoderma for Disease Control", "duration": 12, "content": "Using trichoderma to control soil-borne diseases."}
                ]
            },
            
            # Pest Management Courses
            {
                "title": "Integrated Pest Management (IPM)",
                "description": "Learn modern IPM techniques to control pests while minimizing chemical use and environmental impact.",
                "category": category_map["Pest Management"],
                "level": "intermediate",
                "duration_weeks": 4,
                "language": "English",
                "instructor": "Dr. Anitha Reddy",
                "image_url": "https://images.unsplash.com/photo-1560493676-04071c5f467b?w=400",
                "lessons": [
                    {"title": "Introduction to IPM", "duration": 15, "content": "Principles and components of Integrated Pest Management."},
                    {"title": "Pest Identification", "duration": 18, "content": "Identifying common agricultural pests and beneficial insects."},
                    {"title": "Biological Control Methods", "duration": 16, "content": "Using natural enemies to control pest populations."},
                    {"title": "Cultural Control Practices", "duration": 14, "content": "Crop rotation, trap cropping, and other cultural methods."},
                    {"title": "Chemical Control Strategies", "duration": 12, "content": "Safe and effective use of pesticides when necessary."},
                    {"title": "Pest Monitoring Techniques", "duration": 15, "content": "Using traps, pheromones, and field scouting for pest monitoring."}
                ]
            },
            {
                "title": "Organic Pest Control Methods",
                "description": "Learn completely natural methods to control pests in your crops without chemicals.",
                "category": category_map["Pest Management"],
                "level": "beginner",
                "duration_weeks": 3,
                "language": "English",
                "instructor": "Dr. Anitha Reddy",
                "image_url": "https://images.unsplash.com/photo-1585435557345-6c1e8a0c6b8c?w=400",
                "lessons": [
                    {"title": "Beneficial Insects", "duration": 16, "content": "Identifying and attracting beneficial insects to your farm."},
                    {"title": "Neem Oil Applications", "duration": 14, "content": "Making and using neem oil sprays for pest control."},
                    {"title": "Companion Planting", "duration": 15, "content": "Using companion plants to repel pests naturally."},
                    {"title": "Homemade Organic Sprays", "duration": 18, "content": "Recipes for effective homemade organic pest control sprays."},
                    {"title": "Physical Barriers", "duration": 12, "content": "Using nets, row covers, and other physical barriers."}
                ]
            },
            
            # Irrigation Courses
            {
                "title": "Drip Irrigation Systems",
                "description": "Complete guide to designing, installing, and maintaining drip irrigation systems for water efficiency.",
                "category": category_map["Irrigation"],
                "level": "intermediate",
                "duration_weeks": 4,
                "language": "English",
                "instructor": "Prof. Srinivasa Rao",
                "image_url": "https://images.unsplash.com/photo-1625246333195-78d9c38ad449?w=400",
                "lessons": [
                    {"title": "Introduction to Drip Irrigation", "duration": 14, "content": "Benefits and components of drip irrigation systems."},
                    {"title": "System Design and Layout", "duration": 20, "content": "Designing drip systems for different crops and field sizes."},
                    {"title": "Component Selection", "duration": 16, "content": "Choosing emitters, filters, valves, and other components."},
                    {"title": "Installation Guide", "duration": 18, "content": "Step-by-step installation of drip irrigation systems."},
                    {"title": "Maintenance and Troubleshooting", "duration": 15, "content": "Keeping your system running efficiently."},
                    {"title": "Fertigation Techniques", "duration": 14, "content": "Applying fertilizers through drip irrigation systems."}
                ]
            },
            {
                "title": "Water Management in Agriculture",
                "description": "Learn efficient water management techniques to maximize crop yields with minimal water use.",
                "category": category_map["Irrigation"],
                "level": "beginner",
                "duration_weeks": 3,
                "language": "English",
                "instructor": "Prof. Srinivasa Rao",
                "image_url": "https://images.unsplash.com/photo-1551836022-deb4988cc6c0?w=400",
                "lessons": [
                    {"title": "Soil-Water-Plant Relationships", "duration": 16, "content": "Understanding how plants use water and soil moisture dynamics."},
                    {"title": "Irrigation Scheduling", "duration": 18, "content": "Determining when and how much to irrigate."},
                    {"title": "Water-Saving Techniques", "duration": 15, "content": "Mulching, conservation tillage, and other water-saving methods."},
                    {"title": "Rainwater Harvesting", "duration": 14, "content": "Collecting and storing rainwater for agricultural use."},
                    {"title": "Drought Management", "duration": 12, "content": "Strategies for managing crops during water scarcity."}
                ]
            },
            
            # Farm Technology Courses
            {
                "title": "Precision Agriculture Basics",
                "description": "Introduction to precision agriculture technologies and their benefits for modern farming.",
                "category": category_map["Farm Technology"],
                "level": "intermediate",
                "duration_weeks": 5,
                "language": "English",
                "instructor": "Prof. Srinivasa Rao",
                "image_url": "https://images.unsplash.com/photo-1599393974932-9a3b1a3a1a3a?w=400",
                "lessons": [
                    {"title": "Introduction to Precision Agriculture", "duration": 15, "content": "Overview of precision agriculture and its components."},
                    {"title": "GPS and GIS in Farming", "duration": 18, "content": "Using GPS and GIS for farm mapping and management."},
                    {"title": "Variable Rate Technology", "duration": 16, "content": "Applying inputs at variable rates based on field variability."},
                    {"title": "Remote Sensing Applications", "duration": 14, "content": "Using satellite and drone imagery for crop monitoring."},
                    {"title": "Yield Monitoring Systems", "duration": 12, "content": "Measuring and analyzing crop yields with modern equipment."}
                ]
            },
            {
                "title": "Farm Machinery Operation and Maintenance",
                "description": "Learn proper operation and maintenance of common farm machinery for efficiency and safety.",
                "category": category_map["Farm Technology"],
                "level": "beginner",
                "duration_weeks": 3,
                "language": "English",
                "instructor": "Prof. Srinivasa Rao",
                "image_url": "https://images.unsplash.com/photo-1581092160562-40aa08e78837?w=400",
                "lessons": [
                    {"title": "Tractor Safety and Operation", "duration": 18, "content": "Safe operation and basic maintenance of tractors."},
                    {"title": "Ploughs and Cultivators", "duration": 14, "content": "Operation and maintenance of primary and secondary tillage equipment."},
                    {"title": "Seed Drills and Planters", "duration": 16, "content": "Proper use of seeding equipment for different crops."},
                    {"title": "Harvesting Machinery", "duration": 15, "content": "Operation of combine harvesters and other harvesting equipment."},
                    {"title": "Implements Maintenance", "duration": 12, "content": "Routine maintenance and troubleshooting of farm implements."}
                ]
            },
            
            # Livestock Courses
            {
                "title": "Dairy Farming Management",
                "description": "Comprehensive guide to starting and managing a successful dairy farm.",
                "category": category_map["Livestock"],
                "level": "intermediate",
                "duration_weeks": 6,
                "language": "English",
                "instructor": "Dr. Lakshmi Devi",
                "image_url": "https://images.unsplash.com/photo-1574323347407-f5e1ad6d020b?w=400",
                "lessons": [
                    {"title": "Breed Selection for Dairy", "duration": 18, "content": "Choosing high-yielding dairy cattle breeds."},
                    {"title": "Housing and Shelter Design", "duration": 16, "content": "Designing comfortable and hygienic housing for dairy animals."},
                    {"title": "Feeding and Nutrition", "duration": 20, "content": "Balanced ration formulation and feeding practices."},
                    {"title": "Health Management", "duration": 18, "content": "Common diseases and their prevention in dairy animals."},
                    {"title": "Breeding and Reproduction", "duration": 15, "content": "Artificial insemination and heat detection techniques."},
                    {"title": "Milk Production Management", "duration": 14, "content": "Hygienic milking practices and quality control."}
                ]
            },
            {
                "title": "Poultry Farming for Beginners",
                "description": "Step-by-step guide to starting and managing a profitable poultry farm.",
                "category": category_map["Livestock"],
                "level": "beginner",
                "duration_weeks": 4,
                "language": "English",
                "instructor": "Dr. Lakshmi Devi",
                "image_url": "https://images.unsplash.com/photo-1580489944761-15a19d654956?w=400",
                "lessons": [
                    {"title": "Poultry Breed Selection", "duration": 15, "content": "Choosing the right poultry breeds for egg or meat production."},
                    {"title": "Hatchery Management", "duration": 14, "content": "Setting up and managing a small-scale hatchery."},
                    {"title": "Brooding Management", "duration": 16, "content": "Proper care and management of chicks during brooding period."},
                    {"title": "Feeding and Nutrition", "duration": 18, "content": "Balanced feed formulation and feeding schedules."},
                    {"title": "Disease Prevention and Control", "duration": 15, "content": "Common poultry diseases and vaccination schedules."},
                    {"title": "Egg Production Management", "duration": 12, "content": "Maximizing egg production through proper management."}
                ]
            },
            
            # Horticulture Courses
            {
                "title": "Vegetable Cultivation Techniques",
                "description": "Learn modern techniques for growing vegetables in different agro-climatic conditions.",
                "category": category_map["Horticulture"],
                "level": "beginner",
                "language": "English",
                "instructor": "Dr. Anitha Reddy",
                "image_url": "https://images.unsplash.com/photo-1560493676-04071c5f467b?w=400",
                "duration_weeks": 5,
                "lessons": [
                    {"title": "Site Selection and Preparation", "duration": 16, "content": "Choosing the right location and preparing the soil for vegetable cultivation."},
                    {"title": "Seedling Production", "duration": 14, "content": "Raising healthy seedlings in nurseries."},
                    {"title": "Transplanting Techniques", "duration": 15, "content": "Proper methods for transplanting vegetable seedlings."},
                    {"title": "Irrigation Management", "duration": 12, "content": "Water requirements and irrigation methods for vegetables."},
                    {"title": "Pest and Disease Control", "duration": 18, "content": "Identifying and managing common vegetable pests and diseases."},
                    {"title": "Harvesting and Post-Harvest", "duration": 14, "content": "Proper harvesting techniques and post-harvest handling."}
                ]
            },
            {
                "title": "Fruit Orchard Management",
                "description": "Complete guide to establishing and managing a successful fruit orchard.",
                "category": category_map["Horticulture"],
                "level": "intermediate",
                "duration_weeks": 8,
                "language": "English",
                "instructor": "Dr. Anitha Reddy",
                "image_url": "https://images.unsplash.com/photo-1599781283821-16814f78b5a0?w=400",
                "lessons": [
                    {"title": "Orchard Planning and Design", "duration": 20, "content": "Designing and planning a fruit orchard for maximum productivity."},
                    {"title": "Variety Selection", "duration": 16, "content": "Choosing fruit varieties suitable for your region and climate."},
                    {"title": "Planting Techniques", "duration": 14, "content": "Proper planting methods and spacing for different fruit trees."},
                    {"title": "Pruning and Training", "duration": 18, "content": "Pruning techniques for different fruit tree species."},
                    {"title": "Fertilization and Irrigation", "duration": 15, "content": "Balanced fertilization and irrigation scheduling for fruit trees."},
                    {"title": "Pest and Disease Management", "duration": 16, "content": "Identifying and controlling common fruit tree pests and diseases."},
                    {"title": "Harvesting and Post-Harvest", "duration": 12, "content": "Proper harvesting techniques and post-harvest handling."}
                ]
            },
            
            # Sustainable Farming Courses
            {
                "title": "Sustainable Agriculture Practices",
                "description": "Learn sustainable farming techniques that protect the environment while maintaining productivity.",
                "category": category_map["Sustainable Farming"],
                "level": "intermediate",
                "duration_weeks": 6,
                "language": "English",
                "instructor": "Dr. Kavitha Sharma",
                "image_url": "https://images.unsplash.com/photo-1500382017468-9049fed747ef?w=400",
                "lessons": [
                    {"title": "Principles of Sustainable Agriculture", "duration": 15, "content": "Understanding the core principles of sustainable farming."},
                    {"title": "Conservation Agriculture", "duration": 18, "content": "Minimum tillage, crop residue management, and crop rotation."},
                    {"title": "Agroforestry Systems", "duration": 16, "content": "Integrating trees with crops and livestock for multiple benefits."},
                    {"title": "Water Conservation", "duration": 14, "content": "Techniques for conserving water in agriculture."},
                    {"title": "Soil Conservation", "duration": 15, "content": "Methods to prevent soil erosion and maintain soil health."},
                    {"title": "Biodiversity Conservation", "duration": 12, "content": "Maintaining biodiversity on farms for ecological balance."}
                ]
            },
            {
                "title": "Climate-Smart Farming",
                "description": "Adapt your farming practices to changing climate conditions for resilience and productivity.",
                "category": category_map["Sustainable Farming"],
                "level": "advanced",
                "duration_weeks": 5,
                "language": "English",
                "instructor": "Prof. Srinivasa Rao",
                "image_url": "https://images.unsplash.com/photo-1466611653911-95081537e5b7?w=400",
                "lessons": [
                    {"title": "Climate Change and Agriculture", "duration": 16, "content": "Understanding climate change impacts on agriculture."},
                    {"title": "Drought-Resistant Crops", "duration": 14, "content": "Identifying and cultivating drought-resistant crop varieties."},
                    {"title": "Heat-Tolerant Varieties", "duration": 12, "content": "Selecting crop varieties that tolerate high temperatures."},
                    {"title": "Water-Efficient Irrigation", "duration": 18, "content": "Implementing water-efficient irrigation systems."},
                    {"title": "Crop Diversification", "duration": 15, "content": "Diversifying crops to spread climate-related risks."}
                ]
            },
            
            # Farm Finance Courses
            {
                "title": "Agricultural Financial Management",
                "description": "Learn essential financial management skills for running a profitable farm business.",
                "category": category_map["Farm Finance"],
                "level": "beginner",
                "duration_weeks": 4,
                "language": "English",
                "instructor": "Dr. Lakshmi Devi",
                "image_url": "https://images.unsplash.com/photo-1567191899446-433c3c9405b3?w=400",
                "lessons": [
                    {"title": "Farm Budgeting Basics", "duration": 15, "content": "Creating and managing farm budgets."},
                    {"title": "Cost-Benefit Analysis", "duration": 18, "content": "Evaluating the financial viability of farming decisions."},
                    {"title": "Record Keeping", "duration": 14, "content": "Maintaining proper farm financial records."},
                    {"title": "Government Subsidies and Schemes", "duration": 16, "content": "Understanding and accessing government agricultural subsidies."},
                    {"title": "Risk Management", "duration": 12, "content": "Strategies for managing financial risks in farming."}
                ]
            },
            {
                "title": "Farm Marketing and Sales",
                "description": "Learn effective marketing strategies to sell your farm products at better prices.",
                "category": category_map["Farm Finance"],
                "level": "intermediate",
                "duration_weeks": 3,
                "language": "English",
                "instructor": "Dr. Lakshmi Devi",
                "image_url": "https://images.unsplash.com/photo-1590912731627-57b645103a42?w=400",
                "lessons": [
                    {"title": "Market Research", "duration": 14, "content": "Understanding market demand and pricing."},
                    {"title": "Value Addition", "duration": 16, "content": "Adding value to farm products through processing."},
                    {"title": "Direct Marketing", "duration": 15, "content": "Selling directly to consumers through farmers markets and CSAs."},
                    {"title": "Online Marketing", "duration": 12, "content": "Using digital platforms to market farm products."},
                    {"title": "Contract Farming", "duration": 14, "content": "Understanding and negotiating contract farming agreements."}
                ]
            },
            
            # Modern Farming Courses
            {
                "title": "Hydroponics Farming",
                "description": "Learn soil-less farming techniques using hydroponic systems for higher yields.",
                "category": category_map["Modern Farming"],
                "level": "advanced",
                "duration_weeks": 6,
                "language": "English",
                "instructor": "Dr. Venkateshwar Rao",
                "image_url": "https://images.unsplash.com/photo-1585435557345-6c1e8a0c6b8c?w=400",
                "lessons": [
                    {"title": "Introduction to Hydroponics", "duration": 16, "content": "Principles and types of hydroponic systems."},
                    {"title": "System Design", "duration": 20, "content": "Designing and setting up hydroponic systems."},
                    {"title": "Nutrient Solution Management", "duration": 18, "content": "Preparing and managing nutrient solutions."},
                    {"title": "Crop Selection and Cultivation", "duration": 15, "content": "Choosing crops and cultivation techniques for hydroponics."},
                    {"title": "Pest and Disease Management", "duration": 14, "content": "Controlling pests and diseases in hydroponic systems."},
                    {"title": "Harvesting and Post-Harvest", "duration": 12, "content": "Proper harvesting and handling of hydroponic crops."}
                ]
            },
            {
                "title": "Aquaponics Systems",
                "description": "Learn to integrate fish farming with plant cultivation in aquaponic systems.",
                "category": category_map["Modern Farming"],
                "level": "advanced",
                "duration_weeks": 7,
                "language": "English",
                "instructor": "Dr. Venkateshwar Rao",
                "image_url": "https://images.unsplash.com/photo-1574323347407-f5e1ad6d020b?w=400",
                "lessons": [
                    {"title": "Introduction to Aquaponics", "duration": 15, "content": "Principles and benefits of aquaponic systems."},
                    {"title": "System Design", "duration": 22, "content": "Designing and building aquaponic systems."},
                    {"title": "Fish Selection and Management", "duration": 18, "content": "Choosing fish species and managing fish health."},
                    {"title": "Plant Cultivation", "duration": 16, "content": "Growing plants in aquaponic systems."},
                    {"title": "Water Quality Management", "duration": 14, "content": "Maintaining optimal water quality for fish and plants."},
                    {"title": "System Maintenance", "duration": 12, "content": "Routine maintenance and troubleshooting."}
                ]
            },
            
            # Government Schemes Courses
            {
                "title": "PM-KISAN Scheme: Complete Guide",
                "description": "Learn how to apply for and benefit from the PM-KISAN scheme for income support.",
                "category": category_map["Government Schemes"],
                "level": "beginner",
                "duration_weeks": 2,
                "language": "English",
                "instructor": "Dr. Lakshmi Devi",
                "image_url": "https://images.unsplash.com/photo-1551836022-deb4988cc6c0?w=400",
                "lessons": [
                    {"title": "Understanding PM-KISAN Scheme", "duration": 14, "content": "Eligibility criteria and benefits of PM-KISAN."},
                    {"title": "Registration Process", "duration": 16, "content": "Step-by-step registration guide."},
                    {"title": "Documentation Required", "duration": 12, "content": "List of required documents for registration."},
                    {"title": "Installment Payments", "duration": 10, "content": "Understanding installment structure and payment schedule."},
                    {"title": "Troubleshooting Issues", "duration": 12, "content": "Common issues and their solutions."}
                ]
            },
            {
                "title": "PMFBY: Crop Insurance Guide",
                "description": "Learn how to protect your crops from natural calamities through PMFBY insurance.",
                "category": category_map["Government Schemes"],
                "level": "beginner",
                "duration_weeks": 3,
                "language": "English",
                "instructor": "Dr. Lakshmi Devi",
                "image_url": "https://images.unsplash.com/photo-1599393974932-9a3b1a3a1a3a?w=400",
                "lessons": [
                    {"title": "Understanding PMFBY", "duration": 15, "content": "Principles and coverage of PMFBY insurance."},
                    {"title": "Enrollment Process", "duration": 18, "content": "How to enroll your crops in PMFBY."},
                    {"title": "Premium Calculation", "duration": 14, "content": "Understanding premium rates and government subsidies."},
                    {"title": "Claim Process", "duration": 16, "content": "Step-by-step guide to filing insurance claims."},
                    {"title": "Documentation", "duration": 12, "content": "Required documents for enrollment and claims."}
                ]
            },
            {
                "title": "Kisan Credit Card (KCC) Scheme",
                "description": "Learn how to access easy credit through Kisan Credit Card for your farming needs.",
                "category": category_map["Government Schemes"],
                "level": "beginner",
                "duration_weeks": 2,
                "language": "English",
                "instructor": "Dr. Lakshmi Devi",
                "image_url": "https://images.unsplash.com/photo-1560493676-04071c5f467b?w=400",
                "lessons": [
                    {"title": "Understanding KCC Scheme", "duration": 14, "content": "Features and benefits of Kisan Credit Card."},
                    {"title": "Eligibility Criteria", "duration": 12, "content": "Who can apply for KCC and required documents."},
                    {"title": "Application Process", "duration": 16, "content": "Step-by-step application guide."},
                    {"title": "Credit Limit Calculation", "duration": 14, "content": "How banks calculate your credit limit."},
                    {"title": "Repayment and Interest", "duration": 12, "content": "Repayment terms and interest rates."}
                ]
            },
            {
                "title": "Soil Health Card Scheme",
                "description": "Learn how to use Soil Health Cards to improve your farm productivity.",
                "category": category_map["Government Schemes"],
                "level": "beginner",
                "duration_weeks": 2,
                "language": "English",
                "instructor": "Dr. Venkateshwar Rao",
                "image_url": "https://images.unsplash.com/photo-1574323347407-f5e1ad6d020b?w=400",
                "lessons": [
                    {"title": "Understanding Soil Health Cards", "duration": 15, "content": "What is Soil Health Card and how to read it."},
                    {"title": "Soil Testing Process", "duration": 16, "content": "How soil samples are tested and analyzed."},
                    {"title": "Interpreting Results", "duration": 18, "content": "Understanding the recommendations on your Soil Health Card."},
                    {"title": "Implementing Recommendations", "duration": 14, "content": "Practical ways to implement soil health card recommendations."},
                    {"title": "Monitoring Soil Health", "duration": 12, "content": "Regular soil testing and monitoring practices."}
                ]
            },
            {
                "title": "Organic Farming Certification",
                "description": "Learn the process and requirements for organic farming certification.",
                "category": category_map["Government Schemes"],
                "level": "intermediate",
                "duration_weeks": 4,
                "language": "English",
                "instructor": "Dr. Kavitha Sharma",
                "image_url": "https://images.unsplash.com/photo-1466611653911-95081537e5b7?w=400",
                "lessons": [
                    {"title": "Introduction to Organic Certification", "duration": 15, "content": "Understanding organic certification standards."},
                    {"title": "Certification Process", "duration": 18, "content": "Step-by-step guide to getting certified."},
                    {"title": "Documentation Requirements", "duration": 14, "content": "Required documents and records."},
                    {"title": "Inspection Process", "duration": 12, "content": "What to expect during certification inspection."},
                    {"title": "Maintaining Certification", "duration": 16, "content": "Requirements for maintaining organic certification."}
                ]
            },
            {
                "title": "Natural Farming Promotion Scheme",
                "description": "Learn about government schemes supporting natural farming practices.",
                "category": category_map["Government Schemes"],
                "level": "beginner",
                "duration_weeks": 2,
                "language": "English",
                "instructor": "Dr. Kavitha Sharma",
                "image_url": "https://images.unsplash.com/photo-1500382017468-9049fed747ef?w=400",
                "lessons": [
                    {"title": "Government Support for Natural Farming", "duration": 14, "content": "Overview of schemes supporting natural farming."},
                    {"title": "Subsidy Programs", "duration": 16, "content": "Available subsidies for natural farming inputs."},
                    {"title": "Training and Capacity Building", "duration": 12, "content": "Government training programs and resources."},
                    {"title": "Certification Support", "duration": 14, "content": "Schemes for organic/natural certification."},
                    {"title": "Market Linkages", "duration": 12, "content": "Government programs for connecting farmers to markets."}
                ]
            },
            {
                "title": "Farm Mechanization Subsidies",
                "description": "Learn about government subsidies for farm machinery and equipment.",
                "category": category_map["Government Schemes"],
                "level": "beginner",
                "duration_weeks": 2,
                "language": "English",
                "instructor": "Prof. Srinivasa Rao",
                "image_url": "https://images.unsplash.com/photo-1581092160562-40aa08e78837?w=400",
                "lessons": [
                    {"title": "Understanding Farm Mechanization Subsidies", "duration": 15, "content": "Types of machinery covered and subsidy rates."},
                    {"title": "Eligibility Criteria", "duration": 14, "content": "Who can apply and required documents."},
                    {"title": "Application Process", "duration": 16, "content": "Step-by-step guide to applying for subsidies."},
                    {"title": "Dealer Selection", "duration": 12, "content": "Choosing authorized dealers and equipment."},
                    {"title": "Claim Process", "duration": 14, "content": "How to claim the subsidy after purchase."}
                ]
            },
            {
                "title": "Agri-Infrastructure Development",
                "description": "Learn about government schemes for developing agricultural infrastructure.",
                "category": category_map["Government Schemes"],
                "level": "intermediate",
                "duration_weeks": 3,
                "language": "English",
                "instructor": "Prof. Srinivasa Rao",
                "image_url": "https://images.unsplash.com/photo-1599393974932-9a3b1a3a1a3a?w=400",
                "lessons": [
                    {"title": "Infrastructure Development Schemes", "duration": 18, "content": "Overview of schemes for farm infrastructure."},
                    {"title": "Cold Storage Subsidies", "duration": 14, "content": "Subsidies for building cold storage facilities."},
                    {"title": "Packhouse Construction", "duration": 12, "content": "Subsidies for post-harvest infrastructure."},
                    {"title": "Irrigation Infrastructure", "duration": 16, "content": "Schemes for irrigation infrastructure development."},
                    {"title": "Application Process", "duration": 14, "content": "How to apply for infrastructure development subsidies."}
                ]
            }
        ]
        
        # Create courses and lessons
        created_courses = []
        for course_data in course_data:
            # Create course
            course = Course(
                course_id=generate_id("FA-CRS", db, Course),
                title=course_data["title"],
                description=course_data["description"],
                category=course_data["category"],
                level=course_data["level"],
                duration_weeks=course_data["duration_weeks"],
                language=course_data["language"],
                instructor=course_data["instructor"],
                image_url=course_data["image_url"],
                total_lessons=len(course_data["lessons"]),
                is_published=True
            )
            db.add(course)
            db.flush()
            created_courses.append(course)
            
            # Create lessons
            for i, lesson_data in enumerate(course_data["lessons"]):
                lesson = CourseLesson(
                    lesson_id=generate_id("FA-LESSON", db, CourseLesson),
                    course_id=course.id,
                    title=lesson_data["title"],
                    description=lesson_data["content"],
                    content=lesson_data["content"],
                    content_type="text",
                    order_index=i,
                    duration_minutes=lesson_data["duration"],
                    is_published=True
                )
                db.add(lesson)
        
        db.commit()
        
        print(f"  Learning Courses: {len(created_courses)}")
        print(f"  Total Lessons: {sum(len(c["lessons"]) for c in course_data)}")
        
        # Seed additional users for testing data isolation
        print("Seeding additional test users...")
        for i in range(2):
            test_user = User(
                full_name=f"Farmer Test {i+1}",
                phone_number=f"+91987654321{i+2}",
                email=f"test{i+1}@farmassist.com",
                password_hash=hash_password("1234"),
                preferred_language="en",
                role="farmer",
                is_verified=True,
                is_active=True,
            )
            db.add(test_user)
            db.flush()
            test_user.farmer_id = generate_farmer_id(db)
            db.add(FarmerProfile(
                user_id=test_user.id,
                farmer_id=test_user.farmer_id,
                gender="male",
                occupation="Farmer",
                farming_experience=f"{5+i*5}+ years",
                preferred_crops="Rice,Wheat",
            ))
            db.add(UserAddress(
                user_id=test_user.id,
                address_line=f"Test Farm {i+1}",
                village=f"TestVillage{i+1}",
                mandal="TestMandal",
                district="TestDistrict",
                state="Telangana",
                country="India",
                pincode=f"50800{i+2}",
                latitude=17.0575 + i * 0.1,
                longitude=79.2820 + i * 0.1,
                is_primary=True,
            ))
        
        db.commit()
        
        print("Seed complete!")
        print(f"  Login: +919876543210 / PIN: 1234")
        print(f"  Farmer ID: {user.farmer_id}")
        print(f"  Learning Courses: {len(created_courses)}")
        print(f"  Total Lessons: {sum(len(c["lessons"]) for c in course_data)}")
        print(f"  Learning Course Enrollments: {db.query(CourseEnrollment).count()}")
        print(f"  Lesson Progress Records: {db.query(LessonProgress).count()}")
        print(f"  Farms: {db.query(Farm).count()}")
        print(f"  Plots: {db.query(FarmPlot).count()}")
        print(f"  Crops: {db.query(Crop).count()}")
        print(f"  Crop Cycles: {db.query(CropCycle).count()}")

    except Exception as e:
        db.rollback()
        print(f"Error: {e}")
        import traceback; traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    seed_database()
