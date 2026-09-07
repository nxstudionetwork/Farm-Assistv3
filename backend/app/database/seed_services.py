"""
Database Seeder for 248 Agriculture Services across 25 Major Categories.

Categories (10 services each, except the last which has 8):
 1.  crop-cultivation        - Crop Cultivation
 2.  seeds-planting          - Seeds & Planting
 3.  soil-health             - Soil Testing & Soil Health
 4.  fertilizers-nutrients   - Fertilizer & Nutrient Management
 5.  pest-management         - Pest Management
 6.  crop-disease            - Crop Disease Management
 7.  irrigation-water        - Irrigation & Water Management
 8.  farm-machinery          - Farm Equipment & Machinery
 9.  farm-labour             - Farm Labour
 10. harvesting              - Harvesting Services
 11. post-harvest            - Post-Harvest Management
 12. storage-warehousing     - Storage & Warehousing
 13. transport-logistics     - Transportation & Logistics
 14. livestock               - Livestock Management
 15. veterinary              - Veterinary Services
 16. dairy-poultry           - Dairy & Poultry
 17. organic-farming         - Organic & Natural Farming
 18. sustainable-agri        - Sustainable Agriculture
 19. government-schemes      - Government Agriculture Services
 20. agri-finance            - Agricultural Finance
 21. crop-insurance          - Crop Insurance
 22. expert-consultancy      - Agricultural Experts & Consultancy
 23. market-selling          - Market & Selling Support
 24. agri-technology         - Farm Technology & Smart Farming
 25. other-services          - Other Agriculture Services

The seeder is idempotent and self-healing: if the active catalog does not
exactly match this module's catalog, the table is rebuilt from scratch so the
database always reflects the canonical catalog.
"""

from sqlalchemy.orm import Session
from app.models.service import AgriculturalService

CATEGORY_META = {
    "crop-cultivation": {
        "label": "Crop Cultivation", "icon": "fa-seedling", "color": "#1B5E3F",
        "response_time": "< 2 hours", "duration": "2 to 4 Hours (On-Site Execution)",
        "provider": "Farm Assist Agronomy Panel",
    },
    "seeds-planting": {
        "label": "Seeds & Planting", "icon": "fa-spa", "color": "#2D8659",
        "response_time": "< 2 hours", "duration": "1 to 2 Hours (Advisory Session)",
        "provider": "State Seed Certification Cell",
    },
    "soil-health": {
        "label": "Soil Testing & Soil Health", "icon": "fa-flask-vial", "color": "#8D6E63",
        "response_time": "< 1 hour", "duration": "Laboratory: 3-5 Working Days",
        "provider": "Soil Testing Laboratory Network",
    },
    "fertilizers-nutrients": {
        "label": "Fertilizer & Nutrient Management", "icon": "fa-vial-circle-check", "color": "#388E3C",
        "response_time": "< 2 hours", "duration": "1 to 2 Hours (Advisory Session)",
        "provider": "Farm Assist Nutrient Desk",
    },
    "pest-management": {
        "label": "Pest Management", "icon": "fa-bug", "color": "#C62828",
        "response_time": "< 1 hour", "duration": "1 to 2 Hours (Field Inspection)",
        "provider": "Pest Surveillance Unit",
    },
    "crop-disease": {
        "label": "Crop Disease Management", "icon": "fa-shield-virus", "color": "#6A1B9A",
        "response_time": "< 1 hour", "duration": "Lab Diagnosis: 2-3 Working Days",
        "provider": "Plant Pathology Clinic",
    },
    "irrigation-water": {
        "label": "Irrigation & Water Management", "icon": "fa-droplet", "color": "#0277BD",
        "response_time": "24 hours", "duration": "Site Survey: Half Day",
        "provider": "Irrigation Engineering Cell",
    },
    "farm-machinery": {
        "label": "Farm Equipment & Machinery", "icon": "fa-tractor", "color": "#4E342E",
        "response_time": "< 24 hours", "duration": "Per Hire / Daily Basis",
        "provider": "Community Machinery Bank",
    },
    "farm-labour": {
        "label": "Farm Labour", "icon": "fa-people-roof", "color": "#F9A825",
        "response_time": "< 6 hours", "duration": "Daily Basis (8 Hours)",
        "provider": "Farm Labour Cooperative",
    },
    "harvesting": {
        "label": "Harvesting Services", "icon": "fa-wheat-awn", "color": "#E65100",
        "response_time": "< 24 hours", "duration": "Per Acre / Per Day",
        "provider": "Harvest Operations Squad",
    },
    "post-harvest": {
        "label": "Post-Harvest Management", "icon": "fa-boxes-stacked", "color": "#795548",
        "response_time": "24 hours", "duration": "Per Quintal / Per Batch",
        "provider": "Post-Harvest Technology Centre",
    },
    "storage-warehousing": {
        "label": "Storage & Warehousing", "icon": "fa-warehouse", "color": "#37474F",
        "response_time": "24 hours", "duration": "Monthly Storage Contract",
        "provider": "Central Warehousing Corridor",
    },
    "transport-logistics": {
        "label": "Transportation & Logistics", "icon": "fa-truck-fast", "color": "#00695C",
        "response_time": "< 6 hours", "duration": "Per Trip / Per Km",
        "provider": "Farm Logistics Network",
    },
    "livestock": {
        "label": "Livestock Management", "icon": "fa-cow", "color": "#5D4037",
        "response_time": "< 6 hours", "duration": "Per Visit / Per Head",
        "provider": "Livestock Development Board",
    },
    "veterinary": {
        "label": "Veterinary Services", "icon": "fa-stethoscope", "color": "#AD1457",
        "response_time": "< 1 hour", "duration": "45-60 Minutes (Visit)",
        "provider": "District Veterinary Hospital",
    },
    "dairy-poultry": {
        "label": "Dairy & Poultry", "icon": "fa-egg", "color": "#EF6C00",
        "response_time": "< 6 hours", "duration": "Per Session / Per Batch",
        "provider": "Dairy & Poultry Extension Centre",
    },
    "organic-farming": {
        "label": "Organic & Natural Farming", "icon": "fa-leaf", "color": "#43A047",
        "response_time": "2-3 days", "duration": "Training Workshop: 1 Day",
        "provider": "Organic Farming Mission",
    },
    "sustainable-agri": {
        "label": "Sustainable Agriculture", "icon": "fa-recycle", "color": "#2E7D32",
        "response_time": "2-3 days", "duration": "Planning: 1 to 2 Days",
        "provider": "Sustainable Agriculture Cell",
    },
    "government-schemes": {
        "label": "Government Agriculture Services", "icon": "fa-landmark", "color": "#283593",
        "response_time": "2-3 days", "duration": "3-5 Working Days (Processing)",
        "provider": "District Agriculture Office",
    },
    "agri-finance": {
        "label": "Agricultural Finance", "icon": "fa-coins", "color": "#B8860B",
        "response_time": "< 24 hours", "duration": "2-3 Working Days (Processing)",
        "provider": "Farm Financial Services Desk",
    },
    "crop-insurance": {
        "label": "Crop Insurance", "icon": "fa-shield-halved", "color": "#1565C0",
        "response_time": "2-3 days", "duration": "3-7 Working Days (Processing)",
        "provider": "Agri Insurance Cell",
    },
    "expert-consultancy": {
        "label": "Agricultural Experts & Consultancy", "icon": "fa-user-tie", "color": "#00695C",
        "response_time": "< 2 hours", "duration": "45-60 Minutes (Consultation)",
        "provider": "Farm Assist Expert Network",
    },
    "market-selling": {
        "label": "Market & Selling Support", "icon": "fa-chart-line", "color": "#E65100",
        "response_time": "< 3 hours", "duration": "Per Advisory Session",
        "provider": "Mandi Market Advisory Cell",
    },
    "agri-technology": {
        "label": "Farm Technology & Smart Farming", "icon": "fa-satellite-dish", "color": "#4527A0",
        "response_time": "< 24 hours", "duration": "Installation: Half to Full Day",
        "provider": "AgriTech Innovation Hub",
    },
    "other-services": {
        "label": "Other Agriculture Services", "icon": "fa-box-open", "color": "#546E7A",
        "response_time": "< 24 hours", "duration": "Depends on Scope",
        "provider": "Farm Assist Service Cell",
    },
}

AVAILABILITY_CYCLE = [
    "available", "available", "available", "limited", "available",
    "busy", "available", "available", "limited", "available", "available",
]


def get_service_details(data: dict) -> dict:
    desc = data.get("description", "")
    full_desc = data.get("full_description") or (
        f"{desc} Executed by certified specialists using scientific protocols and modern "
        f"farm tools to improve productivity, lower input costs, and protect long-term farm health."
    )
    deliverables = data.get("deliverables") or (
        "• On-field assessment or laboratory testing as applicable\n"
        "• Digital advisory report with step-by-step guidance\n"
        "• Customized input & application schedule\n"
        "• Direct specialist telephone and chat follow-up"
    )
    eligibility = data.get("eligibility") or (
        "All registered farmers, land owners, and agricultural leaseholders with verified farm records."
    )
    duration = data.get("service_duration") or CATEGORY_META[data["category"]]["duration"]
    docs = data.get("required_documents") or "Farmer ID, Land Record Copy (Khatian/7-12), Farm Plot Photo"
    return {
        "full_description": full_desc,
        "deliverables": deliverables,
        "eligibility": eligibility,
        "service_duration": duration,
        "required_documents": docs,
    }


