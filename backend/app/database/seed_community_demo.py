"""
Demo seed data for the Community feed.

This module populates the Community with a *clearly separated* set of realistic
demo content so the page feels like an active farmer social network:

* 40 demo farmers (``users.is_demo = True``)
* ~110 posts per supported category (Crops, Rice, Vegetables, ... General)
* comments, replies, answers, best answers, likes and saves on those posts

Every demo row is flagged with ``is_demo = True`` so it can be purged at any
time without touching real user data:

    python -m app.database.seed_community_demo             # seed
    python -m app.database.seed_community_demo --force    # wipe + reseed
    python -m app.database.seed_community_demo --wipe     # remove demo data only

Demo content flows through the exact same API/models as real content, so the
Community UI never needs to distinguish them - and can be swapped to fully real
data later by simply clearing the demo rows.
"""

import random
import sys
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models.community import (
    CommunityAnswer, CommunityComment, CommunityGroup, CommunityGroupMember,
    CommunityLike, CommunityPost, CommunitySave,
)
from app.models.user import FarmerProfile, User

POSTS_PER_CATEGORY = 110
MAIN_CATEGORIES = [
    "Crops", "Rice", "Vegetables", "Horticulture", "Soil", "Irrigation",
    "Pest & Disease", "Organic Farming", "Livestock", "Farm Machinery",
    "Markets", "Government Schemes", "Weather", "Technology",
    "Sustainability", "General",
]

LOCATIONS = [
    "Krishna District, AP", "Guntur District, AP", "Thanjavur, TN", "Tiruvallur, TN",
    "Karnal, Haryana", "Ludhiana, Punjab", "Amritsar, Punjab", "Nagpur, Maharashtra",
    "Pune, Maharashtra", "Nashik, Maharashtra", "Anand, Gujarat", "Rajkot, Gujarat",
    "Indore, MP", "Bhopal, MP", "Warangal, Telangana", "Karimnagar, Telangana",
    "Bellary, Karnataka", "Mysuru, Karnataka", "Patna, Bihar", "Muzaffarpur, Bihar",
    "Bardhaman, West Bengal", "Hooghly, West Bengal", "Cuttack, Odisha", "Sambalpur, Odisha",
    "Jabalpur, MP", "Varanasi, UP", "Lucknow, UP", "Agra, UP",
    "Hisar, Haryana", "Jalandhar, Punjab", "Udaipur, Rajasthan", "Jaipur, Rajasthan",
    "Coimbatore, TN", "Madurai, TN", "Kottayam, Kerala", "Kannur, Kerala",
    "Davanagere, Karnataka", "Sangli, Maharashtra", "Kurnool, AP", "Dhuri, Punjab",
]

DEMO_FARMERS = [
    # (name, location, farming_type, bio, verified)
    ("Ramesh Patil", "Sangli, Maharashtra", "Sugarcane & Grapes", "Third generation sugarcane farmer. Love trying new drip systems.", True),
    ("Lakshmi Devi", "Krishna District, AP", "Rice & Pulses", "Smallholder farmer growing paddy on 4 acres.", True),
    ("Arjun Singh Chandel", "Ludhiana, Punjab", "Wheat & Maize", "Machinery enthusiast, owns a combine harvester.", False),
    ("Meena Kumari", "Thanjavur, TN", "Paddy", "Rice farmer who also keeps desi cows.", False),
    ("Suresh Reddy", "Warangal, Telangana", "Cotton & Chilli", "Learnt vermicomposting from KVK courses.", True),
    ("Gita Patel", "Anand, Gujarat", "Dairy", "Owns 12 jersey cows, supplies to cooperative.", False),
    ("Nagaraju Goud", "Karimnagar, Telangana", "Vegetables", "Grows brinjal and tomato in polyhouse.", False),
    ("Sunita Bai", "Indore, MP", "Soybean & Wheat", "Organic farmer, zero-budget method.", True),
    ("Harpreet Kaur", "Amritsar, Punjab", "Wheat & Mustard", "Organic vegetable grower and SHG member.", False),
    ("Mohan Rao", "Guntur District, AP", "Chilli & Cotton", "Exports chillies through FPO.", True),
    ("Anitha Selvaraj", "Coimbatore, TN", "Coconut & Vegetables", "Tissue culture banana grower.", False),
    ("Vikram Joshi", "Pune, Maharashtra", "Grapes & Onion", "Precision farming with soil sensors.", True),
    ("Seeta Wankhede", "Nagpur, Maharashtra", "Oranges", "Organic orange orchard owner.", False),
    ("Dilip Rathod", "Rajkot, Gujarat", "Groundnut & Cotton", "Adapted zero tillage for cotton.", False),
    ("Pallavi Kamath", "Mysuru, Karnataka", "Floriculture", "Grows roses and marigold for market.", True),
    ("Kishan Verma", "Varanasi, UP", "Rice & Vegetables", "Young farmer using app for mandi rates.", False),
    ("Jamuna Tripathi", "Lucknow, UP", "Paddy & Mustard", "Women farmer leading a 20-member group.", True),
    ("Bhupendra Solanki", "Jaipur, Rajasthan", "Bajra & Groundnut", "Dryland farming specialist.", False),
    ("Rekha Nayak", "Cuttack, Odisha", "Rice & Vegetables", "Runs a seed bank in her village.", True),
    ("Farhan Sheikh", "Kannur, Kerala", "Arecanut & Coconut", "Integrated farming with poultry.", False),
    ("Nirmala Pedapati", "Bellary, Karnataka", "Cotton & Tur", "Uses helicopter spraying service.", False),
    ("Gurmeet Gill", "Jalandhar, Punjab", "Potato & Wheat", "Cold storage owner, contract potato farming.", True),
    ("Yashoda Bai", "Kurnool, AP", "Cotton", "Member of women FPO.", False),
    ("Prakash Mane", "Nashik, Maharashtra", "Grapes & Pomegranate", "Export quality grape grower.", True),
    ("Sandhya Rani", "Tiruvallur, TN", "Paddy & Sugarcane", "Drip irrigation adopter.", False),
    ("Devendra Yadav", "Muzaffarpur, Bihar", "Litchi & Vegetables", "Litchi orchard farmer.", False),
    ("Chand Bibi", "Hooghly, West Bengal", "Rice & Mustard", "Market-linked vegetable cluster farmer.", True),
    ("Om Prakash Meena", "Udaipur, Rajasthan", "Guar & Maize", "Dryland crops and rainwater harvesting.", False),
    ("Kalavathi", "Madurai, TN", "Jasmine & Vegetables", "Flower cluster farmer.", False),
    ("Shankar Iyer", "Kottayam, Kerala", "Rubber & Spices", "Pepper and nutmeg planter.", False),
    ("Rajeshwari Bhadri", "Sambalpur, Odisha", "Rice & Pulses", "Promotes System of Rice Intensification.", True),
    ("Anil Kumar Basa", "Bardhaman, West Bengal", "Rice & Potato", "Seed potato multiplication farmer.", False),
    ("Bhanu Pratap", "Jabalpur, MP", "Soybean & Wheat", "Happy seeder early adopter.", True),
    ("Savitri Pawar", "Kolhapur, Maharashtra", "Sugarcane & Milk", "Cooperative society chairperson.", False),
    ("Imran Qureshi", "Dhuri, Punjab", "Cotton & Wheat", "Crop diversification experimenter.", False),
    ("Geetanjali Mohanty", "Kendrapara, Odisha", "Rice & Crab Farming", "Integrated rice-crab farming pioneer.", True),
    ("Sanjeev Nair", "Kottarakkara, Kerala", "Coconut & Banana", "Organic conversion in progress.", False),
    ("Roopa Sree", "Davanagere, Karnataka", "Cotton & Paddy", "Women SHG treasurer.", False),
    ("Kabir Ahmed", "Golaghat, Assam", "Tea & Paddy", "Small tea grower.", False),
    ("Vasanth Kumar", "Salem, TN", "Tapioca & Maize", "Contract tapioca farmer.", False),
    ("Muni Rathnam", "Nellore, AP", "Paddy & Shrimp", "Aquaculture-adjacent rice farmer.", False),
]

# Shared connector sentences used across every category.
GENERIC_SENTENCES = [
    "Anyone else facing the same issue this season?",
    "What has worked for you on your farm?",
    "Sharing this so nobody makes the mistake I did.",
    "Local agriculture officers suggested this last week.",
    "I learnt this in the KVK training session.",
    "The fertilizer shop owner recommended this, but I want real farmer feedback.",
    "Has anyone tried this with good results?",
    "Cost per acre came down noticeably after this.",
    "Looking for experiences from farmers in a similar climate.",
    "Happy to share details if anyone needs them.",
    "This is my second year trying this approach.",
    "The mandi price this week made it worth it.",
    "My father taught me this method, and it still works.",
    "Open to suggestions before I commit to it fully.",
    "Also tried a small demo on one acre before scaling up.",
    "Please share your observations if you have tried this.",
    "Wrote this after a field day in our block.",
    "Consultants advised keeping close records, and it helps.",
    "Started with neighbours who saw good results last year.",
    "Will update with progress photos later this month.",
]

GENERIC_OPENERS = [
    "Here is what I observed on my farm:",
    "Just sharing a small experience:",
    "A quick question from the field:",
    "Thought this might help fellow farmers:",
    "My experience so far:",
    "Practical tip from the ground:",
    "Learnt something new yesterday:",
    "Want to compare notes on this:",
    "From my last season's record:",
]

GENERIC_CLOSERS = [
    "Looking forward to your views.",
    "Suggestions are most welcome.",
    "Hope this helps someone.",
    "Your feedback would mean a lot.",
    "Would love to hear local experiences.",
    "Happy farming everyone.",
]

COMMENT_POOL = [
    "Good to know, thank you!",
    "Tried this and it works.",
    "Can you share the source?",
    "This is a common issue here too.",
    "Thanks for the detailed share.",
    "We used a slightly different method.",
    "Any risk of overdoing it?",
    "Noted for this season.",
    "We faced the same last year, compost helped.",
    "Our block officer recommends exactly this.",
    "Great point, sharing with our group.",
    "Will try on a small plot first.",
]