def build_service(data: dict, idx: int) -> dict:
    meta = CATEGORY_META[data["category"]]
    details = get_service_details(data)
    availability = data.get("availability") or AVAILABILITY_CYCLE[idx % len(AVAILABILITY_CYCLE)]
    return {
        "service_id": data["service_id"],
        "name": data["name"],
        "category": data["category"],
        "description": data["description"],
        "full_description": details["full_description"],
        "deliverables": details["deliverables"],
        "eligibility": details["eligibility"],
        "service_duration": details["service_duration"],
        "required_documents": details["required_documents"],
        "icon": meta["icon"],
        "color": meta["color"],
        "availability": availability,
        "response_time": meta["response_time"],
        "price_info": data.get("price_info", "Free Consultation"),
        "provider_name": data.get("provider_name", meta["provider"]),
        "location_coverage": "All Districts",
        "rating": data.get("rating", 4.8),
        "is_active": True,
    }


SERVICES_CATALOG = [
    {"service_id": "FA-SVC-000001", "name": "Land Preparation & Field Layout Planning", "description": "Soil profiling, proper land leveling, and layout design to maximize sowing efficiency and water distribution across the farm.", "category": "crop-cultivation", "price_info": "₹600 / acre", "rating": 4.9},
    {"service_id": "FA-SVC-000002", "name": "Soil Health Assessment & Fertility Mapping", "description": "Field-level soil physical and biological assessment with GPS fertility mapping to plan seasonal nutrient application.", "category": "crop-cultivation", "price_info": "₹750 / acre", "rating": 4.8},
    {"service_id": "FA-SVC-000003", "name": "Crop Selection & Sowing Schedule Planning", "description": "Selection of the right crop and variety for your soil, climate, and market, with a complete sowing-to-harvest calendar.", "category": "crop-cultivation", "price_info": "₹450 / consultation", "rating": 4.8},
    {"service_id": "FA-SVC-000004", "name": "Precision Land Leveling for Water Uniformity", "description": "Laser-assisted land leveling service that flattens fields for uniform irrigation, better germination, and reduced water wastage.", "category": "crop-cultivation", "price_info": "₹900 / acre", "rating": 4.7},
    {"service_id": "FA-SVC-000005", "name": "Seedbed Preparation & Nursery Raising", "description": "Raised bed and nursery preparation with proper media mix, germination checks, and hardening for healthy transplant-ready seedlings.", "category": "crop-cultivation", "price_info": "₹550 / acre", "rating": 4.6},
    {"service_id": "FA-SVC-000006", "name": "Crop Rotation & Intercropping Planning", "description": "Rotation and intercropping plans that break pest cycles, improve soil fertility, and increase income per unit of land.", "category": "crop-cultivation", "price_info": "₹500 / acre", "rating": 4.8},
    {"service_id": "FA-SVC-000007", "name": "High-Density Plantation Establishment", "description": "High-density plantation layout, pit preparation, and planting guidance for orchards and vegetable crops with faster returns.", "category": "crop-cultivation", "price_info": "₹1,800 / acre", "rating": 4.7},
    {"service_id": "FA-SVC-000008", "name": "Mulching & Drip Layout Design", "description": "Plastic and organic mulching with drip line layout design to control weeds, conserve moisture, and reduce labour.", "category": "crop-cultivation", "price_info": "₹900 / acre", "rating": 4.5},
    {"service_id": "FA-SVC-000009", "name": "Greenhouse & Shade-Net Structure Setup", "description": "Turnkey procurement and erection of protected cultivation structures with climate control guidance for high-value crops.", "category": "crop-cultivation", "price_info": "₹15,000 / structure", "rating": 4.6},
    {"service_id": "FA-SVC-000010", "name": "Organic Land Preparation for Cash Crops", "description": "Green-manure incorporation, compost application, and biological activation of soil for organic cash crop production.", "category": "crop-cultivation", "price_info": "₹700 / acre", "rating": 4.7},
    {"service_id": "FA-SVC-000011", "name": "Certified Seed Selection & Viability Testing", "description": "Laboratory germination, purity, and moisture testing of seed lots to ensure certified, high-yield planting material.", "category": "seeds-planting", "price_info": "₹350 / sample", "rating": 4.8},
    {"service_id": "FA-SVC-000012", "name": "Hybrid Seed Procurement & Sowing Guidance", "description": "Sourcing of genuine hybrid seeds with sowing method, seed rate, and spacing guidance for targeted crops.", "category": "seeds-planting", "price_info": "₹300 / consultation", "rating": 4.7},
    {"service_id": "FA-SVC-000013", "name": "Direct Seeding & Line Sowing Services", "description": "Machine-driven direct seeding and line sowing using drum and multi-crop planters to reduce labour and ensure uniform stand.", "category": "seeds-planting", "price_info": "₹1,200 / acre", "rating": 4.6},
    {"service_id": "FA-SVC-000014", "name": "Seed Treatment & Bio-Priming Protocols", "description": "Fungicide, insecticide, and bio-priming treatments applied before sowing to protect seeds from soil-borne diseases.", "category": "seeds-planting", "price_info": "₹200 / acre", "rating": 4.8},
    {"service_id": "FA-SVC-000015", "name": "Transplanting Services (Paddy, Vegetables, Chillies)", "description": "Skilled labour for timely transplanting of paddy, vegetables, and chilli with correct plant spacing and depth.", "category": "seeds-planting", "price_info": "₹2,200 / acre", "rating": 4.6},
    {"service_id": "FA-SVC-000016", "name": "Tissue-Cultured Plantlet Supply & Planting", "description": "Supply and planting of disease-free tissue-cultured plantlets for banana, sugarcane, and high-value horticulture.", "category": "seeds-planting", "price_info": "₹8 / plantlet", "rating": 4.7},
    {"service_id": "FA-SVC-000017", "name": "Seed Multiplication & Custom Seed Production", "description": "Contract seed multiplication with certification support for growers wanting to produce quality seed for resale.", "category": "seeds-planting", "price_info": "₹1,500 / acre", "rating": 4.5},
    {"service_id": "FA-SVC-000018", "name": "Nursery Development & Maintenance Services", "description": "Setting up and maintaining a nursery with proper ports, irrigation, and hardening to supply quality seedlings year-round.", "category": "seeds-planting", "price_info": "₹3,000 / nursery", "rating": 4.6},
    {"service_id": "FA-SVC-000019", "name": "Sowing Depth & Spacing Calibration", "description": "Calibration of seed drills and planters for correct depth and spacing that improves germination and machinery efficiency.", "category": "seeds-planting", "price_info": "₹400 / visit", "rating": 4.7},
    {"service_id": "FA-SVC-000020", "name": "Seed Certification Assistance & Documentation", "description": "End-to-end help with seed certification applications, field inspection coordination, and tag documentation.", "category": "seeds-planting", "price_info": "₹600 / lot", "rating": 4.5},
    {"service_id": "FA-SVC-000021", "name": "Macro & Micro Nutrient Soil Test", "description": "Complete soil testing for macro and micro nutrients with fertilizer recommendation report from an accredited lab.", "category": "soil-health", "price_info": "₹950 / sample", "rating": 4.9},
    {"service_id": "FA-SVC-000022", "name": "pH & Electrical Conductivity Soil Analysis", "description": "Precise soil pH and EC analysis to assess acidity, alkalinity, and salinity for corrective amendment planning.", "category": "soil-health", "price_info": "₹350 / sample", "rating": 4.8},
    {"service_id": "FA-SVC-000023", "name": "Soil Organic Carbon (SOC) Testing", "description": "Determination of organic carbon content to guide compost and manure application for sustained soil fertility.", "category": "soil-health", "price_info": "₹450 / sample", "rating": 4.8},
    {"service_id": "FA-SVC-000024", "name": "Drip-Irrigation Water Suitability Test", "description": "Water analysis for pH, hardness, and salt content to prevent emitter clogging and crop damage under drip systems.", "category": "soil-health", "price_info": "₹700 / sample", "rating": 4.6},
    {"service_id": "FA-SVC-000025", "name": "Customized Soil Health Card & Advisory", "description": "Issue of individualized soil health card with crop-wise nutrient recommendations and follow-up advisory.", "category": "soil-health", "price_info": "₹500 / card", "rating": 4.9},
    {"service_id": "FA-SVC-000026", "name": "Heavy-Metal & Contaminant Soil Screening", "description": "Screening of soils for heavy metals and industrial contaminants to ensure safe cultivation of food crops.", "category": "soil-health", "price_info": "₹2,500 / sample", "rating": 4.7},
    {"service_id": "FA-SVC-000027", "name": "Bio-Inoculant Demand & Soil Biology Test", "description": "Assessment of beneficial microbial populations to plan bio-fertilizer inoculation and reduce chemical dependency.", "category": "soil-health", "price_info": "₹1,200 / sample", "rating": 4.6},
    {"service_id": "FA-SVC-000028", "name": "Salinity & Reclamation Advisory", "description": "Diagnosis of salt-affected soils with leaching, amendment, and crop-choice strategies for reclamation.", "category": "soil-health", "price_info": "₹600 / consultation", "rating": 4.7},
    {"service_id": "FA-SVC-000029", "name": "Soil Sample Collection & Lab Coordination", "description": "Trained collection of grid-wise soil samples with proper labelling and full coordination with accredited laboratories.", "category": "soil-health", "price_info": "₹250 / sample", "rating": 4.6},
    {"service_id": "FA-SVC-000030", "name": "Precision Soil Moisture Monitoring Plan", "description": "Installation guidance and monitoring schedule for soil moisture sensors to optimize irrigation timing and saving water.", "category": "soil-health", "price_info": "₹800 / acre", "rating": 4.5},
    {"service_id": "FA-SVC-000031", "name": "Customized Nutrient (NPK) Recommendation", "description": "Soil-test-based NPK dosing schedules tailored to crop stage, yield target, and local soil conditions.", "category": "fertilizers-nutrients", "price_info": "₹450 / consultation", "rating": 4.8},
    {"service_id": "FA-SVC-000032", "name": "Drip Fertigation Scheduling & Management", "description": "Weekly fertigation schedules with injector settings that deliver precise nutrient doses through the drip system.", "category": "fertilizers-nutrients", "price_info": "₹900 / acre", "rating": 4.7},
    {"service_id": "FA-SVC-000033", "name": "Micronutrient (Zn, Mn, B, Fe) Advisory", "description": "Detection and correction of micronutrient deficiencies through targeted soil and foliar application programs.", "category": "fertilizers-nutrients", "price_info": "₹400 / consultation", "rating": 4.7},
    {"service_id": "FA-SVC-000034", "name": "Foliar Spray Program Design", "description": "Stage-wise foliar nutrition and stimulant spray schedules for flowering, fruiting, and stress recovery.", "category": "fertilizers-nutrients", "price_info": "₹350 / consultation", "rating": 4.6},
    {"service_id": "FA-SVC-000035", "name": "Bio-Fertilizer & Compost Application Plan", "description": "Practical plan for compost, vermicompost, and bio-fertilizer application to rebuild soil organic matter.", "category": "fertilizers-nutrients", "price_info": "₹500 / acre", "rating": 4.8},
    {"service_id": "FA-SVC-000036", "name": "Urea DAP Coating & Granulation Guidance", "description": "Technical guidance on coating, blending, and granulation of straight fertilizers for efficient nutrient release.", "category": "fertilizers-nutrients", "price_info": "₹300 / session", "rating": 4.5},
    {"service_id": "FA-SVC-000037", "name": "Soil Ameliorant (Lime / Gypsum / Sulphur) Advisory", "description": "Rates and application guidance for lime, gypsum, and sulphur to correct acidic or sodic soil constraints.", "category": "fertilizers-nutrients", "price_info": "₹400 / consultation", "rating": 4.6},
    {"service_id": "FA-SVC-000038", "name": "Liquid Fertilizer & Plant-Stimulant Program", "description": "Design of liquid fertilizer and plant-stimulant programs for rapid crop response and higher yields.", "category": "fertilizers-nutrients", "price_info": "₹450 / consultation", "rating": 4.7},
    {"service_id": "FA-SVC-000039", "name": "Nutrient Deficiency Diagnosis (Field + Lab)", "description": "Visual field diagnosis combined with leaf tissue and soil testing to identify hidden nutrient deficiencies.", "category": "fertilizers-nutrients", "price_info": "₹800 / case", "rating": 4.8},
    {"service_id": "FA-SVC-000040", "name": "Fertilizer Storage, Mixing & Safety Training", "description": "On-farm training on safe fertilizer storage, correct mixing ratios, and protective equipment usage.", "category": "fertilizers-nutrients", "price_info": "₹600 / session", "rating": 4.5},
    {"service_id": "FA-SVC-000041", "name": "Field Pest Scouting & Surveillance", "description": "Systematic weekly scouting of fields for pest and beneficial insect populations with digital reporting.", "category": "pest-management", "price_info": "₹400 / acre", "rating": 4.8},
    {"service_id": "FA-SVC-000042", "name": "Integrated Pest Management (IPM) Plan", "description": "Complete IPM strategy combining cultural, mechanical, biological, and chemical controls for sustainable pest control.", "category": "pest-management", "price_info": "₹600 / consultation", "rating": 4.9},
    {"service_id": "FA-SVC-000043", "name": "Pheromone Trap Installation & Monitoring", "description": "Installation and weekly monitoring of pheromone traps for early detection of fruit borers and moths.", "category": "pest-management", "price_info": "₹350 / acre", "rating": 4.7},
    {"service_id": "FA-SVC-000044", "name": "Biological Control Agent Application", "description": "Releases and applications of parasitoids, predators, and microbial bio-pesticides against target pests.", "category": "pest-management", "price_info": "₹850 / acre", "rating": 4.7},
    {"service_id": "FA-SVC-000045", "name": "Systemic & Foliar Spray Recommendations", "description": "Dose, timing, and nozzle recommendations for systemic and contact sprays matched to the pest stage.", "category": "pest-management", "price_info": "₹300 / consultation", "rating": 4.6},
    {"service_id": "FA-SVC-000046", "name": "Rodent & Termite Control Services", "description": "Baiting, trapping, and soil barrier treatments for sustainable control of rodents and termites in fields and stores.", "category": "pest-management", "price_info": "₹1,200 / acre", "rating": 4.6},
    {"service_id": "FA-SVC-000047", "name": "Weed Management & Safe Herbicide Plan", "description": "Best-fit weed management using mechanical, cultural, and safe herbicide options with application timing.", "category": "pest-management", "price_info": "₹450 / acre", "rating": 4.6},
    {"service_id": "FA-SVC-000048", "name": "Locust & Migratory Pest Monitoring", "description": "Alert-based monitoring and rapid response planning for locust swarms and other migratory pest threats.", "category": "pest-management", "price_info": "₹1,500 / visit", "rating": 4.5},
    {"service_id": "FA-SVC-000049", "name": "Post-Spray Safety Interval Enforcement", "description": "Advisory and field verification to enforce pre-harvest intervals and ensure residue-safe produce.", "category": "pest-management", "price_info": "₹300 / consultation", "rating": 4.8},
    {"service_id": "FA-SVC-000050", "name": "Nematode & Soil-Borne Pest Solutions", "description": "Sampling and management plans for plant-parasitic nematodes and soil-borne insects using bio-pesticides and rotation.", "category": "pest-management", "price_info": "₹750 / sample", "rating": 4.5},
    # @PART1DONE@
    {"service_id": "FA-SVC-000051", "name": "Crop Disease Surveillance & Early Warning", "description": "Field surveillance and early warning alerts for fungal, bacterial, and viral disease outbreaks.", "category": "crop-disease", "price_info": "₹450 / acre", "rating": 4.8},
    {"service_id": "FA-SVC-000052", "name": "Plant Disease Laboratory Diagnosis", "description": "Accurate laboratory identification of plant pathogens with tailored treatment and prevention prescriptions.", "category": "crop-disease", "price_info": "₹850 / sample", "rating": 4.9},
    {"service_id": "FA-SVC-000053", "name": "Integrated Disease Management (IDM) Plan", "description": "Combined cultural, resistant-variety, biological, and chemical measures to control diseases economically.", "category": "crop-disease", "price_info": "₹600 / consultation", "rating": 4.8},
    {"service_id": "FA-SVC-000054", "name": "Controlled Environment Disease Control", "description": "Humidity, ventilation, and fungicide strategy management for greenhouse and polyhouse crop protection.", "category": "crop-disease", "price_info": "₹900 / visit", "rating": 4.6},
    {"service_id": "FA-SVC-000055", "name": "Seed-Borne Disease Elimination Treatment", "description": "Hot-water, chemical, and biological seed treatments to eliminate seed-borne fungal and bacterial infections.", "category": "crop-disease", "price_info": "₹250 / acre", "rating": 4.7},
    {"service_id": "FA-SVC-000056", "name": "Bacterial Wilt & Blight Management", "description": "Specialized management of bacterial wilt, blight, and leaf spot diseases in vegetables and cash crops.", "category": "crop-disease", "price_info": "₹700 / acre", "rating": 4.7},
    {"service_id": "FA-SVC-000057", "name": "Fungicide Resistance Monitoring Advisory", "description": "Advisory to monitor and prevent resistance through rotation of fungicide mode-of-action groups.", "category": "crop-disease", "price_info": "₹400 / consultation", "rating": 4.5},
    {"service_id": "FA-SVC-000058", "name": "Post-Rain Fungal Outbreak Rapid Response", "description": "Rapid response plan and curative spray program within 48 hours after heavy rain-induced disease outbreaks.", "category": "crop-disease", "price_info": "₹600 / visit", "rating": 4.6},
    {"service_id": "FA-SVC-000059", "name": "Virus Vector (Insect) Control Program", "description": "Vector suppression programs including nets, oils, and insecticides to limit virus spread in crops.", "category": "crop-disease", "price_info": "₹650 / acre", "rating": 4.5},
    {"service_id": "FA-SVC-000060", "name": "Plant Disease Record Digitization", "description": "Digital disease history mapping for fields to forecast risks and plan preventive calendars for future seasons.", "category": "crop-disease", "price_info": "₹350 / field", "rating": 4.3},
    {"service_id": "FA-SVC-000061", "name": "Sprinkler Irrigation System Design & Install", "description": "Pressure-budgeted sprinkler design and turnkey installation for water-efficient coverage of field crops.", "category": "irrigation-water", "price_info": "₹45,000 / acre", "rating": 4.6},
    {"service_id": "FA-SVC-000062", "name": "Drip Irrigation System Design & Install", "description": "Custom drip design with emission uniformity checks and full subsurface or surface installation.", "category": "irrigation-water", "price_info": "₹38,000 / acre", "rating": 4.8},
    {"service_id": "FA-SVC-000063", "name": "Farm Pond Construction & Lining", "description": "Excavation, compaction, and geo-membrane lining services for rainwater harvesting farm ponds.", "category": "irrigation-water", "price_info": "₹95,000 / pond", "rating": 4.7},
    {"service_id": "FA-SVC-000064", "name": "Solar-Powered Irrigation Pump Support", "description": "Feasibility, subsidy paperwork, and installation support for solar water pumps and pump sets.", "category": "irrigation-water", "price_info": "₹90,000 / unit", "rating": 4.7},
    {"service_id": "FA-SVC-000065", "name": "Irrigation Scheduling Advisory Service", "description": "Data-driven irrigation schedules using weather, soil moisture, and crop stage to save up to 30% water.", "category": "irrigation-water", "price_info": "₹400 / acre", "rating": 4.8},
    {"service_id": "FA-SVC-000066", "name": "Trench Method & Furrow Irrigation Modernization", "description": "Modernization of furrow and trench irrigation for gravity-fed gardens with proper ridge and row spacing.", "category": "irrigation-water", "price_info": "₹800 / acre", "rating": 4.5},
    {"service_id": "FA-SVC-000067", "name": "Micro-Sprinkler Assembly for Orchards", "description": "Micro-sprinkler layout, assembly, and commissioning for orchard and vegetable canopy irrigation.", "category": "irrigation-water", "price_info": "₹650 / acre", "rating": 4.5},
    {"service_id": "FA-SVC-000068", "name": "Water Pump Efficiency Audit & Sizing", "description": "Pump efficiency audit, horsepower correction, and energy-efficiency recommendations for irrigation pumps.", "category": "irrigation-water", "price_info": "₹500 / audit", "rating": 4.6},
    {"service_id": "FA-SVC-000069", "name": "Open Well & Borewell Water Health Check", "description": "Water level trend, salinity, and sediment testing of open wells and borewells for safe irrigation use.", "category": "irrigation-water", "price_info": "₹400 / check", "rating": 4.5},
    {"service_id": "FA-SVC-000070", "name": "Wastewater Reuse & Treated Water Advisory", "description": "Assessment and advisory for safe reuse of treated wastewater in agriculture with crop suitability mapping.", "category": "irrigation-water", "price_info": "₹600 / consultation", "rating": 4.3},
    {"service_id": "FA-SVC-000071", "name": "Tractor Hiring & Custom Operations", "description": "Tractor with operator for ploughing, cultivation, haulage, and allied operations on a per-hour or acre basis.", "category": "farm-machinery", "price_info": "₹1,100 / hour", "rating": 4.7},
    {"service_id": "FA-SVC-000072", "name": "Rotavator / Cultivator Hiring Service", "description": "High-speed rotavator and cultivator operations for perfect seedbed preparation in record time.", "category": "farm-machinery", "price_info": "₹950 / acre", "rating": 4.6},
    {"service_id": "FA-SVC-000073", "name": "Harvester & Thresher Rental", "description": "Ready-to-operate combine harvesters, reapers, and threshers with operator for timely harvest operations.", "category": "farm-machinery", "price_info": "₹1,800 / acre", "rating": 4.7},
    {"service_id": "FA-SVC-000074", "name": "Power Tiller & Mini-Tractor Service", "description": "Compact power tiller and mini-tractor operations suited for orchards, small plots, and inter-row work.", "category": "farm-machinery", "price_info": "₹700 / hour", "rating": 4.5},
    {"service_id": "FA-SVC-000075", "name": "Drone Spraying & Crop Monitoring Service", "description": "License-compliant agricultural drone service for uniform pesticide spraying and aerial crop health mapping.", "category": "farm-machinery", "price_info": "₹36,000 / acre", "rating": 4.6},
    {"service_id": "FA-SVC-000076", "name": "Sprayer & Dusting Machinery Service", "description": "Commissioning, calibration, and hiring of tractor-mounted, power, and knapsack sprayers.", "category": "farm-machinery", "price_info": "₹500 / day", "rating": 4.5},
    {"service_id": "FA-SVC-000077", "name": "Tractor & Implement Repair Workshop", "description": "Authorized repair and overhaul of tractors, engines, and implements with genuine spares and warranty.", "category": "farm-machinery", "price_info": "₹400 / labour hour", "rating": 4.6},
    {"service_id": "FA-SVC-000078", "name": "Harvest Attachments & Tools Fixing", "description": "Fitting and calibration of harvest attachments, trailers, and unloading systems on existing tractors.", "category": "farm-machinery", "price_info": "₹500 / attachment", "rating": 4.4},
    {"service_id": "FA-SVC-000079", "name": "Irrigation Engine & Pump Service", "description": "On-farm servicing of irrigation engines, pump sets, valves, and filters including alignment and priming.", "category": "farm-machinery", "price_info": "₹600 / visit", "rating": 4.6},
    {"service_id": "FA-SVC-000080", "name": "Machinery Operator Training & License", "description": "Hands-on operator training and documentation support for tractors, harvesters, and drones.", "category": "farm-machinery", "price_info": "₹2,000 / course", "rating": 4.5},
    {"service_id": "FA-SVC-000081", "name": "Farm Labour Force Booking", "description": "Verified daily-wage farm labour for sowing, weeding, harvesting, and general farm work.", "category": "farm-labour", "price_info": "₹500 / day", "rating": 4.4},
    {"service_id": "FA-SVC-000082", "name": "Harvest Crew & Pickers Team", "description": "Trained harvesting and picking crew for vegetables, fruits, cotton, and grains with careful handling.", "category": "farm-labour", "price_info": "₹650 / day", "rating": 4.5},
    {"service_id": "FA-SVC-000083", "name": "Grafting, Budding & Pruning Specialists", "description": "Skilled horticulture hands for grafting, budding, crown pruning, and training of fruit trees.", "category": "farm-labour", "price_info": "₹800 / day", "rating": 4.7},
    {"service_id": "FA-SVC-000084", "name": "Greenhouse & Polyhouse Work Crew", "description": "Experienced crew for greenhouse cleaning, tray filling, planting, and netting work.", "category": "farm-labour", "price_info": "₹700 / day", "rating": 4.5},
    {"service_id": "FA-SVC-000085", "name": "Landscaping & Farm Beautification Crew", "description": "Crew for farm landscaping, pathway creation, fencing greenery, and general beautification works.", "category": "farm-labour", "price_info": "₹750 / day", "rating": 4.4},
    {"service_id": "FA-SVC-000086", "name": "Seasonal Supervisory Staff", "description": "Trained farm supervisors for seasonal management, work scheduling, and record keeping.", "category": "farm-labour", "price_info": "₹12,000 / month", "rating": 4.5},
    {"service_id": "FA-SVC-000087", "name": "Fencing & Trellis Installation Labour", "description": "Dedicated labour for farm fencing, trellis erection, netting, and support-stake installation.", "category": "farm-labour", "price_info": "₹700 / day", "rating": 4.4},
    {"service_id": "FA-SVC-000088", "name": "Packhouse & Grading Line Labour", "description": "Labour for sorting, grading, cleaning, and packing produce at packhouse stations.", "category": "farm-labour", "price_info": "₹550 / day", "rating": 4.3},
    {"service_id": "FA-SVC-000089", "name": "Emergency Surge-Labor Dispatch", "description": "Rapid dispatch of extra labour teams during peak planting or harvest windows on short notice.", "category": "farm-labour", "price_info": "₹700 / day", "rating": 4.4},
    {"service_id": "FA-SVC-000090", "name": "Cow & Livestock Caretaker Service", "description": "Reliable caretaker and labourer for daily livestock feeding, cleaning, and basic health observation.", "category": "farm-labour", "price_info": "₹9,000 / month", "rating": 4.2},
    {"service_id": "FA-SVC-000091", "name": "Manual Harvesting Support", "description": "Human-directed manual harvesting of grains and pulses with sheaving and bundle tying.", "category": "harvesting", "price_info": "₹1,300 / acre", "rating": 4.4},
    {"service_id": "FA-SVC-000092", "name": "Paddy & Wheat Combine Harvesting", "description": "Combine harvesting with straw management and grain bagging for paddy and wheat.", "category": "harvesting", "price_info": "₹2,000 / acre", "rating": 4.7},
    {"service_id": "FA-SVC-000093", "name": "Fruit & Vegetable Picking Service", "description": "Careful selective picking, sorting, and crating of fruits and vegetables to protect market quality.", "category": "harvesting", "price_info": "₹80 / hour", "rating": 4.6},
    {"service_id": "FA-SVC-000094", "name": "Sugarcane & Fibre Crop Harvesting", "description": "Skilled crews for sugarcane cutting, bundling, and fibre crop harvesting with proper tool upkeep.", "category": "harvesting", "price_info": "₹4,500 / acre", "rating": 4.3},
    {"service_id": "FA-SVC-000095", "name": "Harvest Time Planning & Readiness Audit", "description": "Pre-harvest audit of moisture, maturity, labour, and logistics readiness to avoid losses.", "category": "harvesting", "price_info": "₹400 / consultation", "rating": 4.6},
    {"service_id": "FA-SVC-000096", "name": "Mechanical Reaper & Binder Rental", "description": "Rental of reaper binders with operator for efficient harvesting of grain crops.", "category": "harvesting", "price_info": "₹1,500 / acre", "rating": 4.5},
    {"service_id": "FA-SVC-000097", "name": "Onion, Garlic & Root Crop Digging", "description": "Careful digging, curing, and topping service for onion, garlic, and root vegetables.", "category": "harvesting", "price_info": "₹1,200 / acre", "rating": 4.4},
    {"service_id": "FA-SVC-000098", "name": "Harvest Quality Sampling & Testing", "description": "Moisture, foreign matter, and grading tests at harvest time to route produce to the best market.", "category": "harvesting", "price_info": "₹250 / sample", "rating": 4.5},
    {"service_id": "FA-SVC-000099", "name": "Multi-Phase Harvest Crew Management", "description": "End-to-end coordination of cut-to-transport crews with quality checks at each harvest stage.", "category": "harvesting", "price_info": "₹1,000 / day", "rating": 4.4},
    {"service_id": "FA-SVC-000100", "name": "Harvest Machinery Retrofit & Hiring", "description": "Retrofit attachments on existing machinery and rent additional harvest equipment for peak loads.", "category": "harvesting", "price_info": "₹600 / day", "rating": 4.3},
    # @PART2DONE@
    {"service_id": "FA-SVC-000101", "name": "Produce Cleaning, Grading & Sorting", "description": "Cleaning, moisture management, and size/quality grading of grains and produce for premium market returns.", "category": "post-harvest", "price_info": "₹400 / quintal", "rating": 4.6},
    {"service_id": "FA-SVC-000102", "name": "Post-Harvest Drying Service", "description": "Open-yard and mechanical drying service to bring moisture to safe storage levels and prevent spoilage.", "category": "post-harvest", "price_info": "₹250 / quintal", "rating": 4.5},
    {"service_id": "FA-SVC-000103", "name": "Produce Value Addition & Processing", "description": "Primary processing support for milling, polishing, juicing, and value-added product conversion.", "category": "post-harvest", "price_info": "₹1,500 / batch", "rating": 4.4},
    {"service_id": "FA-SVC-000104", "name": "Packing & Labeling Services", "description": "Jute, poly, and consumer pack filling with labelling to FSSAI and market quality standards.", "category": "post-harvest", "price_info": "₹350 / quintal", "rating": 4.5},
    {"service_id": "FA-SVC-000105", "name": "Grain Moisture Surveillance Program", "description": "Durable monitoring of grain moisture across seasons with alerts and aeration advice.", "category": "post-harvest", "price_info": "₹200 / bin", "rating": 4.4},
    {"service_id": "FA-SVC-000106", "name": "Food Safety & Residue Audit", "description": "Residue and food-safety audit for export- and retail-bound produce with corrective advisory.", "category": "post-harvest", "price_info": "₹1,200 / audit", "rating": 4.5},
    {"service_id": "FA-SVC-000107", "name": "Cold Chain Gap Assessment", "description": "Assessment of cold storage and transport gaps for perishables with economically justified upgrades.", "category": "post-harvest", "price_info": "₹1,500 / audit", "rating": 4.4},
    {"service_id": "FA-SVC-000108", "name": "Threshing, Winnowing & Shelling", "description": "Mechanical threshing, winnowing, and shelling services for grains, pulses, and oilseeds.", "category": "post-harvest", "price_info": "₹450 / quintal", "rating": 4.5},
    {"service_id": "FA-SVC-000109", "name": "Post-Harvest Loss Reduction Workshop", "description": "Hands-on training on handling, storage, and transport practices that cut field-to-market losses.", "category": "post-harvest", "price_info": "₹800 / participant", "rating": 4.5},
    {"service_id": "FA-SVC-000110", "name": "Ripening & Hardening Chamber Setup", "description": "Design and operation guidance for ethylene ripening and hardening chambers for fruits.", "category": "post-harvest", "price_info": "₹2,000 / setup", "rating": 4.3},
    {"service_id": "FA-SVC-000111", "name": "Warehouse Space Leasing & Booking", "description": "Verified warehouse space for seasonal produce with flexible monthly or seasonal leasing.", "category": "storage-warehousing", "price_info": "₹120 / quintal / month", "rating": 4.5},
    {"service_id": "FA-SVC-000112", "name": "Cold Storage Space Booking", "description": "Temperature-controlled cold storage slots for perishables with digital inventory tracking.", "category": "storage-warehousing", "price_info": "₹180 / crate / month", "rating": 4.6},
    {"service_id": "FA-SVC-000113", "name": "Warehouse Fumigation & Sanitation", "description": "Legal phosphine and contact fumigation plus sanitation protocol for storage pest control.", "category": "storage-warehousing", "price_info": "₹150 / tonne", "rating": 4.6},
    {"service_id": "FA-SVC-000114", "name": "Silo & Bag Storage Loading", "description": "Grain receipt, weighing, stacking, and loading work inside silos and godowns.", "category": "storage-warehousing", "price_info": "₹40 / bag", "rating": 4.3},
    {"service_id": "FA-SVC-000115", "name": "Storage Health & Quality Audit", "description": "Periodic audit of temperature, moisture, pests, and hygiene inside stores with risk scoring.", "category": "storage-warehousing", "price_info": "₹600 / audit", "rating": 4.4},
    {"service_id": "FA-SVC-000116", "name": "Grain Bag & Packaging Material Supply", "description": "Supply of quality jute, PP, and silo bags with markings for bulk grain storage.", "category": "storage-warehousing", "price_info": "₹45 / bag", "rating": 4.3},
    {"service_id": "FA-SVC-000117", "name": "Warehouse Inventory Digitalization", "description": "Digital lot tracking, stock registers, and issue-by-lot record systems for stores and godowns.", "category": "storage-warehousing", "price_info": "₹500 / session", "rating": 4.4},
    {"service_id": "FA-SVC-000118", "name": "Mandi Storage Transfer Support", "description": "Coordination and transport of stored produce to mandi and auction yards with weighment records.", "category": "storage-warehousing", "price_info": "₹1,100 / trip", "rating": 4.4},
    {"service_id": "FA-SVC-000119", "name": "Reusable Packaging & Pallet Program", "description": "Design and supply of reusable crates, pallets, and returnable packaging for cold chains.", "category": "storage-warehousing", "price_info": "₹650 / crate", "rating": 4.2},
    {"service_id": "FA-SVC-000120", "name": "Warehouse Insurance & Compliance Advisory", "description": "Advisory for storage insurance coverage and compliance ratings under collateral management norms.", "category": "storage-warehousing", "price_info": "₹700 / consultation", "rating": 4.4},
    {"service_id": "FA-SVC-000121", "name": "Farm-to-Mandi Produce Transport", "description": "Reliable local transport of produce from farm gate to mandi with loading and unloading support.", "category": "transport-logistics", "price_info": "₹12 / km", "rating": 4.5},
    {"service_id": "FA-SVC-000122", "name": "Interstate Agricultural Freight", "description": "Long-haul freight service for bulk agricultural commodities across state borders.", "category": "transport-logistics", "price_info": "₹8 / km", "rating": 4.4},
    {"service_id": "FA-SVC-000123", "name": "Cold Chain Reefer Truck Hire", "description": "Temperature-controlled reefer hire for perishable transport with live temperature monitoring.", "category": "transport-logistics", "price_info": "₹45 / km", "rating": 4.6},
    {"service_id": "FA-SVC-000124", "name": "Livestock & Poultry Transport", "description": "Animal-safe transport trolleys with water, ventilation, and permits for livestock movement.", "category": "transport-logistics", "price_info": "₹18 / km", "rating": 4.3},
    {"service_id": "FA-SVC-000125", "name": "Agricultural Input Logistics", "description": "Door delivery of fertilizers, seeds, and agro-chemicals with handling and documentation.", "category": "transport-logistics", "price_info": "₹6 / km", "rating": 4.4},
    {"service_id": "FA-SVC-000126", "name": "Laden Weighbridge & Documentation Aid", "description": "Weighbridge coordination and challan documentation for transparent load transactions.", "category": "transport-logistics", "price_info": "₹150 / trip", "rating": 4.3},
    {"service_id": "FA-SVC-000127", "name": "Route Planning & Demurrage Advisory", "description": "Optimized route planning and demurrage (loading-unloading) discipline to cut freight costs.", "category": "transport-logistics", "price_info": "₹350 / consultation", "rating": 4.4},
    {"service_id": "FA-SVC-000128", "name": "Packaging for Transport (Stacking & Lashing)", "description": "Secure stacking, lashing, and weather-proofing of produce loads for safe road and rail transit.", "category": "transport-logistics", "price_info": "₹250 / vehicle", "rating": 4.2},
    {"service_id": "FA-SVC-000129", "name": "Perishable Express Courier Service", "description": "Verified express courier of perishables and samples to metros with cold packaging.", "category": "transport-logistics", "price_info": "₹350 / consignment", "rating": 4.5},
    {"service_id": "FA-SVC-000130", "name": "Multi-Modal Grain Corridor Booking", "description": "Coordinated road-rail barge corridor movement for bulk grain with warehousing links.", "category": "transport-logistics", "price_info": "₹1,200 / tonne", "rating": 4.3},
    {"service_id": "FA-SVC-000131", "name": "Dairy Animal Health & Feeding Audit", "description": "Routine health, feeding, and comfort audit for dairy animals with productivity benchmarks.", "category": "livestock", "price_info": "₹500 / visit", "rating": 4.5},
    {"service_id": "FA-SVC-000132", "name": "Ejzen-Nutrition & BMR Ration Balancing", "description": "Ration balancing for dairy and growing animals using by-product-rich feeding programs.", "category": "livestock", "price_info": "₹400 / animal", "rating": 4.6},
    {"service_id": "FA-SVC-000133", "name": "Winter & Summer Shelter Management", "description": "Shelter ventilation, bedding, and heat-stress management for all seasons.", "category": "livestock", "price_info": "₹350 / session", "rating": 4.4},
    {"service_id": "FA-SVC-000134", "name": "Artificial Insemination Coordination", "description": "Timely AI scheduling, technician coordination, and heat-detection support for dairy herds.", "category": "livestock", "price_info": "₹250 / insemination", "rating": 4.5},
    {"service_id": "FA-SVC-000135", "name": "Hoof Trimming & Foot Care", "description": "Routine hoof trimming and foot-bath protocols to prevent lameness in dairy and draft animals.", "category": "livestock", "price_info": "₹300 / animal", "rating": 4.3},
    {"service_id": "FA-SVC-000136", "name": "Pregnancy Diagnosis & Herd Recording", "description": "Pregnancy diagnosis scheduling and structured herd records for reproduction management.", "category": "livestock", "price_info": "₹350 / check", "rating": 4.5},
    {"service_id": "FA-SVC-000137", "name": "Livestock Waste & Slurry Management", "description": "Slurry handling, composting, and safe disposal plans turning farm waste into inputs.", "category": "livestock", "price_info": "₹600 / unit", "rating": 4.4},
    {"service_id": "FA-SVC-000138", "name": "Small Ruminant (Goat/Sheep) Program", "description": "Health, deworming, breeding, and balanced feeding schedules for goat and sheep flocks.", "category": "livestock", "price_info": "₹300 / session", "rating": 4.4},
    {"service_id": "FA-SVC-000139", "name": "Livestock Insurance Facilitation", "description": "Enrollment support for livestock insurance schemes with claim documentation help.", "category": "livestock", "price_info": "₹200 / head", "rating": 4.3},
    {"service_id": "FA-SVC-000140", "name": "Zootechnical Slide & Selective Breeding", "description": "Stud selection, breeding targets, and record-led genetic improvement planning.", "category": "livestock", "price_info": "₹500 / consultation", "rating": 4.2},
    {"service_id": "FA-SVC-000141", "name": "Emergency Veterinary Visit & Treatment", "description": "Priority 24-hour emergency vet visits for livestock with on-site treatment and care plans.", "category": "veterinary", "price_info": "₹900 / visit", "rating": 4.8},
    {"service_id": "FA-SVC-000142", "name": "Vaccination & Deworming Camp", "description": "Scheduled vaccination and deworming camps under veterinary guidance for livestock and pets.", "category": "veterinary", "price_info": "₹150 / animal", "rating": 4.7},
    {"service_id": "FA-SVC-000143", "name": "Artificial Insemination Expert Service", "description": "Certified AI specialist service with quality semen and conception follow-up verification.", "category": "veterinary", "price_info": "₹350 / insemination", "rating": 4.6},
    {"service_id": "FA-SVC-000144", "name": "Mobile Veterinary Clinic Day", "description": "Village-coordinated mobile clinic day covering multiple flocks and herds in a single visit.", "category": "veterinary", "price_info": "₹750 / day", "rating": 4.7},
    {"service_id": "FA-SVC-000145", "name": "Laboratory Diagnostics for Animals", "description": "Blood, fecal, milk, and skin sample testing for disease confirmation and herd surveillance.", "category": "veterinary", "price_info": "₹500 / test", "rating": 4.7},
    {"service_id": "FA-SVC-000146", "name": "Zoonotic Disease Prevention Audit", "description": "Hygiene and bio-security audit to reduce zoonotic disease risk to farm families.", "category": "veterinary", "price_info": "₹450 / audit", "rating": 4.6},
    {"service_id": "FA-SVC-000147", "name": "Animal Birth Control & Welfare Support", "description": "Humane birth-control and welfare support for community and stray animals.", "category": "veterinary", "price_info": "₹350 / animal", "rating": 4.4},
    {"service_id": "FA-SVC-000148", "name": "Post-Surgery & Wound Care Follow-up", "description": "Structured post-surgical and wound care follow-up with medication schedules.", "category": "veterinary", "price_info": "₹250 / visit", "rating": 4.5},
    {"service_id": "FA-SVC-000149", "name": "Veterinary Medicine & Consumables Supply", "description": "Genuine veterinary medicines, supplements, and consumables with dosage guidance.", "category": "veterinary", "price_info": "Varies by prescription", "rating": 4.5},
    {"service_id": "FA-SVC-000150", "name": "Seasonal Disease Preparedness Plan", "description": "Season-aware vaccination, nutrition, and bio-security calendar for disease prevention.", "category": "veterinary", "price_info": "₹400 / consultation", "rating": 4.6},
    # @PART3DONE@
    {"service_id": "FA-SVC-000151", "name": "Clean Milk Production Advisory", "description": "Milk room hygiene, machine milking, and chilling protocols for premium clean-milk quality.", "category": "dairy-poultry", "price_info": "₹350 / session", "rating": 4.5},
    {"service_id": "FA-SVC-000152", "name": "Milk Quality & SNF/Fat Testing", "description": "On-spot milk fat, SNF, adulteration, and pH testing with corrective feeding advice.", "category": "dairy-poultry", "price_info": "₹150 / sample", "rating": 4.6},
    {"service_id": "FA-SVC-000153", "name": "Poultry Layer & Broiler Health Plan", "description": "Health, vaccination, lighting, and biosecurity planning for layers and broilers.", "category": "dairy-poultry", "price_info": "₹550 / session", "rating": 4.5},
    {"service_id": "FA-SVC-000154", "name": "Dairy Feed & Concentrate Formulation", "description": "Least-cost feed and concentrate formulations using locally available ingredients.", "category": "dairy-poultry", "price_info": "₹300 / herd", "rating": 4.6},
    {"service_id": "FA-SVC-000155", "name": "Poultry Shed Bio-Security Program", "description": "Entry protocols, disinfection, and litter management to keep poultry flocks disease-free.", "category": "dairy-poultry", "price_info": "₹400 / visit", "rating": 4.5},
    {"service_id": "FA-SVC-000156", "name": "Hatchery & Incubation Management", "description": "Temperature, humidity, turning, and hatch-window management for better hatch rates.", "category": "dairy-poultry", "price_info": "₹600 / session", "rating": 4.4},
    {"service_id": "FA-SVC-000157", "name": "Dairy Farm Productivity Coaching", "description": "Month-wise coaching on milking, feeding, reproduction, and record keeping to raise herd output.", "category": "dairy-poultry", "price_info": "₹1,200 / month", "rating": 4.6},
    {"service_id": "FA-SVC-000158", "name": "Egg Grading & Storage Guidance", "description": "Size grading, washing policy, temperature, and rotation for longer egg shelf life.", "category": "dairy-poultry", "price_info": "₹250 / session", "rating": 4.3},
    {"service_id": "FA-SVC-000159", "name": "Poultry Feed Mixer & Equipment Setup", "description": "Setup and calibration of feed mixers, nipple lines, and ventilation equipment.", "category": "dairy-poultry", "price_info": "₹750 / setup", "rating": 4.3},
    {"service_id": "FA-SVC-000160", "name": "Manure Drying & Composting Unit Setup", "description": "Turning poultry and dairy manure into saleable compost with structured drying beds.", "category": "dairy-poultry", "price_info": "₹1,000 / unit", "rating": 4.4},
    {"service_id": "FA-SVC-000161", "name": "Organic Certification Consultation", "description": "Step-by-step guidance from conversion planning to final NPOP/NOP certification approval.", "category": "organic-farming", "price_info": "₹2,000 / consultation", "rating": 4.7},
    {"service_id": "FA-SVC-000162", "name": "GAP (Good Agriculture Practices) Advisory", "description": "GAP adoption advisory for residue-free produce and better market acceptance.", "category": "organic-farming", "price_info": "₹800 / consultation", "rating": 4.6},
    {"service_id": "FA-SVC-000163", "name": "Jeevamrutham & Beejamrutham Preparation", "description": "On-farm training and quantity planning for jeevamrutham, beejamrutham, and dasagavya preparations.", "category": "organic-farming", "price_info": "₹350 / session", "rating": 4.6},
    {"service_id": "FA-SVC-000164", "name": "Bio-Fertilizer & Vermicompost Unit Setup", "description": "Setting up vermicompost and bio-fertilizer production units with harvesting schedules.", "category": "organic-farming", "price_info": "₹1,500 / unit", "rating": 4.6},
    {"service_id": "FA-SVC-000165", "name": "Natural Farming Pest Management", "description": "Preparation and application of botanical and microbial pest-control recipes under natural farming.", "category": "organic-farming", "price_info": "₹450 / session", "rating": 4.6},
    {"service_id": "FA-SVC-000166", "name": "Organic Farm Inspection Gap Check", "description": "Pre-inspection audit that helps organic farms clear certification inspections on first attempt.", "category": "organic-farming", "price_info": "₹1,200 / audit", "rating": 4.5},
    {"service_id": "FA-SVC-000167", "name": "Multi-Layer Kitchen Garden Model", "description": "Design of year-round kitchen garden modules using organic principles for family nutrition.", "category": "organic-farming", "price_info": "₹500 / session", "rating": 4.4},
    {"service_id": "FA-SVC-000168", "name": "Green Manure & Cover Crop Program", "description": "Selection and incorporation of green manure crops to build nitrogen and organic matter.", "category": "organic-farming", "price_info": "₹300 / acre", "rating": 4.6},
    {"service_id": "FA-SVC-000169", "name": "Organic Input Supply Chain Setup", "description": "Sourcing and pooling of validated organic inputs with farmer-group volume benefits.", "category": "organic-farming", "price_info": "₹600 / session", "rating": 4.3},
    {"service_id": "FA-SVC-000170", "name": "Zero Budget Natural Farming (ZBNF) Adoption", "description": "ZBNF adoption roadmap with subsidy linkage and village-level mentor support.", "category": "organic-farming", "price_info": "₹700 / session", "rating": 4.7},
    {"service_id": "FA-SVC-000171", "name": "Carbon Farming & Soil Sequestration Plan", "description": "Practice bundles that sequester soil carbon and open carbon-credit and CSR revenue options.", "category": "sustainable-agri", "price_info": "₹800 / consultation", "rating": 4.5},
    {"service_id": "FA-SVC-000172", "name": "Water Footprint & Catchment Plan", "description": "Catchment-scale water budgeting that improves tank, borewell, and rain-fed resilience.", "category": "sustainable-agri", "price_info": "₹1,000 / consultation", "rating": 4.6},
    {"service_id": "FA-SVC-000173", "name": "Crop-Diversification Risk Plan", "description": "Diversified crop-mix models that stabilize income and reduce climate and price risk.", "category": "sustainable-agri", "price_info": "₹600 / consultation", "rating": 4.6},
    {"service_id": "FA-SVC-000174", "name": "Predator-Friendly Pest Control Adoption", "description": "Designing habitats and practices that sustain beneficial insects and reduce sprays.", "category": "sustainable-agri", "price_info": "₹500 / visit", "rating": 4.5},
    {"service_id": "FA-SVC-000175", "name": "Climate-Smart Modular Farm Plan", "description": "Crop, water, and energy modules tailored to district-level climate outlooks.", "category": "sustainable-agri", "price_info": "₹1,000 / plan", "rating": 4.6},
    {"service_id": "FA-SVC-000176", "name": "Deforestation-Free Land Use Map", "description": "Land-use mapping that protects natural assets while optimizing productive area.", "category": "sustainable-agri", "price_info": "₹800 / mapping", "rating": 4.4},
    {"service_id": "FA-SVC-000177", "name": "On-Farm Renewable Energy Audit", "description": "Solar, bio-gas, and biomass energy audits with payback and subsidy computations.", "category": "sustainable-agri", "price_info": "₹900 / audit", "rating": 4.5},
    {"service_id": "FA-SVC-000178", "name": "Regenerative Agroforestry Design", "description": "Tree-crop-livestock system designs that restore soil and produce multiple benefits.", "category": "sustainable-agri", "price_info": "₹1,200 / acre", "rating": 4.6},
    {"service_id": "FA-SVC-000179", "name": "Wetland & Rainwater Harvest Advisor", "description": "Rebuilding farm bunds, trenches, and ponds to recharge groundwater and cut flood damage.", "category": "sustainable-agri", "price_info": "₹700 / visit", "rating": 4.5},
    {"service_id": "FA-SVC-000180", "name": "Sustainability Report & Impact Mapping", "description": "Greenhouse-gas, water, and biodiversity impact reporting for eco-labeled market access.", "category": "sustainable-agri", "price_info": "₹1,500 / report", "rating": 4.4},
    {"service_id": "FA-SVC-000181", "name": "PM-KISAN & State Scheme Application", "description": "Documentation and tracking support for PM-KISAN and state direct-benefit farm schemes.", "category": "government-schemes", "price_info": "Free (Govt Value)", "rating": 4.7},
    {"service_id": "FA-SVC-000182", "name": "Drip & Sprinkler Subsidy Application", "description": "End-to-end preparation, submission, and tracking of micro-irrigation subsidy claims.", "category": "government-schemes", "price_info": "₹300 / application", "rating": 4.7},
    {"service_id": "FA-SVC-000183", "name": "Kisan Credit Card (KCC) Assistance", "description": "KCC application completion, document collation, and renewal tracking with bankers.", "category": "government-schemes", "price_info": "₹250 / application", "rating": 4.6},
    {"service_id": "FA-SVC-000184", "name": "Fasal Bima Yojana (Crop Insurance) Apply", "description": "Enrollment, premium documentation, and claim filing support under PMFBY.", "category": "government-schemes", "price_info": "₹200 / farmer", "rating": 4.7},
    {"service_id": "FA-SVC-000185", "name": "Solar Pump Set Subsidy Facilitation", "description": "Eligibility, application, and installation-issue resolution for solar pump subsidies.", "category": "government-schemes", "price_info": "₹350 / application", "rating": 4.6},
    {"service_id": "FA-SVC-000186", "name": "Certification-Linked Incentive Schemes", "description": "Guidance for organic, quality certification, and export-linked state incentive programs.", "category": "government-schemes", "price_info": "₹400 / consultation", "rating": 4.5},
    {"service_id": "FA-SVC-000187", "name": "Farm Machinery Bank Subsidy Support", "description": "Custom hiring center and machinery-bank subsidy documentation and procurement help.", "category": "government-schemes", "price_info": "₹500 / application", "rating": 4.5},
    {"service_id": "FA-SVC-000188", "name": "Cold Storage & Warehouse Scheme Application", "description": "Preparation of cold storage, warehousing, and drying unit scheme applications.", "category": "government-schemes", "price_info": "₹700 / application", "rating": 4.4},
    {"service_id": "FA-SVC-000189", "name": "PM-KUSUM Solarization Applications", "description": "Pump solarization application and stakeholder coordination under PM-KUSUM.", "category": "government-schemes", "price_info": "₹400 / application", "rating": 4.5},
    {"service_id": "FA-SVC-000190", "name": "Agri-Startup & Skill Scheme Guidance", "description": "START-UP, skill development, and youth scheme linkages with business-plan support.", "category": "government-schemes", "price_info": "₹500 / consultation", "rating": 4.4},
    {"service_id": "FA-SVC-000191", "name": "Crop Loan Application Processing", "description": "Timely crop-loan application support, documentation, and disbursement follow-up.", "category": "agri-finance", "price_info": "₹200 / application", "rating": 4.6},
    {"service_id": "FA-SVC-000192", "name": "Farm Credit Health & Restructuring Plan", "description": "Debt review and restructuring strategy aligned with farm cash flows and schemes.", "category": "agri-finance", "price_info": "₹600 / session", "rating": 4.6},
    {"service_id": "FA-SVC-000193", "name": "Subsidy-Linked Investment Advisory", "description": "Prioritized investment plan for drip, drone, cold chain, and machinery with subsidy sync.", "category": "agri-finance", "price_info": "₹500 / consultation", "rating": 4.5},
    {"service_id": "FA-SVC-000194", "name": "Farmer Producer Company (FPO) Setup", "description": "FPO registration, bye-laws, and governance support for farmer collectives.", "category": "agri-finance", "price_info": "₹3,000 / setup", "rating": 4.6},
    {"service_id": "FA-SVC-000195", "name": "Insurance Premium Eligible Document Aid", "description": "Documentation and dispute-resolution help for crop and livestock insurance premiums.", "category": "agri-finance", "price_info": "₹150 / case", "rating": 4.4},
    {"service_id": "FA-SVC-000196", "name": "Agriculture Startup Funding Path", "description": "Mapping of grants, incubator, and venture paths for agri-startups with pitch support.", "category": "agri-finance", "price_info": "₹1,200 / session", "rating": 4.5},
    {"service_id": "FA-SVC-000197", "name": "Warehouse Receipt Financing Advisory", "description": "Using e-NWR warehouse receipts to unlock post-harvest credit at warehouse rates.", "category": "agri-finance", "price_info": "₹300 / consultation", "rating": 4.4},
    {"service_id": "FA-SVC-000198", "name": "Small Farmer Joint Liability Support", "description": "JL group formation and loan documentation for small and marginal farmers.", "category": "agri-finance", "price_info": "₹250 / group", "rating": 4.4},
    {"service_id": "FA-SVC-000199", "name": "Farmer Credit Score & Records Cleaning", "description": "Credit-report review and clean-up guidance that improves loan approvals.", "category": "agri-finance", "price_info": "₹400 / consultation", "rating": 4.3},
    {"service_id": "FA-SVC-000200", "name": "Cash-Flow & Tax Planning for Farm Businesses", "description": "Farm cash-flow, GST basics, and income planning for registered farm businesses.", "category": "agri-finance", "price_info": "₹700 / session", "rating": 4.5},
    # @PART4DONE@
    {"service_id": "FA-SVC-000201", "name": "PMFBY Premium Filing & Enrollment", "description": "Complete premium filing and enrollment support under PMFBY with accurate land records.", "category": "crop-insurance", "price_info": "₹200 / farmer", "rating": 4.7},
    {"service_id": "FA-SVC-000202", "name": "Crop Loss Intimation & Claim Tracking", "description": "Helping farmers intimate losses on time and follow claim processing to settlement.", "category": "crop-insurance", "price_info": "₹300 / case", "rating": 4.6},
    {"service_id": "FA-SVC-000203", "name": "Localized Calamity Coverage Application", "description": "Applications for localized calamity and crop cut assessment windows.", "category": "crop-insurance", "price_info": "₹200 / case", "rating": 4.5},
    {"service_id": "FA-SVC-000204", "name": "Yield Estimation & CCE Coordination", "description": "Coordination with crop-cutting experiment (CCE) teams for fair yield evaluation.", "category": "crop-insurance", "price_info": "₹250 / plot", "rating": 4.5},
    {"service_id": "FA-SVC-000205", "name": "Remote-Sensing Claim Evidence Support", "description": "Using satellite and drone evidence to strengthen delayed-sowing and damage claims.", "category": "crop-insurance", "price_info": "₹350 / case", "rating": 4.4},
    {"service_id": "FA-SVC-000206", "name": "Insurance Awareness & Policy Selection", "description": "Help choosing the right policy from PMFBY, state, and commercial products.", "category": "crop-insurance", "price_info": "Free consultation", "rating": 4.6},
    {"service_id": "FA-SVC-000207", "name": "Premium Refund & Discrepancy Resolution", "description": "Resolving premium deductions, refunds, and data-entry discrepancies with insurers.", "category": "crop-insurance", "price_info": "₹150 / case", "rating": 4.4},
    {"service_id": "FA-SVC-000208", "name": "Multi-Season Insurance Portfolio Plan", "description": "Kharif-Rabi-yearly insurance stacking for family food and cash-crop security.", "category": "crop-insurance", "price_info": "₹400 / plan", "rating": 4.5},
    {"service_id": "FA-SVC-000209", "name": "Post-Insurance Farm Data Records", "description": "Maintaining sowing, input, and yield records that speed up future claim assessments.", "category": "crop-insurance", "price_info": "₹250 / season", "rating": 4.3},
    {"service_id": "FA-SVC-000210", "name": "Livestock & Poultry Insurance Enrollment", "description": "Enrollment of animals and birds under livestock insurance with tagging coordination.", "category": "crop-insurance", "price_info": "₹150 / head", "rating": 4.4},
    {"service_id": "FA-SVC-000211", "name": "One-on-One Crop Advisory Session", "description": "Personal crop advisory consultation with an agronomist for stage-wise decisions.", "category": "expert-consultancy", "price_info": "₹399 / session", "rating": 4.9},
    {"service_id": "FA-SVC-000212", "name": "Video Farm Consultancy with Expert", "description": "Live video consultation with experts including field photos and digital diagnosis.", "category": "expert-consultancy", "price_info": "₹499 / session", "rating": 4.8},
    {"service_id": "FA-SVC-000213", "name": "Yield-Complaint Resolution Consult", "description": "Root-cause analysis of yield stagnation with an implementation-ready recovery plan.", "category": "expert-consultancy", "price_info": "₹700 / case", "rating": 4.7},
    {"service_id": "FA-SVC-000214", "name": "Expert Farm Visit & Walkthrough", "description": "On-field walkthrough by senior experts with hands-on recommendations and checklists.", "category": "expert-consultancy", "price_info": "₹1,500 / visit", "rating": 4.8},
    {"service_id": "FA-SVC-000215", "name": "Fruit Orchard Expert Support", "description": "Orchard-specific expert guidance from establishment to mature fruiting care.", "category": "expert-consultancy", "price_info": "₹1,000 / session", "rating": 4.7},
    {"service_id": "FA-SVC-000216", "name": "Market Price & Commodity Consultation", "description": "Commodity price outlook and best-sell-window advice from market analysts.", "category": "expert-consultancy", "price_info": "₹350 / consultation", "rating": 4.6},
    {"service_id": "FA-SVC-000217", "name": "Contract Farming Agreement Review", "description": "Independent review of contract-farming terms to protect farmer interests.", "category": "expert-consultancy", "price_info": "₹800 / review", "rating": 4.6},
    {"service_id": "FA-SVC-000218", "name": "Organic & Exports Expert Cluster", "description": "Consultations with specialized experts for organic, export, and niche crop programs.", "category": "expert-consultancy", "price_info": "₹900 / session", "rating": 4.6},
    {"service_id": "FA-SVC-000219", "name": "Soil Expert Follow-Up Program", "description": "Season-long follow-up with a single soil expert for data-led decisions.", "category": "expert-consultancy", "price_info": "₹600 / month", "rating": 4.5},
    {"service_id": "FA-SVC-000220", "name": "Digital Climate & SK Field Intelligence", "description": "Weekly climate and pest intelligence briefings for proactive farm management.", "category": "expert-consultancy", "price_info": "₹300 / month", "rating": 4.5},
    {"service_id": "FA-SVC-000221", "name": "Mandi Price Alerts & Forecast Service", "description": "Daily mandi prices and forecast alerts for optimal selling timing.", "category": "market-selling", "price_info": "Free service", "rating": 4.6},
    {"service_id": "FA-SVC-000222", "name": "Direct Farm-Gate Consumer Connect", "description": "Bridging farmers with consumer communities for premium farm-gate pricing.", "category": "market-selling", "price_info": "₹300 / listing", "rating": 4.5},
    {"service_id": "FA-SVC-000223", "name": "Structured Sell File & Invoice Aid", "description": "Building structured selling documents, invoices, and lot-wise records.", "category": "market-selling", "price_info": "₹250 / lot", "rating": 4.4},
    {"service_id": "FA-SVC-000224", "name": "B2B Buyer Connect for Bulk Lots", "description": "Connecting farmers to verified bulk buyers at fair, transparent terms.", "category": "market-selling", "price_info": "₹1% brokerage", "rating": 4.5},
    {"service_id": "FA-SVC-000225", "name": "Export Readiness & Documentation", "description": "Pre-shipment, phytosanitary, and packaging readiness for export-grade produce.", "category": "market-selling", "price_info": "₹1,500 / consignment", "rating": 4.5},
    {"service_id": "FA-SVC-000226", "name": "Branding, Pricing & Premium Positioning", "description": "Farm-gate branding and premium pricing strategy for differentiated produce.", "category": "market-selling", "price_info": "₹400 / session", "rating": 4.4},
    {"service_id": "FA-SVC-000227", "name": "Auction & Commodity Exchange Selling Aid", "description": "Registration, lot-filing, and bidding assistance on commodity exchanges.", "category": "market-selling", "price_info": "₹500 / session", "rating": 4.4},
    {"service_id": "FA-SVC-000228", "name": "Seasonal Market Calendar & Crop Timing", "description": "Matching harvest timing to seasonal demand windows for better prices.", "category": "market-selling", "price_info": "₹300 / consultation", "rating": 4.5},
    {"service_id": "FA-SVC-000229", "name": "Quality Control at Point of Sale", "description": "Independent sorting and quality verification at the point of sale.", "category": "market-selling", "price_info": "₹200 / lot", "rating": 4.3},
    {"service_id": "FA-SVC-000230", "name": "Retail & Food-Service Supply Setup", "description": "Stable retail and food-service supply relationships with reliable quantity and quality.", "category": "market-selling", "price_info": "₹600 / setup", "rating": 4.4},
    {"service_id": "FA-SVC-000231", "name": "Weather Station & IoT Sensor Installation", "description": "Turnkey farm weather stations and IoT sensors with cloud dashboards and alerts.", "category": "agri-technology", "price_info": "₹12,000 / unit", "rating": 4.6},
    {"service_id": "FA-SVC-000232", "name": "Precision Irrigation Automation Setup", "description": "Auto-valve and sensor-driven irrigation automation that waters on demand.", "category": "agri-technology", "price_info": "₹8,500 / acre", "rating": 4.6},
    {"service_id": "FA-SVC-000233", "name": "Drone Aerial Survey & NDVI Mapping", "description": "Aerial NDVI and vegetation health mapping for precise crop care decisions.", "category": "agri-technology", "price_info": "₹1,500 / acre", "rating": 4.7},
    {"service_id": "FA-SVC-000234", "name": "Satellite Crop Health Monitoring", "description": "Weekly satellite monitoring of crop health, moisture, and growth anomalies.", "category": "agri-technology", "price_info": "₹500 / acre / season", "rating": 4.6},
    {"service_id": "FA-SVC-000235", "name": "Smart Farming Dashboard Setup", "description": "Connecting farm data into one easy dashboard for soil, water, weather, and crop records.", "category": "agri-technology", "price_info": "₹700 / setup", "rating": 4.5},
    {"service_id": "FA-SVC-000236", "name": "Farm Record App & ERP Adoption", "description": "Training and setup for digital farm record keeping with cost and yield analytics.", "category": "agri-technology", "price_info": "₹500 / session", "rating": 4.5},
    {"service_id": "FA-SVC-000237", "name": "Automated Nutrient Dosing Systems", "description": "Sensor-driven nutrient dosing for hydroponic and precision systems.", "category": "agri-technology", "price_info": "₹15,000 / unit", "rating": 4.5},
    {"service_id": "FA-SVC-000238", "name": "Horticulture Shed-Net Agri-Photovoltaic Advisors", "description": "Design advisory for shade-net and agrivoltaic structures with microclimate control.", "category": "agri-technology", "price_info": "₹1,200 / consultation", "rating": 4.4},
    {"service_id": "FA-SVC-000239", "name": "Farm Data Security & Record Ownership", "description": "Protecting farm data ownership and secure sharing with buyers and bankers.", "category": "agri-technology", "price_info": "₹300 / consultation", "rating": 4.3},
    {"service_id": "FA-SVC-000240", "name": "Digital Agronomy API & Tools Training", "description": "Training farmers and staff on digital agronomy tools and advisory applications.", "category": "agri-technology", "price_info": "₹600 / session", "rating": 4.4},
    {"service_id": "FA-SVC-000241", "name": "Farm Visit Coordination & Scheduling", "description": "Scheduling and logistics coordination for visits by officials, experts, and buyers.", "category": "other-services", "price_info": "₹150 / visit", "rating": 4.3},
    {"service_id": "FA-SVC-000242", "name": "Legal Land & Tenancy Documentation Aid", "description": "Guidance to complete land tenancy and documentation needs for scheme eligibility.", "category": "other-services", "price_info": "₹400 / case", "rating": 4.4},
    {"service_id": "FA-SVC-000243", "name": "Farmer ID (KYC) & Records Premier", "description": "One-time digital KYC and farm photo-profile setup for smoother scheme access.", "category": "other-services", "price_info": "Free service", "rating": 4.6},
    {"service_id": "FA-SVC-000244", "name": "Seasonal Newsletter & Crops Bulletin", "description": "Alerts and crop-phase bulletins for raising operations in time.", "category": "other-services", "price_info": "Free service", "rating": 4.4},
    {"service_id": "FA-SVC-000245", "name": "Turning in Veterans & New-Farmer Support", "description": "Mentoring and advisory support for new and returning farmers during early seasons.", "category": "other-services", "price_info": "₹350 / session", "rating": 4.5},
    {"service_id": "FA-SVC-000246", "name": "Village Farmer Club & Group Linkage", "description": "Forming and linking village farmer groups for bulk input buying and shared learning.", "category": "other-services", "price_info": "₹500 / group", "rating": 4.4},
    {"service_id": "FA-SVC-000247", "name": "Rainbow Seed Bank & Germplasm Access", "description": "Access to community seed banks and indigenous germplasm for biodiversity protection.", "category": "other-services", "price_info": "₹250 / access", "rating": 4.3},
    {"service_id": "FA-SVC-000248", "name": "Farm Estate Succession Planning", "description": "Succession and inheritance planning to keep farm businesses intact for the next generation.", "category": "other-services", "price_info": "₹600 / consultation", "rating": 4.5},
    # @PART5DONE@
]


def seed_agricultural_services(db: Session):
    target = [build_service(d, i) for i, d in enumerate(SERVICES_CATALOG)]
    current = db.query(AgriculturalService).all()
    if len(current) == len(target):
        current_names = {s.name for s in current}
        if current_names == {t["name"] for t in target}:
            return

    db.query(AgriculturalService).delete()
    db.flush()
    for t in target:
        db.add(AgriculturalService(**t))
    db.commit()
    print(f"Services seeded: {len(target)} agriculture services across {len(CATEGORY_META)} categories.")