ANSWER_POOL = [
    "We follow the same practice and it helps.",
    "Try reducing the dose by half first.",
    "Consult the local extension officer for this.",
    "This worked well in our sandy loam soil.",
    "Combine it with proper drainage.",
    "Many farmers in our cluster got good results.",
    "Monitor for a week after applying.",
    "Timing it with the rainfall forecast worked for us.",
]

# (titles, sentences, crops, tags) per category.
CONTENT_KIT = {
    "Crops": {
        "titles": [
            "Best sowing window for {crop} in our region?", "How to improve {crop} yield per acre?",
            "Common mistakes while growing {crop}", "Rotation advice: which crop after {crop}?",
            "Seed rate and spacing for {crop}", "What fertilizer plan works for {crop}?",
            "Irrigation schedule for {crop}", "Why is my {crop} turning yellow?",
            "Harvesting and storage tips for {crop}", "Crop insurance for {crop} - worth it?",
        ],
        "crops": ["wheat", "maize", "black gram", "green gram", "chickpea", "groundnut", "sugarcane", "cotton", "soybean"],
        "tags": ["crops", "yield", "sowing", "fertilizer", "harvest"],
        "sentences": [
            "Soil testing before sowing changed my fertilizer plan completely.",
            "Late sowing cut my chickpea yield by almost a quarter last year.",
            "DAP at sowing plus urea split after 30 days gave balanced growth.",
            "Green gram as a catch crop improved soil nitrogen for the next season.",
            "Legume crops fixed enough nitrogen to reduce urea use by one bag.",
            "Zero tillage worked well for sugarcane ratoons on clay soil.",
            "Crop rotation with pulses broke the pest cycle in our field.",
            "Harvesting at 14 percent moisture stopped grain damage in storage.",
            "Proper plant population at sowing decides the final yield.",
            "We maintain a small diary of operations for each plot.",
        ],
    },
    "Rice": {
        "titles": [
            "SRI method - real results in paddy?", "Best paddy variety for this season?",
            "How to control weeds in direct-seeded rice?", "Nursery management tips for healthy seedlings",
            "Water saving paddy techniques that actually work", "Why is my paddy turning pale after transplanting?",
            "Spacing and age of seedlings for transplanting", "Panicle initiation stage - what fertilizer to apply?",
            "Paddy harvesting - moisture and threshing tips", "Straw management after harvest",
        ],
        "crops": ["paddy", "basmati", "swarna", "samba", "hybrid rice"],
        "tags": ["rice", "paddy", "sri", "nursery", "transplanting"],
        "sentences": [
            "SRI transplanting reduced water use by a third with no yield loss.",
            "Younger seedlings recovered faster after transplanting.",
            "Maintaining shallow water through panicle stage matters most.",
            "We apply zinc sulphate once in nursery to avoid zinc deficiency.",
            "Direct seeded rice needs perfect land levelling to control weeds.",
            "Use of cono weeder twice reduced manual weeding cost heavily.",
            "Basmati paddy gave premium prices but needs careful water control.",
            "Straw incorporation with a decomposer sped up field preparation.",
            "Brown spot appeared when we skipped the potash dose.",
            "We chose the short-duration variety to fit a second crop.",
        ],
    },
    "Vegetables": {
        "titles": [
            "Tomato nursery tips for strong seedlings", "Organic pest control for vegetable plots?",
            "Best spacing for high-density chilli", "Drip fertigation schedule for vegetables",
            "Why are my brinjal flowers dropping?", "Cauliflower head not forming - why?",
            "Mulching experience - plastic vs straw?", "Off-season vegetable income tips",
            "Okra borer control that actually works", "Better price after washing and grading vegetables",
        ],
        "crops": ["tomato", "brinjal", "chilli", "cauliflower", "cabbage", "cucumber", "okra", "onion", "potato"],
        "tags": ["vegetables", "nursery", "mulching", "irrigation"],
        "sentences": [
            "Seedling drenching with biocontrol agents reduced damping off.",
            "Plastic mulch cut weed labour drastically in our tomato crop.",
            "Staking tomato plants improved airflow and fruit size.",
            "Cucumber on trellis uses half the space with nearly double yield.",
            "Slow-release fertilizer near the roots suits okra best.",
            "We harvest vegetables in the early morning for longer shelf life.",
            "Cauliflower needs consistent moisture at curd initiation.",
            "Spraying neem oil alternate weeks kept sucking pests in check.",
            "Rotation of beds prevented soil-borne disease build-up.",
            "Grow short-duration radish between main rows for extra income.",
        ],
    },
    "Horticulture": {
        "titles": [
            "Mango flowering management - tips needed", "Banana bunch weight improvement ideas",
            "Pomegranate cracking - causes and control?", "Guava propagation by grafting questions",
            "Fruit drop problem in litchi, please help", "Coconut nutrition and fertilizer schedule",
            "Dragon fruit support system that works", "Marigold as intercrop with vegetables",
            "Orchard pruning cycle advice", "Flower picking time for better vase life",
        ],
        "crops": ["mango", "banana", "pomegranate", "guava", "litchi", "papaya", "coconut", "dragon fruit"],
        "tags": ["horticulture", "orchard", "fruits", "flower"],
        "sentences": [
            "We used potassium sprays at flowering for mango fruit setting.",
            "Fruit thinning in pomegranate improved average fruit size.",
            "Banana bunch cover with non-woven bags protected the fingers.",
            "Regular basin mulching conserved moisture around guava trees.",
            "Litchi fruit drop reduced when we controlled leaf miner early.",
            "Coconut needs one round of organic manure and two of chemical.",
            "Dragon fruit poles spaced well apart with drip works nicely.",
            "Marigold rows between vegetables attracted pollinators.",
            "Pruning after harvest encouraged new flowering wood.",
            "Flowers cut in the early morning lasted two days longer.",
        ],
    },
    "Soil": {
        "titles": [
            "Soil test every season or every two years?", "Vermicompost vs farmyard manure - which first?",
            "How to fix acidic soil naturally?", "Organic carbon in soil - how to improve?",
            "Biofertilizer effectiveness in the field", "Gypsum for saline soil - dosage help",
            "Mulching impact on soil temperature", "Microbial culture spraying experience",
            "Green manuring with sunhemp results", "Signs your soil needs rest and care",
        ],
        "crops": ["soil", "compost", "lime", "gypsum"],
        "tags": ["soil", "soilhealth", "vermicompost", "testing", "fertility"],
        "sentences": [
            "Our soil pH came down after two seasons of lime application.",
            "Vermicompost at two tonnes per acre improved soil texture visibly.",
            "Green manure ploughing added organic matter faster than expected.",
            "A soil test saved us from an unnecessary expensive fertilizer bill.",
            "Biofertilizer with organic manure performed better than alone.",
            "Crop residues retained on field reduced moisture loss.",
            "Gypsum helped break the hard clay layer in our block.",
            "Earthworm count rose noticeably after regular compost addition.",
            "We avoid deep ploughing every year to protect soil life.",
            "Cover crops in the off season kept the soil covered.",
        ],
    },
    "Irrigation": {
        "titles": [
            "Drip system cost and subsidy details", "Sprinkler vs drip for vegetables?",
            "Rainwater harvesting on the farm - setup tips", "How to avoid waterlogging in rainy season?",
            "Irrigation schedule for wheat with limited water", "Drip fertigation: mixing nutrients in tank",
            "Laser land levelling worth it?", "Motor and pipe sizing for small farm",
            "Water quality - is borewell water safe?", "Solar pump experience in farming",
        ],
        "crops": ["drip", "sprinkler", "rainwater"],
        "tags": ["irrigation", "drip", "sprinkler", "water", "waterlogging"],
        "sentences": [
            "Drip with mulch halved the water requirement for chilli.",
            "We schedule sprinkler runs early morning to reduce evaporation.",
            "Rainwater harvesting pit recharged the borewell in our farm.",
            "A moisture sensor app tells me exactly when to irrigate.",
            "Raised beds solved the seasonal waterlogging problem.",
            "Fertigation through drip gave even application of nutrients.",
            "Laser levelling made irrigation uniform across the field.",
            "Solar pump running costs beat diesel within two seasons.",
            "We alternate furrow irrigation to save water in wheat.",
            "Laying laterals at proper spacing prevents wet and dry patches.",
        ],
    },
    "Pest & Disease": {
        "titles": [
            "Fall armyworm in maize - best control?", "Whitefly on cotton: what worked for you?",
            "Chilli thrips control recommendations", "Tomato late blight - treatment plans",
            "Brown plant hopper in paddy urgent help", "Fruit borer damage in brinjal",
            "Yellowing and curling leaves cause?", "Safe pesticide mix for field spraying",
            "Yellow sticky traps - do they help?", "Biological control agents available locally?",
        ],
        "crops": ["rice", "cotton", "chilli", "tomato", "brinjal"],
        "tags": ["pest", "disease", "ipm", "spray"],
        "sentences": [
            "Early scouting twice a week caught the pest before spread.",
            "Neem-based spray kept sucking pests at moderate levels.",
            "Yellow sticky traps reduced whitefly numbers noticeably.",
            "Spraying in the late afternoon gave better results.",
            "We rotate chemicals to avoid pest resistance.",
            "Removing and destroying infected leaves checked the spread.",
            "Predatory insects increased after we stopped harsh chemicals.",
            "Disease appeared after heavy rain; drainage fixed it.",
            "Seed treatment prevented early seedling infection.",
            "Foliar spray of borax helped the curling leaves recover.",
        ],
    },
    "Organic Farming": {
        "titles": [
            "Organic transition - what to expect in year one?", "Making good compost: ratios and turning",
            "Cow urine and neem foliar sprays experience", "Biocontrol options instead of chemicals",
            "Organic certification process steps", "Natural farming vs organic - key difference",
            "How to handle first-year yield drop?", "Organic pest sprays that actually work",
            "Local organic input sources", "Marketing organic produce at premium price",
        ],
        "crops": ["vermicompost", "neem", "cow dung"],
        "tags": ["organic", "organicfarming", "compost", "natural", "certification"],
        "sentences": [
            "Compost turned once a week matured in two months.",
            "Cow dung slurry enriched our beds with microbes.",
            "Neem seed kernel extract sprayed once a week on veggies.",
            "The first organic season yield was lower, but cost dropped.",
            "Certification body asked for field history records.",
            "We sell certified vegetables at a fixed premium to regulars.",
            "Biochar in compost improved retention of nutrients.",
            "Leguminous intercrops supplied nitrogen naturally.",
            "Cover cropping reduced weed pressure over time.",
            "Our market cluster supports organic growers with logistics.",
        ],
    },
    "Livestock": {
        "titles": [
            "Milk yield improvement through feeding", "Best fodder crops for year-round green feed",
            "Calf care tips after birth", "Poultry vaccination schedule questions",
            "Goat rearing income and care", "Buffalo breeding: AI vs natural?",
            "Managing mastitis in dairy animals", "Silage making from maize fodder",
            "Desi vs crossbred cow for small farm", "Clean milk production practices",
        ],
        "crops": ["cattle", "buffalo", "goat", "poultry", "fodder"],
        "tags": ["livestock", "dairy", "poultry", "fodder", "goat"],
        "sentences": [
            "Balanced feed with mineral mixture improved milk fat.",
            "Napier grass cut every 45 days feeds the stock well.",
            "Colostrum fed in the first hour built calf immunity.",
            "We follow the vaccination calendar without missing a dose.",
            "Kid care in the first week decided the goat project's success.",
            "AI records helped us plan calving dates better.",
            "Clean udder hygiene reduced mastitis cases sharply.",
            "Maize silage stored well lasted the dry season.",
            "Desi cows are easier to manage on limited feed.",
            "Free-range poultry supplements the kitchen income nicely.",
        ],
    },
    "Farm Machinery": {
        "titles": [
            "Second-hand tractor buying checklist", "Renting vs buying a rotavator?",
            "Combine harvester custom hiring rates", "Attachments that pay for themselves",
            "Happy seeder experience in wheat", "Maintenance tips for diesel engines",
            "GPS guidance for farmers worth it?", "Choosing the right plough for clay soil",
            "Safety precautions during operations", "Repair network in rural areas",
        ],
        "crops": ["tractor", "rotavator", "harvester", "planter"],
        "tags": ["machinery", "tractor", "rotavator", "harvester"],
        "sentences": [
            "A used rotavator paid for itself in two seasons.",
            "Custom hiring a combine cut harvest cost per acre.",
            "Timely greasing extended our tractor's life.",
            "The happy seeder left paddy straw and gave a good wheat stand.",
            "Automatic boom height saved time during spraying.",
            "Disc harrow works best on our clay soil.",
            "We keep a basic toolkit and trained two operators.",
            "Fuel records helped us estimate cost per acre.",
            "GPS-guided sowing for straight rows used less seed.",
            "Periodic filter cleaning avoids most breakdowns.",
        ],
    },
    "Markets": {
        "titles": [
            "Best time to sell paddy in the season?", "e-NAM experience - higher price or not?",
            "Direct selling to buyers vs mandi", "How to check daily mandi rates quickly?",
            "Grading and cleaning for premium price", "Export rules for chilli and spices",
            "Contract farming pitfalls to avoid", "Cold storage and selling later - worth it?",
            "FPO collective selling benefits", "Price forecasts for next season crops",
        ],
        "crops": ["mandi", "e-NAM", "onion", "chilli"],
        "tags": ["markets", "mandi", "prices", "enam", "selling"],
        "sentences": [
            "Selling through the FPO gave us a better pooled price.",
            "e-NAM bidding pushed the price above the local mandi.",
            "Grading before auction improved our onion realisation.",
            "Small market arrivals usually mean firm prices.",
            "We check the official mandi app every morning.",
            "Storing in the cooperative cold store paid off after two weeks.",
            "Quality certificate helped us tap the export buyer.",
            "Long-distance buyers pay for proper packing.",
            "Contract farming needs a clear, written weight and price basis.",
            "Watching arrivals across three mandis informs our selling day.",
        ],
    },
    "Government Schemes": {
        "titles": [
            "KCC limit increase process steps", "Subsidy for drip irrigation - how to apply?",
            "PMFBY claim settlement experience", "PM-KISAN instalment issues anyone?",
            "Subsidy on tractor and implements", "Soil health card scheme usage",
            "Organic certification subsidy details", "Seed subsidy for pulse crops",
            "How to check scheme eligibility online?", "Village-level officer contacts for schemes",
        ],
        "crops": ["kisan credit card", "subsidy", "insurance"],
        "tags": ["schemes", "subsidy", "kcc", "insurance", "pmfby"],
        "sentences": [
            "A complete KCC application got me a higher limit quickly.",
            "Drip subsidy forms go through the horticulture department.",
            "PMFBY claim forms need the right crop loss documents.",
            "PM-KISAN direct transfer arrives on time for most.",
            "We bought a rotavator with subsidy support.",
            "Soil health card recommendations matched our lab results.",
            "The organic cluster availed certification cost support.",
            "Pulse seed subsidy reduced our input bill this season.",
            "All scheme records are now checked on the portal.",
            "A farmer service centre helped us complete the forms.",
        ],
    },
    "Weather": {
        "titles": [
            "Monsoon onset delay - sowing adjustments?", "Rainfall forecast reliability for farmers",
            "Protecting crops from unseasonal rain", "Hailstorm damage - what to do next?",
            "Frost protection tips for vegetables", "Heat wave impact on summer crops",
            "Weather-based crop advisories useful?", "Grain drying during humid days",
            "Preparing fields before expected heavy rain", "Signs to watch in local weather patterns",
        ],
        "crops": ["monsoon", "rain", "hail", "frost"],
        "tags": ["weather", "rainfall", "monsoon", "forecast", "climate"],
        "sentences": [
            "We held sowing till the forecast showed steady rain.",
            "Weather advisory SMS helped us plan the spray day.",
            "Unseasonal rain damaged the open grain before cover.",
            "Frost blankets over the nursery saved young seedlings.",
            "Heat stress during flowering lowered the fruit set.",
            "Humidity gauge guides our drying and storage timing.",
            "Drainage channels cleared before monsoon protected the field.",
            "Cloudy weeks call for extra care against blight.",
            "We time fertilizer application to avoid heavy rain days.",
            "Mulch kept the soil temperature stable during the heat wave.",
        ],
    },
    "Technology": {
        "titles": [
            "Drone spraying experience and cost", "Soil moisture sensors - do they pay off?",
            "Best apps for farm record keeping", "Precision agriculture on a small farm",
            "Solar fencing for field protection", "AI disease detection photos - reliability?",
            "Digital mandi platforms comparison", "Automated irrigation controller setup",
            "Using spreadsheets for crop budget", "Smart spray schedule apps",
        ],
        "crops": ["drones", "sensor", "app", "fencing"],
        "tags": ["technology", "agritech", "drone", "sensors"],
        "sentences": [
            "Drone spraying in cotton saved time and chemical evenly.",
            "Two soil sensors guide our irrigation decisions now.",
            "The farm record app warns when expenses cross budget.",
            "Precision seeding with variable rate saved seed.",
            "Solar fencing protected the fields from stray cattle.",
            "We use photo-based disease detection as a second opinion.",
            "Digital mandi bids opened better markets for our produce.",
            "An automated timer runs drip cycles when we are away.",
            "A simple budget sheet made each crop profitable to track.",
            "GPS mapping of plots helps with planning and insurance.",
        ],
    },
    "Sustainability": {
        "titles": [
            "Agroforestry species for our region", "Reducing chemical input step by step",
            "Rainwater harvesting for climate resilience", "Carbon farming basics explained",
            "Intercropping systems that sustain soil", "Biodiversity strips on the farm",
            "Comparing organic vs conventional costs", "Climate-resilient crop selection",
            "Renewable energy on the farm", "Water-saving practices for dry years",
        ],
        "crops": ["agroforestry", "organic", "biodiversity"],
        "tags": ["sustainability", "climate", "agroforestry", "carbon"],
        "sentences": [
            "Mango rows along the boundary double as windbreak and income.",
            "We cut chemical use by a third using IPM in two seasons.",
            "Every roof on the farm now feeds the rainwater pit.",
            "Mulched beds kept moisture for a full week in summer.",
            "Diversified crops reduce the risk of a single failure.",
            "Native flowering plants attract beneficial insects.",
            "Biodiesel and biomass finally replaced diesel pumping days.",
            "Legume intercropping fixed nitrogen and cut urea use.",
            "Simple per-acre cost records show sustainability is cheaper.",
            "Swales along the slope harvest runoff efficiently.",
        ],
    },
    "General": {
        "titles": [
            "Introducing myself - new farmer here", "Best farming tip that changed your farm",
            "How do you manage farm finances?", "Training programs worth attending",
            "Dealing with labour shortage", "Success story from our village",
            "Planning the next season - where to start?", "Books and resources for farmers",
            "Farmers' field day experiences", "Sharing a bumper harvest moment",
        ],
        "crops": ["farm", "market", "training"],
        "tags": ["farming", "community", "training", "tips"],
        "sentences": [
            "Started farming full time two years ago on inherited land.",
            "One good neighbour taught me more than many courses.",
            "Keeping records changed how I plan every input.",
            "KVK training on composting was very practical.",
            "We pool labour among five families during transplanting.",
            "Our village celebrates every successful first harvest.",
            "Reading weather and soil bulletins helps season planning.",
            "Farmers' field days are the best place for tricks.",
            "This community group solved my marketing questions.",
            "Simple, consistent effort beats heroic one-time acts.",
        ],
    },
}


def _rng():
    return random.Random()


def _pick(pool, rnd):
    return rnd.choice(pool)


def _sample(pool, k, rnd):
    if k >= len(pool):
        return list(pool)
    return rnd.sample(pool, k)


def _content_sentences(category, rnd):
    """Build a varied, realistic post body for a category."""
    kit = CONTENT_KIT[category]
    parts = []
    if rnd.random() < 0.4:
        parts.append(_pick(GENERIC_OPENERS, rnd))
    parts.extend(_sample(kit["sentences"], rnd.randint(3, 4), rnd))
    parts.extend(_sample(GENERIC_SENTENCES, rnd.randint(1, 2), rnd))
    if rnd.random() < 0.5:
        parts.append(_pick(GENERIC_CLOSERS, rnd))
    rnd.shuffle(parts)
    return parts[:7]


def _make_title(kit, rnd):
    t = _pick(kit["titles"], rnd)
    return t.replace("{crop}", _pick(kit["crops"], rnd))


def _timestamp(rnd):
    days = int(rnd.expovariate(1.0 / 45.0))
    days = min(days, 180)
    hours = rnd.randint(5, 20)
    minutes = rnd.randint(0, 59)
    ago = timedelta(days=days, hours=24 - (hours % 24), minutes=minutes)
    return datetime.utcnow() - ago


def _seq_start(db, model, column_name, prefix):
    highest = 0
    for (val,) in db.query(getattr(model, column_name)).filter(
        getattr(model, column_name).like(f"{prefix}-%")
    ).all():
        try:
            digit = str(val).split("-")[-1]
            highest = max(highest, int(digit))
        except (TypeError, ValueError):
            continue
    return highest + 1


def seed_demo(db: Session, force: bool = False) -> dict:
    """Seed the demo Community content. Idempotent; ``force`` reseeds."""
    from app.database.seed_communities import CATALOG_BY_CATEGORY

    if force:
        wipe_demo(db)

    existing_demo_posts = db.query(CommunityPost.id).filter(
        CommunityPost.is_demo == True
    ).first()
    if existing_demo_posts:
        demo_farmers = db.query(User).filter(User.is_demo == True).count()
        return {"farmers": demo_farmers, "skipped": True, "posts": 0,
                "comments": 0, "answers": 0, "likes": 0, "saves": 0}

    rnd = _rng()

    # ------------------------------------------------------------------ farmers
    demo_users = []
    existing_demo = {u.farmer_id: u for u in
                     db.query(User).filter(User.farmer_id.like("DEMO-%")).all()}
    existing_phones = {p for (p,) in db.query(User.phone_number).all()}
    profile_ids = {pid for (pid,) in db.query(FarmerProfile.user_id).all()}
    need_profile = []
    for i, (name, location, ftype, bio, verified) in enumerate(DEMO_FARMERS, start=1):
        fid = f"DEMO-{i:04d}"
        u = existing_demo.get(fid)
        if u is None:
            base = f"9895{900000 + i:06d}"
            phone = base
            guard = 0
            while phone in existing_phones and guard < 50:
                guard += 1
                phone = f"9895{900000 + i + guard:06d}"
            existing_phones.add(phone)
            u = User(
                farmer_id=fid,
                full_name=name,
                phone_number=phone,
                password_hash="demo-seed-user",
                is_verified=verified,
                is_active=True,
                is_demo=True,
                created_at=datetime.utcnow() - timedelta(days=rnd.randint(120, 400)),
            )
            need_profile.append((u, location, ftype, bio))
        elif u.id not in profile_ids:
            need_profile.append((u, location, ftype, bio))
        demo_users.append(u)
    db.add_all(demo_users)
    db.flush()

    for u, location, ftype, bio in need_profile:
        db.add(FarmerProfile(
            user_id=u.id,
            farmer_id=f"PRO-{u.farmer_id}",
            farming_type=ftype,
            farm_location=location,
            bio=bio,
            farming_experience=f"{rnd.randint(3, 32)} years",
        ))
    db.flush()
    db.commit()  # persist farmers so generate lookups below are stable

    post_seq = _seq_start(db, CommunityPost, "post_id", "FA-PST")
    answer_seq = _seq_start(db, CommunityAnswer, "answer_id", "FA-ANS")

    groups_by_name = {g.name: g for g in db.query(CommunityGroup).all()}

    posts_done = 0
    for category in MAIN_CATEGORIES:
        kit = CONTENT_KIT[category]
        for _ in range(POSTS_PER_CATEGORY):
            rtype = rnd.random()
            if rtype < 0.36:
                post_type, has_title = "question", True
            elif rtype < 0.62:
                post_type, has_title = "discussion", False
            elif rtype < 0.82:
                post_type, has_title = "experience", rnd.random() < 0.4
            else:
                post_type, has_title = "advice", False

            author = _pick(demo_users, rnd)
            created = _timestamp(rnd)
            sentences = _content_sentences(category, rnd)
            content = " ".join(sentences)

            tags = _sample(kit["tags"], rnd.randint(0, 2), rnd)
            if tags:
                content += " " + " ".join("#" + t for t in tags)

            crop = _pick(kit["crops"], rnd) if rnd.random() < 0.55 else None
            location = _pick(LOCATIONS, rnd) if rnd.random() < 0.6 else None

            image_url = None
            if rnd.random() < 0.16:
                seed = f"fa{str(crop or 'farm').replace(' ', '')[:6]}{posts_done}"
                image_url = f"https://picsum.photos/seed/{seed}/720/460"

            community_id = None
            category_groups = CATALOG_BY_CATEGORY.get(category, [])
            if category_groups and rnd.random() < 0.5:
                group = groups_by_name.get(_pick(category_groups, rnd))
                if group:
                    community_id = group.id

            title = _make_title(kit, rnd) if has_title else None
            if post_type == "question" and title and title[-1] != "?":
                title = title.rstrip(".") + "?"

            post = CommunityPost(
                post_id=f"FA-PST-{post_seq:08d}",
                user_id=author.id,
                community_id=community_id,
                title=title,
                content=content,
                category=category,
                crop=crop,
                location=location,
                image_url=image_url,
                media_type="image" if image_url else "text",
                post_type=post_type,
                is_active=True,
                is_demo=True,
                created_at=created,
                updated_at=created,
            )
            db.add(post)
            db.flush()  # populate post.id so FK references below resolve
            post_seq += 1
            posts_done += 1

            # likes: a share of demo farmers + larger display count
            like_rows_created = 0
            for liker in _sample(demo_users, rnd.randint(1, 5), rnd):
                db.add(CommunityLike(post_id=post.id, user_id=liker.id,
                                     is_demo=True, created_at=created))
                like_rows_created += 1
            post.likes_count = like_rows_created + rnd.randint(0, 24)

            # comments (some with a reply)
            if rnd.random() < 0.6:
                n_comments = rnd.randint(1, 5)
                commenters = _sample(demo_users, n_comments, rnd)
                for cus in commenters:
                    body = _pick(COMMENT_POOL, rnd)
                    db.add(CommunityComment(post_id=post.id, user_id=cus.id,
                                            content=body, is_demo=True,
                                            created_at=created + timedelta(
                                                minutes=rnd.randint(2, 300))))
                post.comments_count = n_comments

            # answers for question posts
            if post_type == "question" and rnd.random() < 0.8:
                n_answers = rnd.randint(1, 3)
                for au in _sample(demo_users, n_answers, rnd):
                    db.add(CommunityAnswer(
                        answer_id=f"FA-ANS-{answer_seq:08d}",
                        post_id=post.id,
                        user_id=au.id,
                        content=_pick(ANSWER_POOL, rnd),
                        is_best_answer=rnd.random() < 0.25,
                        is_demo=True,
                        created_at=created + timedelta(hours=rnd.randint(1, 72)),
                    ))
                    answer_seq += 1

            # saves
            if rnd.random() < 0.18:
                db.add(CommunitySave(post_id=post.id, user_id=_pick(demo_users, rnd).id,
                                     is_demo=True, created_at=created))
                post.saves_count = 1
            else:
                post.saves_count = 0

            post.shares_count = rnd.randint(0, 18)

            if posts_done % 200 == 0:
                db.flush()

    # ------------------------------------------------------------------ memberships
    members_added = 0
    for group in groups_by_name.values():
        for u in _sample(demo_users, rnd.randint(12, 41), rnd):
            db.add(CommunityGroupMember(
                community_id=group.id,
                user_id=u.id,
                joined_at=_timestamp(rnd),
            ))
            members_added += 1

    db.commit()
    return {
        "farmers": len(demo_users),
        "posts": posts_done,
        "comments": db.query(CommunityComment).filter(CommunityComment.is_demo == True).count(),
        "answers": db.query(CommunityAnswer).filter(CommunityAnswer.is_demo == True).count(),
        "likes": db.query(CommunityLike).filter(CommunityLike.is_demo == True).count(),
        "saves": db.query(CommunitySave).filter(CommunitySave.is_demo == True).count(),
        "members": members_added,
        "skipped": False,
    }


def wipe_demo(db: Session) -> None:
    """Remove every demo-flagged row (posts, interactions and demo farmers)."""
    db.query(CommunityLike).filter(CommunityLike.is_demo == True).delete(synchronize_session=False)
    db.query(CommunitySave).filter(CommunitySave.is_demo == True).delete(synchronize_session=False)
    db.query(CommunityAnswer).filter(CommunityAnswer.is_demo == True).delete(synchronize_session=False)
    db.query(CommunityComment).filter(CommunityComment.is_demo == True).delete(synchronize_session=False)
    db.query(CommunityPost).filter(CommunityPost.is_demo == True).delete(synchronize_session=False)

    demo_ids = [uid for (uid,) in db.query(User.id).filter(User.is_demo == True).all()]
    if demo_ids:
        db.query(CommunityGroupMember).filter(
            CommunityGroupMember.user_id.in_(demo_ids)
        ).delete(synchronize_session=False)
        db.query(FarmerProfile).filter(FarmerProfile.user_id.in_(demo_ids)).delete(synchronize_session=False)
        db.query(User).filter(User.id.in_(demo_ids)).delete(synchronize_session=False)
    db.commit()


if __name__ == "__main__":
    from app.database.connection import SessionLocal

    if "--wipe" in sys.argv:
        session = SessionLocal()
        try:
            wipe_demo(session)
            print("seed_community_demo: demo data wiped")
        finally:
            session.close()
        sys.exit(0)

    session = SessionLocal()
    try:
        result = seed_demo(session, force="--force" in sys.argv)
        print("seed_community_demo:", result)
    finally:
        session.close()