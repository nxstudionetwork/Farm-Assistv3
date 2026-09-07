const FarmDB = (function() {
  const db = {
    farms: [], plots: [], tasks: [], products: [], transactions: [], news: [],
    experts: [], posts: [], notifications: [], orders: [], livestock: [],
    suggestions: [], events: [], chatMessages: [], jobs: [], courses: [], documents: [],
    // NEW CATEGORIES
    waterSources: [], irrigationSchedules: [], fertilizerGuides: [],
    workers: [], equipmentRentals: [], seedInventory: [], soilHealth: [],
    marketPrices: [], cropDiseases: [], govSchemes: [], weatherData: []
  };

  const rand = (arr) => arr[Math.floor(Math.random() * arr.length)];
  const rng = (min, max) => Math.floor(Math.random() * (max - min + 1)) + min;
  const dateOff = (days) => { const d = new Date(); d.setDate(d.getDate() + days); return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }); };

  // 1. EXISTING FARMS & PLOTS (preserved)
  const farmNames = ["Green Acre Homestead", "Saraswati Organic Fields", "Deccan Foothills Farm", "Vanguard Hydroponics Valley", "Sunrise Agro Estate", "Kaveri Riverside Farms", "Golden Harvest Grounds", "Nilgiri Terrace Farm", "Maruti Krishi Bhoomi", "Shakti Green Valley", "Anmol Organic Acres", "Sahyadri Highlands Farm", "Prakruti Agro Park", "Suryodaya Fields", "Annapurna Farmstead", "Bharat Agri Co-op", "Vasundhara Estate", "Krishna Delta Farm"];
  const farmDistricts = ["Pune", "Nashik", "Nagpur", "Kolhapur", "Solapur", "Aurangabad", "Satara", "Ahmednagar", "Sangli", "Amravati"];
  const farmManagers = ["Ramesh Kumar", "Suresh Patil", "Anita Deshmukh", "Vijay Rao", "Priya Sharma", "Ganesh More", "Lakshmi Naidu", "Farhan Ali"];
  const cropTypes = ["Rice", "Cotton", "Maize", "Wheat", "Sugarcane", "Tomato", "Potato", "Soybean", "Mustard", "Chilli", "Onion", "Bajra", "Groundnut"];
  const FARM_COUNT = 15;
  for (let i = 1; i <= FARM_COUNT; i++) db.farms.push({ id: `F${i}`, name: farmNames[(i-1) % farmNames.length], location: `Sector ${String.fromCharCode(64+((i-1)%26)+1)}, ${farmDistricts[i % farmDistricts.length]}`, size: `${(i%9)*8 + 12} Acres`, manager: farmManagers[i % farmManagers.length], joined: "Jan 2024" });
  for (let i = 1; i <= 150; i++) {
    const s = ["Healthy","Needs Water","Pest Risk","Harvest Ready","Stable"];
    db.plots.push({
      id: i, farmId: `F${(i%FARM_COUNT)+1}`, farmName: farmNames[(i%FARM_COUNT) % farmNames.length], name: `Plot ${String.fromCharCode(65+(i%8))}${i}`, crop: cropTypes[i%cropTypes.length],
      status: i===2?"Needs Water":i===5?"Pest Risk":i===12?"Harvest Ready":rand(s),
      ndvi: `${rng(55,96)}%`, moisture: `${rng(30,72)}%`, temp: `${rng(24,32)}°C`,
      waterNeeded: i%3===0?"High":i%3===1?"Medium":"Low",
      soilNPK: `N:${rng(30,80)}, P:${rng(20,50)}, K:${rng(40,90)} kg/ha`,
      planted: dateOff(-rng(30,120)), expectedHarvest: dateOff(rng(15,60))
    });
  }

  // 2. TASKS (100)
  const taskDescs = ["Apply drip irrigation","Inspect pest traps","Distribute NPK booster","Calibrate harvesters","Test soil pH","NDVI leaf analysis","Manual weeding","Clear drainage","Neem oil spray","Prepare seedling beds"];
  const taskCats = ["Irrigation","Pests","Fertilizer","Harvest","Soil","Pruning","Tilling","Seeding","Weeding"];
  for (let i = 1; i <= 100; i++) {
    db.tasks.push({
      id: i, text: `${rand(taskDescs)} - Plot ${String.fromCharCode(65+(i%8))}`,
      completed: i%3===0, category: rand(taskCats), priority: rng(1,3),
      date: dateOff(-(i%15)), plotId: (i%30)+1
    });
  }

  // 3. PRODUCTS (100+ preserved and expanded)
  const prodCats = ["seeds","fertilizers","pesticides","equipment","livestock","rentals"];
  const brands = ["KrishiGold","EcoSeed","BharatAgri","SoilShield","Pioneer","TractorCorp","SolarHarvest","AgriTech"];
  const seeds = [
    {n:"Premium Basmati Rice Seeds V2",p:920},{n:"Hybrid Bt Cotton Seeds",p:1450},{n:"Organic Golden Maize 5kg",p:780},
    {n:"High-Drought Wheat Grain Seeds",p:620},{n:"Cherry Tomato Seeds 100g",p:340},{n:"Red Onion Globe Seed Pack",p:420},
    {n:"Early-Sprout Mustard 2kg",p:510},{n:"Hybrid Paddy Seeds DRR-50",p:1100}
  ];
  const ferts = [
    {n:"Bio-Organic Humic Acid",p:880},{n:"NPK 19-19-19 Soluble",p:1250},{n:"Pure Vermicompost",p:450},
    {n:"Neem Cake Meal Organic",p:650},{n:"Micronutrient Mix 1kg",p:320},{n:"Gypsum Soil Block",p:980},
    {n:"DAP Fertilizer 50kg",p:1400},{n:"Urea 46% Nitrogen 50kg",p:1200}
  ];
  const pest = [
    {n:"Eco Neem Oil Guard 1L",p:540},{n:"Fungal Shield Copper 500ml",p:480},{n:"Trichoderma Bio Powder",p:380},
    {n:"Snail Sentry Traps 6pk",p:290},{n:"Mite Shield Botanical",p:610},{n:"Bacterial Blight Control 1L",p:720}
  ];
  const equip = [
    {n:"Bluetooth Soil NPK Sensor",p:3499},{n:"Drip Irrigation WiFi Hub",p:5200},{n:"Ergonomic Hand Trowel",p:290},
    {n:"Solar Fence Energizer",p:8900},{n:"Backpack Sprayer 16L",p:2450},{n:"Rain Gauge & Dial",p:750},
    {n:"Soil Moisture Meter Digital",p:1200},{n:"Portable Weather Station",p:6500}
  ];
  const live = [
    {n:"Gir Dairy Cow (Lactation)",p:72000},{n:"Murrah Water Buffalo",p:85000},{n:"Sirohi Goat Male",p:11200},
    {n:"Rhode Island Chickens 25pk",p:3750},{n:"Italian Bee Hive",p:4800},{n:"Kadaknath Chicken Pair",p:2500}
  ];
  const rent = [
    {n:"Mahindra 575 DI Tractor Daily",p:3200},{n:"Laser Land Leveler Daily",p:1800},{n:"Paddy Transplanter Daily",p:4500},
    {n:"Power Thresher Daily",p:2800},{n:"NDVI Drone Mapping",p:6000},{n:"Combine Harvester Daily",p:8500}
  ];
  const allProducts = [...seeds,...ferts,...pest,...equip,...live,...rent];
  let pid = 1;
  prodCats.forEach((cat,ci) => {
    const items = [seeds,ferts,pest,equip,live,rent][ci];
    items.forEach(p => {
      db.products.push({
        id: pid++, name: p.n, price: p.p, category: cat, rating: (rng(42,49)/10).toFixed(1),
        reviews: rng(15,230), tag: rand(["Best Seller","Recommended","Eco Friendly","New","10% OFF","Trending"]),
        icon: ["fa-seedling","fa-leaf","fa-spray-can","fa-microchip","fa-cow","fa-tractor"][ci],
        brand: rand(brands), stock: rng(5,50), seller: `Pune Agritech (${rng(4,5)}★)`
      });
    });
  });
  while (db.products.length < 100) {
    const b = db.products[rng(0,db.products.length-1)];
    db.products.push({ id: pid++, name: `${b.name} Batch#${rng(10,99)}`, price: Math.floor(b.price*(rng(90,110)/100)), category: b.category, rating: b.rating, reviews: rng(5,150), tag: pid%4===0?"Flash Deal":rand(["New","Sale","Limited"]), icon: b.icon, brand: b.brand, stock: rng(2,40), seller: b.seller });
  }

  // 4-16. EXISTING DATA (preserved with expanded counts)
  const txTypes = [
    {d:"Sold Crop Harvest",a:52000,t:"income"},{d:"Purchased NPK Fertilizer",a:-4800,t:"expense"},{d:"Tractor Rental 2 Days",a:-6400,t:"expense"},
    {d:"PM-Kisan Subsidy",a:2000,t:"income"},{d:"Milk Yield Sale",a:15400,t:"income"},{d:"Farm Labor Salaries",a:-9000,t:"expense"},
    {d:"Smart Sensor Probes",a:-3499,t:"expense"},{d:"Organic Seeds Packets",a:-1850,t:"expense"},{d:"Insurance Payout",a:24000,t:"income"},{d:"Sold Sheep Marketplace",a:47500,t:"income"}
  ];
  for (let i = 1; i <= 80; i++) {
    const b = txTypes[i%txTypes.length];
    db.transactions.push({ id: `TX${100+i}`, desc: `${b.d} #${rng(10,99)}`, amount: Math.floor(b.a*(rng(90,110)/100)), type: b.t, date: dateOff(-(i%20)), category: b.t==="income"?"sales":b.d.includes("Fertilizer")?"inputs":"labor" });
  }

  const newsTitles = [
    "Subsidies on Drip Irrigation expanded to 55%","Basmati Export caps lifted, prices surge",
    "Early monsoon expected, IMD advisory","Soil health cards save 20% on fertilizer",
    "New dwarf rice variety pest resilient","KUSUM solar scheme accepting applications",
    "Heatwave alert Maharashtra: irrigation advised","Organic certification simplified",
    "Community cold storage opens in Haveli","Drone pilot training for farmers launched",
    "MSP increased for Kharif crops 2026","New pest-resistant cotton variety released",
    "National agriculture market digital platform","Zero-budget natural farming initiative expanded"
  ];
  for (let i = 1; i <= 100; i++) db.news.push({ id: i, source: rand(["Krishi Vigyan","AgriMarket Pulse","IMD","Agritech Today","PIB"]), headline: `${newsTitles[i%newsTitles.length]} - Update ${i}`, category: rand(["technology","market","government","weather","agri"]), time: i<3?"30 min ago":`${rng(1,23)}h ago`, summary: "Agricultural news and policy updates for farmers.", bookmarked: i%7===0 });

  const experts = [
    {n:"Dr. Arvind Swaminathan",r:"Agronomist"},{n:"Dr. Meera Deshmukh",r:"Veterinarian"},{n:"Dr. Ralph Vance",r:"Soil Scientist"},{n:"Ananya Sen",r:"Pest Controller"},
    {n:"Prof. G.S. Randhawa",r:"Horticulturist"},{n:"Dr. Sarah Patel",r:"Irrigation Engineer"},{n:"Rajesh Kumar",r:"Climate Forecaster"},{n:"Dr. Emily Taylor",r:"Seed Specialist"}
  ];
  for (let i = 1; i <= 40; i++) {
    const e = rand(experts);
    db.experts.push({ id: i, name: `${e.n} ${String.fromCharCode(65+(i%26))}.`, role: e.r, rating: (rng(44,50)/10).toFixed(1), bio: `${rng(5,20)} years experience in agricultural consulting.`, status: i%3===0?"offline":"online", cost: rng(200,600), favorite: i%8===0 });
  }

  const posts = [
    "Bumper Basmati harvest! NPK balancing worked great.","Dairy cows post-vaccination, yield stable at 12L/day.",
    "Solar pump installed - zero electricity bills now!","Yellow spots on potato leaves - need copper spray advice.",
    "Direct selling to city gave 25% premium over mandi.","Mulching reduced watering frequency to half.",
    "Drip irrigation saved 40% water this season.","New variety maize showing excellent drought tolerance."
  ];
  for (let i = 1; i <= 100; i++) db.posts.push({ id: i, author: rand(["Ravi Patil","Meera Nair","Gurpreet Singh","Ketan Patel","Priya Sen","Vijay Rao","Sunita Devi","Arun Sharma"]), role: `Farmer Sector ${String.fromCharCode(65+(i%6))}`, text: `${rand(posts)} (Post ${i})`, likes: rng(10,180), commentsCount: rng(2,25), followed: i%4===0, liked: i%5===0, bookmarked: i%9===0 });

  const notifs = [
    {t:"weather",ti:"Heavy Rain Advisory",p:"High",d:"Expect 30mm+ rain tomorrow. Secure crops."},
    {t:"market",ti:"Rice Price Spike",p:"Medium",d:"Basmati up ₹150/qtl in local mandi."},
    {t:"ai",ti:"Crop Health Alert",p:"High",d:"Plot E NDVI dropped to 64%. Pest risk."},
    {t:"finance",ti:"Loan Due Alert",p:"High",d:"₹3,400 interest due July 25."},
    {t:"government",ti:"Subsidy Approved",p:"Medium",d:"Drip irrigation subsidy payout initiated."},
    {t:"community",ti:"Reply to Your Post",p:"Low",d:"Rajesh replied to your pest query."}
  ];
  for (let i = 1; i <= 50; i++) { const b = rand(notifs); db.notifications.push({ id: 100+i, type: b.t, title: b.ti, priority: b.p, desc: b.d, time: i<3?"10m ago":`${i*15}m ago`, read: i>5 }); }

  const statuses = ["Processing","Shipped","Delivered","Cancelled"];
  for (let i = 1; i <= 50; i++) { const p = db.products[i%db.products.length]; db.orders.push({ id: `ORD-980${i}`, productName: p.name, price: p.price, quantity: rng(1,5), status: i<=2?"Processing":i<=6?"Shipped":rand(statuses), date: dateOff(-(i%10)) }); }

  const animals = [
    {t:"Cow",b:"Gir Dairy",y:"12L/day",i:"fa-cow"},{t:"Buffalo",b:"Murrah",y:"14L/day",i:"fa-cow"},{t:"Goat",b:"Sirohi",y:"2L/day",i:"fa-goat"},{t:"Chicken",b:"Rhode Island Red",y:"1 egg/day",i:"fa-dove"},
    {t:"Cow",b:"Sahiwal",y:"10L/day",i:"fa-cow"},{t:"Goat",b:"Jamunapari",y:"3L/day",i:"fa-goat"}
  ];
  for (let i = 1; i <= 60; i++) { const a = rand(animals); db.livestock.push({ id: `LV-${i}`, name: `${a.t} #${i}`, type: a.t, breed: a.b, health: i%7===0?"Vaccination Due":"Healthy", yield: a.y, feed: `${rng(2,10)}kg/day`, vaccineDate: dateOff(i%2===0?-120:15), icon: a.i, age: `${rng(1,8)} years` }); }

  for (let i = 1; i <= 100; i++) db.suggestions.push({ id: i, title: rand(["Optimize Irrigation","NPK Adjustment","Pest Warning","Sell Window","Subsidy Filing"]), category: rand(["water","soil","pest","market","gov"]), text: `AI recommendation #${i}: Based on current field conditions.`, priority: i%4===0?"High":"Medium", date: dateOff(-(i%5)) });

  for (let i = 1; i <= 100; i++) db.events.push({ id: i, title: rand(["Harvest Schedule","Consultation Call","Loan Payment","Fungicide Spray","Community Meetup","Scheme Deadline","Vaccination Drive","Soil Sampling"]), date: dateOff((i-50)%30), time: `${rng(9,17)}:00`, type: rand(["harvest","expert","finance","task"]) });

  for (let i = 1; i <= 100; i++) db.chatMessages.push({ id: i, partner: rand(["AI Assistant","Dr. Arvind S.","Ananya Sen","Farmers Forum"]), sender: i%2===0?"user":"partner", text: i%2===0?`Query about ${rand(cropTypes)} cultivation.`:"Based on regional data, we suggest adjusting irrigation.", timestamp: dateOff(-(i%3)) });

  for (let i = 1; i <= 20; i++) db.jobs.push({ id: i, title: rand(["Tractor Operator","Agronomist","Harvester Crew","Solar Technician","Drip Installer","Farm Manager"]), pay: rand(["₹800/Day","₹2,500/Visit","₹600/Day","₹3,000 Flat","₹1,200/Day"]), duration: rand(["10 Days","Ongoing","4 Days","Seasonal"]), location: rand(["Pune","Haveli","Sector B","Shirur"]), contact: `+91 ${rng(1000000000,9999999999)}`, desc: "Agricultural work opportunity. Apply with farm credentials." });

  const courses = [
    {t:"Advanced Hydroponics",d:"4h 12 Lessons",r:"4.9",c:"tech"},{t:"Organic Soil Biology",d:"2.5h 8 Lessons",r:"4.8",c:"soil"},{t:"Dairy Cow Health",d:"5h 16 Lessons",r:"4.7",c:"livestock"},{t:"Mandi Markets & Export",d:"3h 10 Lessons",r:"4.6",c:"finance"},{t:"Drone Crop Surveys NDVI",d:"6h 18 Lessons",r:"4.9",c:"tech"},{t:"Irrigation Management",d:"4h 12 Lessons",r:"4.8",c:"water"},{t:"Organic Pest Control",d:"3h 9 Lessons",r:"4.7",c:"pest"}
  ];
  for (let i = 1; i <= 40; i++) { const c = rand(courses); db.courses.push({ id: i, title: `${c.t}${i > 7 ? ' - Module ' + Math.ceil(i/7) : ''}`, duration: c.d, rating: c.r, category: c.c, progress: i%3===0?"completed":i%2===0?"in-progress":"not-started", percent: i%3===0?100:i%2===0?50:0 }); }

  for (let i = 1; i <= 30; i++) db.documents.push({ id: i, title: rand(["SBI Agri Gold Loan","7/12 Land Record","Seed Purity Cert","NPK Invoice","PM-Kisan Acknowledge","Soil Health Card","Organic Cert","Crop Insurance Policy","Kisan Credit Card","Warehouse Receipt","Lease Agreement","Water Tax Receipt"]), type: rand(["Finance","Land Record","Certificate","Invoice","Government"]), date: dateOff(-i*12), size: `${(rng(102,920)/100).toFixed(1)} MB`, format: i%4===0?"JPG":"PDF" });

  // ========== NEW WATER & IRRIGATION DATA ==========
  const waterTypes = ["Borewell","Canal","River","Reservoir","Rainwater Harvesting","Pond","Well"];
  for (let i = 1; i <= 20; i++) {
    db.waterSources.push({
      id: `WS-${i}`, name: `${rand(waterTypes)} - Source ${i}`,
      type: rand(waterTypes), capacity: `${rng(50,500)} KL`,
      currentLevel: `${rng(30,95)}%`, status: i%4===0?"Low":i%8===0?"Critical":"Normal",
      location: `Sector ${String.fromCharCode(64+(i%8))}`, lastMaintenance: dateOff(-rng(5,90)),
      pumpCapacity: `${rng(1,10)} HP`, depth: `${rng(50,500)} ft`
    });
  }

  for (let i = 1; i <= 30; i++) {
    db.irrigationSchedules.push({
      id: `IS-${i}`, plotId: (i%30)+1, crop: rand(cropTypes),
      method: rand(["Drip","Sprinkler","Flood","Furrow","Rain Gun"]),
      duration: `${rng(30,180)} min`, frequency: rand(["Daily","Alternate Days","Weekly","Bi-weekly"]),
      nextWatering: dateOff(i%7), status: i%5===0?"Overdue":i%3===0?"Due Today":"Scheduled",
      waterRequired: `${rng(10,100)} L`, created: dateOff(-rng(1,30))
    });
  }

  // ========== FERTILIZER GUIDE ==========
  const fertGuide = [
    {c:"Rice",o:"Vermicompost 2t/ha",n:"NPK 120:60:40 kg/ha",s:"Basal + 2 splits",t:"Organic+Chemical",p:"₹4,500/ha"},
    {c:"Cotton",o:"Farmyard manure 5t/ha",n:"NPK 80:40:40 kg/ha",s:"Basal + top dressing",t:"Chemical",p:"₹3,800/ha"},
    {c:"Wheat",o:"Compost 2.5t/ha",n:"NPK 100:50:50 kg/ha",s:"Basal + 2 splits",t:"Organic+Chemical",p:"₹3,200/ha"},
    {c:"Maize",o:"Green manure",n:"NPK 90:45:45 kg/ha",s:"Basal + top dressing",t:"Chemical",p:"₹3,500/ha"},
    {c:"Sugarcane",o:"Press mud 10t/ha",n:"NPK 250:90:120 kg/ha",s:"3 splits",t:"Organic+Chemical",p:"₹8,000/ha"},
    {c:"Tomato",o:"Vermicompost 3t/ha",n:"NPK 100:50:50 kg/ha",s:"Weekly fertigation",t:"Drip",p:"₹5,000/ha"},
    {c:"Groundnut",o:"Gypsum 500kg/ha",n:"NPK 30:60:30 kg/ha",s:"Basal application",t:"Chemical",p:"₹2,800/ha"}
  ];
  for (let i = 1; i <= 30; i++) {
    const g = rand(fertGuide);
    db.fertilizerGuides.push({
      id: i, crop: g.c, organicOption: g.o, npkDose: g.n, schedule: g.s,
      type: g.t, costPerHa: g.p, recommendation: `Apply ${g.n} for optimal ${g.c} yield.`,
      brand: rand(brands), rating: (rng(40,50)/10).toFixed(1), source: "Krishi Vigyan Kendra"
    });
  }

  // ========== WORKERS & LABOUR ==========
  const workerCategories = ["Harvest Workers","Tractor Drivers","Machine Operators","Drone Operators","Livestock Workers","Irrigation Workers","Field Workers","Equipment Mechanics"];
  const categorySkills = {
    "Harvest Workers": ["Manual Harvesting","Crop Cutting","Sorting","Packing","Grading"],
    "Tractor Drivers": ["Tractor Operator","Ploughing","Tilling","Trailer Handling","Rotavator"],
    "Machine Operators": ["Harvester Operator","Thresher","Baler","Seed Drill","Combine Machine"],
    "Drone Operators": ["Drone Pilot","Spray Drone","Crop Mapping","Aerial Survey","DGCA Certified"],
    "Livestock Workers": ["Dairy Worker","Cattle Handling","Milking","Feeding","Animal Care"],
    "Irrigation Workers": ["Drip Setup","Sprinkler","Pump Operation","Pipe Fitting","Water Scheduling"],
    "Field Workers": ["Weeding","Sowing","Transplanting","Mulching","General Labor"],
    "Equipment Mechanics": ["Engine Repair","Hydraulics","Welding","Electrical","Diesel Mechanic"]
  };
  const workerFirst = ["Raju","Suresh","Mahesh","Ganesh","Sunil","Vijay","Amit","Deepak","Prakash","Ramesh","Siddharth","Nitin","Balaji","Kishor","Santosh","Dinesh","Ravindra","Ashok","Manoj","Pandurang"];
  const workerLast = ["Shinde","Patil","More","Jadhav","Pawar","Gaikwad","Kamble","Deshmukh","Salunke","Bhosale","Chavan","Kadam"];
  const workerLangs = ["Hindi","Marathi","Telugu","English","Kannada","Tamil"];
  const reviewComments = [
    "Very hardworking and punctual. Completed the harvest on time.",
    "Skilled operator, handled the machinery with great care.",
    "Reliable worker, would definitely hire again.",
    "Good attitude and knows the work well.",
    "Excellent job, my field looks perfect now.",
    "Professional and efficient. Highly recommended.",
    "Arrived on time and worked diligently all day.",
    "Great communication and quality work."
  ];
  for (let i = 1; i <= 120; i++) {
    const cat = workerCategories[i % workerCategories.length];
    const skillPool = categorySkills[cat];
    const skills = [rand(skillPool), rand(skillPool), rand(skillPool)].filter((v,j,a)=>a.indexOf(v)===j);
    const fullName = `${rand(workerFirst)} ${rand(workerLast)}`;
    const reviewCount = rng(4, 90);
    const rating = (rng(38,50)/10);
    const reviews = [];
    for (let r = 0; r < Math.min(3, reviewCount); r++) {
      reviews.push({ author: `${rand(workerFirst)} ${rand(workerLast).charAt(0)}.`, rating: rng(4,5), date: dateOff(-(r*15+rng(1,10))), comment: rand(reviewComments) });
    }
    const expYears = rng(1,22);
    const timeline = [
      { year: 2024 - Math.min(expYears,1), role: `Senior ${cat.replace(' Workers','').replace(' Drivers','').replace(' Operators','')}`, place: rand(["Green Valley Farms","Patil Agro","Krishna Cooperative"]) },
      { year: 2024 - Math.min(expYears,4), role: cat.replace(' Workers','').replace(' Drivers','').replace(' Operators',''), place: rand(["Sahyadri Estates","Deccan Fields","Godavari Farms"]) },
      { year: 2024 - expYears, role: "Field Assistant", place: rand(["Village Cooperative","Family Farm","Local Contractor"]) }
    ];
    db.workers.push({
      id: `W-${String(i).padStart(3,'0')}`, name: fullName,
      image: `https://i.pravatar.cc/160?img=${(i % 70) + 1}`,
      category: cat,
      age: rng(22,55), skills: skills,
      experience: `${expYears} years`, experienceYears: expYears,
      dailyWage: rng(350,1400), dailyWageLabel: `₹${rng(350,1400)}/day`,
      location: rand(["Pune","Haveli","Shirur","Baramati","Saswad","Daund","Junnar","Mulshi"]),
      distance: `${(rng(5,320)/10).toFixed(1)} km`, distanceKm: (rng(5,320)/10),
      rating: rating.toFixed(1), reviewsCount: reviewCount, reviews: reviews,
      available: i%4!==0, availabilityNote: i%4!==0 ? "Available Now" : rand(["Busy till "+dateOff(rng(2,6)),"On another job"]),
      phone: `+91 ${rng(70,99)}${rng(10000000,99999999)}`,
      languages: [rand(workerLangs), rand(workerLangs), rand(workerLangs)].filter((v,j,a)=>a.indexOf(v)===j),
      verified: i%3!==0, jobsCompleted: rng(12,240), completedProjects: rng(12,240),
      timeline: timeline
    });
  }

  // ========== EQUIPMENT RENTALS ==========
  const equipTypes = ["Tractor","Harvester","Drone","Sprayer","Plough","Rotavator","Leveller","Transplanter","Thresher","Pump"];
  for (let i = 1; i <= 25; i++) {
    db.equipmentRentals.push({
      id: `ER-${i}`, name: `${rand(["Mahindra","John Deere","New Holland","Kubota","Swaraj","Escorts"])} ${rand(equipTypes)}`,
      type: rand(equipTypes), dailyRate: `₹${rng(800,12000)}/day`,
      owner: rand(["Ramesh Kumar","Village Cooperative","Sharma Traders","Patil Agritech","Green Farm Services"]),
      location: rand(["Pune","Haveli","Shirur","Baramati"]), rating: (rng(38,50)/10).toFixed(1),
      available: i%5!==0, advanceBooking: `${rng(1,7)} days`, distance: `${rng(2,30)} km`,
      fuelType: rand(["Diesel","Petrol","Electric"]), year: rng(2018,2024),
      reviews: rng(5,80)
    });
  }

  // ========== SEED INVENTORY ==========
  const seedTypes = [
    {n:"Basmati Rice Pusa 1121",v:"Certified",p:"₹85/kg",y:"25 qtls/acre",d:"135 days"},{n:"Bt Cotton RCH-2",v:"Hybrid",p:"₹650/packet",y:"15 qtls/acre",d:"160 days"},
    {n:"Hybrid Maize NMH-851",v:"Hybrid",p:"₹320/kg",y:"35 qtls/acre",d:"110 days"},{n:"Wheat HD-2967",v:"Certified",p:"₹45/kg",y:"30 qtls/acre",d:"120 days"},
    {n:"Paddy DRR-50",v:"Certified",p:"₹55/kg",y:"28 qtls/acre",d:"125 days"},{n:"Mustard Pusa Jaikisan",v:"Hybrid",p:"₹280/kg",y:"18 qtls/acre",d:"140 days"},
    {n:"Groundnut TAG-24",v:"Certified",p:"₹90/kg",y:"22 qtls/acre",d:"130 days"},{n:"Sugarcane CO-86032",v:"Certified",p:"₹8/set",y:"80 tons/acre",d:"12 months"}
  ];
  for (let i = 1; i <= 20; i++) {
    const s = rand(seedTypes);
    db.seedInventory.push({
      id: i, name: s.n, variety: s.v, price: s.p, yield: s.y, duration: s.d,
      stock: `${rng(50,500)} kg`, dealer: rand(["Krishi Seed Centre","Bharat Beej Bhandar","Green Field Seeds","Pioneer Hybrids","Nuziveedu Seeds"]),
      treatment: rand(["Untreated","Fungicide Treated","Bio-fertilizer coated","Vermi-coated"]),
      sowingSeason: rand(["Kharif","Rabi","Zaid","All Season"]), rating: (rng(40,50)/10).toFixed(1)
    });
  }

  // ========== SOIL HEALTH ==========
  const soilTypes = ["Black Cotton","Red Sandy","Alluvial","Laterite","Clay Loam","Sandy Loam"];
  for (let i = 1; i <= 25; i++) {
    db.soilHealth.push({
      id: i, plotId: (i%30)+1, soilType: rand(soilTypes),
      pH: (rng(55,85)/10).toFixed(1), nitrogen: `${rng(30,80)} kg/ha`,
      phosphorus: `${rng(15,50)} kg/ha`, potassium: `${rng(40,100)} kg/ha`,
      organicCarbon: `${(rng(3,12)/10).toFixed(1)}%`, zinc: `${(rng(2,15)/10).toFixed(1)} ppm`,
      iron: `${(rng(20,80)/10).toFixed(1)} ppm`, testDate: dateOff(-rng(10,180)),
      healthScore: rng(55,95), recommendation: rand(["Apply lime to reduce acidity","Add organic matter","Reduce nitrogen input","Apply zinc sulfate","Maintain current practice"])
    });
  }

  // ========== MARKET PRICES ==========
  const mandis = ["Haveli Mandi","Pune Market","Shirur APMC","Baramati","Daund","Loni"];
  const commodities = [
    {n:"Basmati Rice",u:"₹/qtl",p:2500},{n:"Cotton Bt",u:"₹/qtl",p:6700},{n:"Maize Hybrid",u:"₹/qtl",p:2100},{n:"Wheat",u:"₹/qtl",p:2400},
    {n:"Sugarcane",u:"₹/ton",p:3400},{n:"Tomato",u:"₹/qtl",p:1200},{n:"Onion",u:"₹/qtl",p:1800},{n:"Potato",u:"₹/qtl",p:1400},
    {n:"Soybean",u:"₹/qtl",p:4200},{n:"Mustard",u:"₹/qtl",p:5600},{n:"Groundnut",u:"₹/qtl",p:5200},{n:"Chilli",u:"₹/kg",p:85}
  ];
  for (let i = 1; i <= 40; i++) {
    const c = rand(commodities);
    const price = c.p * rng(85,115)/100;
    db.marketPrices.push({
      id: i, commodity: c.n, unit: c.u, price: Math.round(price),
      change: `${(rng(-5,8)/10).toFixed(1)}%`, trend: rng(0,1)?"up":"down",
      mandi: rand(mandis), date: dateOff(0), msp: c.p,
      demand: rand(["High","Medium","Low"]), arrival: `${rng(500,5000)} qtls`
    });
  }

  // ========== CROP DISEASES ==========
  const diseases = [
    {c:"Rice",d:"Blast Disease",s:"Leaf spots, neck rot",o:"Neem oil + Tricyclazole",p:"High",t:"Fungal"},{c:"Cotton",d:"Bollworm Attack",s:"Boll damage, drooping",o:"Emonectin benzoate spray",p:"High",t:"Pest"},
    {c:"Tomato",d:"Late Blight",s:"Leaf dark spots, fruit rot",o:"Copper oxychloride",p:"Medium",t:"Fungal"},{c:"Wheat",d:"Rust Disease",s:"Orange pustules on leaves",o:"Propiconazole spray",p:"Medium",t:"Fungal"},
    {c:"Maize",d:"Fall Armyworm",s:"Leaf feeding, whorl damage",o:"Spinosad + neem",p:"High",t:"Pest"},{c:"Chilli",d:"Leaf Curl Virus",s:"Leaf curling, stunting",o:"Imidacloprid + virus resistant seeds",p:"Medium",t:"Viral"},
    {c:"Groundnut",d:"Tikka Disease",s:"Leaf spots, defoliation",o:"Carbendazim spray",p:"Low",t:"Fungal"},{c:"Onion",d:"Purple Blotch",s:"Purple spots on leaves",o:"Mancozeb spray",p:"Medium",t:"Fungal"}
  ];
  for (let i = 1; i <= 25; i++) {
    const d = rand(diseases);
    db.cropDiseases.push({
      id: i, crop: d.c, disease: d.d, symptoms: d.s, organicSolution: d.o,
      chemicalSolution: d.o, severity: d.p, type: d.t, season: rand(["Kharif","Rabi","Zaid","All Year"]),
      prevention: rand(["Crop rotation","Resistant varieties","Proper spacing","Clean seed","Field sanitation"]),
      image: `https://source.unsplash.com/100x100/?plant-disease&${i}`
    });
  }

  // ========== GOVERNMENT SCHEMES (25+ realistic schemes) ==========
  db.govSchemes = [
    {id:1,name:"PM-KISAN Samman Nidhi",category:"Central",type:"Income Support",description:"Direct income support of ₹6,000 per year to all small and marginal farmers, transferred in three equal installments directly to bank accounts.",benefit:"₹6,000/year",eligibility:"All small & marginal farmer families with up to 2 hectares of land",documents:"AADHAR Card, Land Records, Bank Account, Passport Photo, Declaration Form",deadline:dateOff(45),applicants:11000000,status:"Open",applyMode:"Online at pmkisan.gov.in or nearest CSC centre",objective:"Provide financial support to supplement farmers' needs for agricultural inputs",contact:"District Agriculture Officer, Toll-free: 1800-180-1551",faq:"Q: Can tenant farmers apply? A: Yes, with land lease agreement. Q: When is the next installment? A: Usually April, August, December."},
    {id:2,name:"PM-KUSUM Solar Pump Scheme",category:"Central",type:"Subsidy",description:"Installation of solar pumps and grid-connected solar power plants for farmers. 60% central subsidy + 30% state subsidy = only 10% farmer contribution.",benefit:"60% subsidy (up to ₹45,000)",eligibility:"All farmers with irrigation facilities and grid connectivity",documents:"AADHAR Card, Land Records, Bank Account, Electricity Bill, Solar Dealer Quotation",deadline:dateOff(60),applicants:1890000,status:"Open",applyMode:"Online through state DISCOM portal",objective:"Promote solar energy in agriculture, reduce diesel dependency",contact:"State Renewable Energy Department",faq:"Q: What size pump? A: Up to 7.5 HP. Q: Can I sell excess power? A: Yes, at ₹3-5/unit."},
    {id:3,name:"Soil Health Card Scheme",category:"Central",type:"Soil Testing",description:"Free soil testing for all farmers with personalized recommendations on nutrient doses, fertilizer applications, and soil amendments.",benefit:"Free soil testing + recommendations",eligibility:"All farmers owning agricultural land",documents:"AADHAR Card, Land Records, Survey Number Details",deadline:dateOff(180),applicants:52000000,status:"Open",applyMode:"Visit nearest agriculture department or Krishi Vigyan Kendra",objective:"Improve soil productivity through balanced nutrient management",contact:"District Soil Testing Laboratory, Toll-free: 1800-180-1551",faq:"Q: How often? A: Every 2-3 years. Q: What is tested? A: pH, NPK, micronutrients, organic carbon."},
    {id:4,name:"Drip Irrigation Subsidy (PMKSY)",category:"Central",type:"Subsidy",description:"55% subsidy on installation of drip and sprinkler irrigation systems for water conservation. Available for all horticultural and row crops.",benefit:"55% subsidy (up to ₹12,500/acre)",eligibility:"Small & marginal farmers with 0.5-5 acres",documents:"AADHAR Card, Land Records, Bank Account, Quotation from empaneled vendor",deadline:dateOff(90),applicants:2450000,status:"Open",applyMode:"Through District Agriculture Department or online PMKSY portal",objective:"Promote micro-irrigation to save water and increase crop yield",contact:"District Horticulture Officer",faq:"Q: Can I install on existing farm? A: Yes. Q: What crops covered? A: All horticultural crops."},
    {id:5,name:"Kisan Credit Card (KCC)",category:"Central",type:"Loan",description:"Easy agricultural loans up to ₹3 lakh at 4% interest rate with no collateral. Covers crop production, post-harvest, and maintenance expenses.",benefit:"Loan up to ₹3 lakh at 4% interest",eligibility:"All farmers, sharecroppers, tenant farmers, and agri-entrepreneurs",documents:"AADHAR Card, Land Records, Bank Account, Passport Photo, Proof of farming activity",deadline:dateOff(30),applicants:75000000,status:"Open",applyMode:"Apply at any nationalized bank or cooperative bank",objective:"Provide timely and adequate credit to farmers for agricultural needs",contact:"Lead Bank Manager, NABARD Office",faq:"Q: What is the repayment period? A: Up to 3 years. Q: Insurance included? A: Optional personal accident insurance."},
    {id:6,name:"PM Fasal Bima Yojana (PMFBY)",category:"Central",type:"Insurance",description:"Comprehensive crop insurance at a nominal premium of 2% for Kharif crops, 1.5% for Rabi crops, and 5% for horticultural/commercial crops.",benefit:"Insurance coverage at 2% premium only",eligibility:"All farmers growing notified crops in notified areas",documents:"AADHAR Card, Land Records, Bank Account, Crop Sown Certificate",deadline:dateOff(20),applicants:38000000,status:"Open",applyMode:"Through bank branches, CSC centres, or insurance company agents",objective:"Protect farmers against crop loss due to natural calamities, pests, and diseases",contact:"Insurance Company Toll-free, District Agriculture Officer",faq:"Q: What is covered? A: Drought, flood, hail, pest, cyclone. Q: How is claim calculated? A: Based on yield assessment."},
    {id:7,name:"MSP Procurement Scheme",category:"Central",type:"Procurement",description:"Government procurement of 23 notified crops at Minimum Support Price. Assured market and price protection for farmers across all states.",benefit:"MSP + procurement bonus",eligibility:"All farmers growing notified crops (wheat, rice, cotton, pulses, oilseeds, etc.)",documents:"AADHAR Card, Land Records, Bank Account, Harvest Declaration",deadline:dateOff(15),applicants:25000000,status:"Open",applyMode:"Register at nearest government procurement centre or mandi",objective:"Ensure farmers receive remunerative prices and food security",contact:"NAFED Office, State Food & Civil Supplies Department",faq:"Q: Which crops? A: 23 crops including wheat, rice, cotton, pulses. Q: When is procurement? A: Kharif Oct-Feb, Rabi Apr-Jun."},
    {id:8,name:"Rythu Bandhu Scheme (Telangana)",category:"State",type:"Income Support",description:"Investment support of ₹10,000 per acre per year for all farmers in Telangana. Direct bank transfer for crop investment.",benefit:"₹10,000/acre/year",eligibility:"All farmers in Telangana with agricultural land",documents:"AADHAR Card, Land Records, Bank Account, Dharani Passbook",deadline:dateOff(30),applicants:5200000,status:"Open",applyMode:"Through Rythu Bharosa Kendras (farmer assistance centres)",objective:"Provide upfront investment support to farmers for crop production",contact:"Rythu Bharosa Kendra, District Agriculture Officer",faq:"Q: Is it per person or per acre? A: Per acre up to 5 acres. Q: Can tenant farmers apply? A: Yes, with lease agreement."},
    {id:9,name:"Free Urea Distribution for Corn Farmers",category:"Central",type:"Subsidy",description:"Free 50kg bag of urea per acre for corn farmers registered under the National Food Security Mission. Additional 25kg DAP at 50% subsidy.",benefit:"Free 50kg urea/acre + 50% DAP subsidy",eligibility:"Corn farmers registered with NFSM, land up to 5 acres",documents:"AADHAR Card, Land Records, Corn crop registration proof, Bank Account",deadline:dateOff(25),applicants:890000,status:"Open",applyMode:"Register at District Agriculture Office or online NFSM portal",objective:"Boost maize production through subsidized fertilizer distribution",contact:"NFSM District Coordinator, Agriculture Department",faq:"Q: How to register? A: Through local agriculture officer. Q: Which varieties? A: All maize hybrids and composites."},
    {id:10,name:"National Agriculture Market (e-NAM)",category:"Central",type:"Market",description:"Unified national digital market platform connecting 1,000+ mandis. Farmers can sell produce online and get better prices through competitive bidding.",benefit:"Better price discovery, single license",eligibility:"All farmers, traders, and FPOs registered on e-NAM platform",documents:"AADHAR Card, Bank Account, Mobile Number, Quality Certificate",deadline:dateOff(365),applicants:17000000,status:"Open",applyMode:"Register at nearest e-NAM mandi or online at enam.gov.in",objective:"Create a unified national market for agricultural commodities",contact:"e-NAM Help Desk, Toll-free: 1800-270-0224",faq:"Q: How do I sell? A: Take produce to e-NAM mandi, get quality tested, bid online. Q: Payment? A: Direct bank transfer within 24h."},
    {id:11,name:"Paramparagat Krishi Vikas Yojana (PKVY)",category:"Central",type:"Organic Farming",description:"Promotion of organic farming through clusters. ₹50,000 per hectare for 3 years for certification, inputs, and marketing support.",benefit:"₹50,000/ha for 3 years",eligibility:"Farmers willing to adopt organic farming in clusters of 50+ acres",documents:"AADHAR Card, Land Records, Organic Conversion Plan, Cluster Formation Document",deadline:dateOff(60),applicants:640000,status:"Open",applyMode:"Through District Agriculture Department or online portal",objective:"Promote organic farming and certification for export markets",contact:"PKVY Nodal Officer, State Agriculture Department",faq:"Q: What is the cluster size? A: Minimum 50 acres. Q: Certification included? A: Yes, third-party organic certification."},
    {id:12,name:"Pradhan Mantri Krishi Sinchayee Yojana (PMKSY)",category:"Central",type:"Irrigation",description:"'Har Khet Ko Paani' - Comprehensive irrigation scheme covering micro-irrigation, watershed development, and water harvesting structures.",benefit:"Up to 55% subsidy on irrigation",eligibility:"All farmers, especially in rainfed areas",documents:"AADHAR Card, Land Records, Irrigation Plan, Bank Account",deadline:dateOff(120),applicants:3200000,status:"Open",applyMode:"Through District Agriculture Department",objective:"Enhance water use efficiency and expand irrigated area",contact:"PMKSY District Coordinator",faq:"Q: What structures covered? A: Drip, sprinkler, check dams, farm ponds. Q: Subsidy percentage? A: 55% for small farmers."},
    {id:13,name:"Pradhan Mantri Kisan Maandhan Yojana",category:"Central",type:"Pension",description:"Old age pension scheme for farmers. Monthly contribution of ₹55-200 for guaranteed pension of ₹3,000/month after 60 years.",benefit:"₹3,000/month pension after 60",eligibility:"Small & marginal farmers aged 18-40 years with up to 2 hectares",documents:"AADHAR Card, Land Records, Bank Account, Nominee Details",deadline:dateOff(365),applicants:4200000,status:"Open",applyMode:"Apply at nearest CSC centre or through PMKMY portal",objective:"Provide social security to small farmers in their old age",contact:"CSC Centre, PMKMY Helpline",faq:"Q: How much to contribute? A: ₹55-200/month based on age. Q: When does pension start? A: After age 60."},
    {id:14,name:"Rashtriya Krishi Vikas Yojana (RKVY)",category:"Central",type:"Development",description:"State-specific agricultural development projects. Funds for infrastructure, mechanization, value addition, and farmer training programs.",benefit:"Project-based funding up to ₹10 crore",eligibility:"State governments, FPOs, agri-entrepreneurs",documents:"Project Proposal, DPR, Land Documents, Registration Certificate",deadline:dateOff(90),applicants:5800,status:"Open",applyMode:"Through State Agriculture Department",objective:"Make agriculture a profitable business through innovation and infrastructure",contact:"RKVY State Nodal Officer",faq:"Q: Who can apply? A: States, FPOs, startups. Q: What is funded? A: Processing units, cold storage, mechanization."},
    {id:15,name:"Seed Subsidy Scheme",category:"Central",type:"Subsidy",description:"50% subsidy on certified seeds for all Kharif and Rabi crops. Includes hybrid seeds of rice, wheat, maize, pulses, and oilseeds.",benefit:"50% subsidy on seed cost",eligibility:"All farmers, priority to SC/ST and women farmers",documents:"AADHAR Card, Land Records, Bank Account, Seed Requirement Form",deadline:dateOff(20),applicants:7800000,status:"Open",applyMode:"Through District Agriculture Department or seed distribution centres",objective:"Increase use of quality certified seeds for higher productivity",contact:"District Seed Officer",faq:"Q: How much seed? A: Up to 5 acres per farmer. Q: Which varieties? A: Certified/hybrid varieties of major crops."},
    {id:16,name:"Farm Machinery Bank Subsidy",category:"Central",type:"Subsidy",description:"50% subsidy on establishment of custom hiring centres for farm machinery. Includes tractors, harvesters, threshers, and precision equipment.",benefit:"50% subsidy up to ₹10 lakh",eligibility:"FPOs, farmer groups, rural entrepreneurs aged 18-45",documents:"Project Report, Land Documents, Group Registration, Bank Account",deadline:dateOff(60),applicants:125000,status:"Open",applyMode:"Through District Agriculture Office or SMAM portal",objective:"Make farm machinery accessible to small farmers through custom hiring",contact:"SMAM Nodal Officer",faq:"Q: What machinery? A: Tractors, combines, sprayers, planters. Q: Who can operate? A: Trained operators from the group."},
    {id:17,name:"Pradhan Mantri Fasal Bima Yojana (PMFBY) - Rabi 2026",category:"Central",type:"Insurance",description:"Rabi season crop insurance at 1.5% premium. Coverage for wheat, mustard, gram, peas, and other rabi crops against frost, hail, and drought.",benefit:"1.5% premium insurance",eligibility:"All farmers growing notified rabi crops in notified areas",documents:"AADHAR Card, Land Records, Bank Account, Rabi Sown Certificate",deadline:dateOff(10),applicants:22000000,status:"Open",applyMode:"Through bank branches or insurance company agents",objective:"Protect rabi crop farmers against seasonal risks and climate events",contact:"PMFBY District Coordinator",faq:"Q: Cutoff date? A: Usually Dec 31 for Rabi. Q: How is loss assessed? A: CCE (Crop Cutting Experiments)."},
    {id:18,name:"Crop Insurance for Horticulture (MSP-based)",category:"Central",type:"Insurance",description:"Special insurance for horticultural crops including mango, banana, citrus, vegetables, and spices at 5% premium with MSP-linked coverage.",benefit:"5% premium, MSP-based coverage",eligibility:"All horticulture farmers",documents:"AADHAR Card, Land Records, Horticulture Registration, Bank Account",deadline:dateOff(15),applicants:650000,status:"Open",applyMode:"Through District Horticulture Department",objective:"Protect high-value horticulture crops with adequate insurance cover",contact:"District Horticulture Officer",faq:"Q: Which crops covered? A: All major horticulture crops. Q: Sum insured? A: Based on MSP or market value."},
    {id:19,name:"Kisan Rail & Kisan Ship Scheme",category:"Central",type:"Logistics",description:"Special train and ship services for transportation of perishable agricultural produce. 50% transportation subsidy for farmers and FPOs.",benefit:"50% transport subsidy",eligibility:"Farmers, FPOs, cooperatives transporting perishable agri-produce",documents:"Registration on Kisan Rail portal, Product Details, Quantity Certificate",deadline:dateOff(30),applicants:32000,status:"Open",applyMode:"Book online through Kisan Rail portal or IRCTC",objective:"Reduce post-harvest losses and ensure timely market access",contact:"Indian Railways Parcel Office",faq:"Q: What products? A: Fruits, vegetables, dairy, meat, fish. Q: Minimum quantity? A: No minimum."},
    {id:20,name:"Water Management Scheme (Watershed Development)",category:"Central",type:"Water",description:"Integrated watershed development for rainfed areas. Includes check dams, farm ponds, contour bunding, and recharge structures.",benefit:"Up to 90% project cost covered",eligibility:"Village communities, farmer groups in watershed areas",documents:"Community Resolution, Land Documents, Watershed Plan, Bank Account",deadline:dateOff(120),applicants:45000,status:"Open",applyMode:"Through District Watershed Cell",objective:"Conserve soil and water through watershed management in rainfed areas",contact:"Project Director, Watershed Cell",faq:"Q: What is the duration? A: 4-5 years. Q: Who implements? A: Village Watershed Committee with technical support."},
    {id:21,name:"Goat & Sheep Rearing Subsidy",category:"Central",type:"Subsidy",description:"50% subsidy for purchase of goats/sheep units (20+2 or 50+5 units). Includes shelter, feed, and veterinary care for small ruminants.",benefit:"50% subsidy (up to ₹1.5 lakh)",eligibility:"Small & marginal farmers, landless laborers, women farmers",documents:"AADHAR Card, Bank Account, Land Records (if applicable), Animal Shed Plan",deadline:dateOff(45),applicants:280000,status:"Open",applyMode:"Through District Animal Husbandry Department",objective:"Promote small ruminant rearing for livelihood diversification",contact:"District Animal Husbandry Officer",faq:"Q: What is the unit size? A: 20 female + 2 male goats. Q: Training provided? A: Yes, 7-day training included."},
    {id:22,name:"Dairy Development & Milk Production Scheme",category:"Central",type:"Livestock",description:"Subsidy for purchase of dairy animals (2-10 cows/buffaloes), milking machines, bulk milk coolers, and dairy infrastructure.",benefit:"33-50% subsidy on dairy units",eligibility:"All farmers, dairy cooperatives, FPOs with dairy activity",documents:"AADHAR Card, Bank Account, Animal Health Certificate, Dairy Plan",deadline:dateOff(60),applicants:560000,status:"Open",applyMode:"Through District Animal Husbandry or dairy cooperative",objective:"Increase milk production through improved dairy animal husbandry",contact:"District Dairy Development Officer",faq:"Q: How many animals? A: Minimum 2, maximum 10. Q: What breeds? A: Gir, Sahiwal, Murrah, Jaffarabadi."},
    {id:23,name:"Machinery Subsidy for Women Farmers",category:"Central",type:"Subsidy",description:"70% subsidy for women farmers on purchase of small farm machinery and tools - power tillers, weeder, sprayers, seed drills, and harvesters.",benefit:"70% subsidy (up to ₹80,000)",eligibility:"Women farmers with minimum 0.5 acre land",documents:"AADHAR Card, Land Records (joint name preferred), Bank Account, Quotation",deadline:dateOff(30),applicants:180000,status:"Open",applyMode:"Through District Agriculture Department - Women Cell",objective:"Empower women farmers through farm mechanization and drudgery reduction",contact:"Women Agriculture Officer",faq:"Q: What machinery covered? A: Power tillers, weeders, sprayers, seed drills. Q: Is training provided? A: Yes, free training."},
    {id:24,name:"National Livestock Mission - Poultry Scheme",category:"Central",type:"Livestock",description:"Backyard poultry development with 50% subsidy on desi chicken units (50+5 birds). Includes shelter, feed, vaccination, and training.",benefit:"50% subsidy on poultry units",eligibility:"Rural farmers, landless laborers, SHGs, women farmers",documents:"AADHAR Card, Bank Account, Viability Certificate from vet",deadline:dateOff(30),applicants:490000,status:"Open",applyMode:"Through District Animal Husbandry Department",objective:"Promote backyard poultry for income and nutrition security",contact:"District Poultry Officer",faq:"Q: Which breed? A: Native breeds like Kadaknath, Aseel, Vanaraja. Q: Housing required? A: Minimum 100 sq ft shed."},
    {id:25,name:"BEE Solar Agriculture Pump Scheme",category:"Central",type:"Energy",description:"Energy-efficient solar pump sets with BEE star rating. 30% subsidy + 30% state subsidy + low-interest loan for balance.",benefit:"60% total subsidy on solar pump",eligibility:"All farmers with grid-connected agriculture connection",documents:"AADHAR Card, Land Records, Electricity Connection Proof, Bank Account",deadline:dateOff(60),applicants:420000,status:"Open",applyMode:"Through DISCOM or empaneled solar vendor",objective:"Promote energy-efficient solar water pumping for irrigation",contact:"BEE Regional Office, DISCOM Office",faq:"Q: What HP pumps covered? A: 1-10 HP. Q: Warranty? A: 5 years for pump, 25 years for solar panel."},
    {id:26,name:"Sub-Mission on Agricultural Mechanization (SMAM)",category:"Central",type:"Mechanization",description:"50-60% subsidy on purchase of agricultural machinery including tractors, power tillers, combined harvesters, and precision farming equipment.",benefit:"50-60% subsidy (up to ₹12 lakh)",eligibility:"Small & marginal farmers, FPOs, custom hiring centres",documents:"AADHAR Card, Land Records, Bank Account, Machine Quotation, Farmer ID",deadline:dateOff(45),applicants:1400000,status:"Open",applyMode:"Through online SMAM portal or District Agriculture Office",objective:"Enhance farm mechanization among small and marginal farmers",contact:"SMAM District Nodal Officer",faq:"Q: What is the subsidy percentage? A: 50% for general, 60% for SC/ST/women. Q: Is second-hand covered? A: No, only new machinery."},
    {id:27,name:"Fisheries & Aquaculture Infrastructure Fund",category:"Central",type:"Subsidy",description:"Financial support for pond construction, fish seed rearing, cage culture, and ornamental fisheries. 40-60% subsidy for aquaculture development.",benefit:"40-60% subsidy (up to ₹5 lakh)",eligibility:"Farmers, SHGs, FPOs, entrepreneurs interested in fisheries",documents:"AADHAR Card, Land/Pond Documents, Bank Account, Aquaculture Plan",deadline:dateOff(60),applicants:175000,status:"Open",applyMode:"Through District Fisheries Department",objective:"Increase fish production through scientific aquaculture practices",contact:"District Fisheries Development Officer",faq:"Q: What size pond? A: Minimum 0.1 ha. Q: What species? A: Rohu, Catla, Tilapia, Pangasius."}
  ];

  // Extend schemes to 50+ with generated state/central variations
  const schemeStates = ["Maharashtra","Karnataka","Punjab","Gujarat","Tamil Nadu","Rajasthan","Bihar","Odisha","Kerala","Assam"];
  const schemeTypes = ["Subsidy","Loan","Insurance","Income Support","Irrigation","Market","Organic Farming","Machinery"];
  const schemeNames = ["Krishi Yantra Subsidy","Micro-Irrigation Grant","Farm Mechanization Aid","Horticulture Mission","Dairy Development Fund","Fisheries Support Scheme","Beekeeping Promotion","Seed Village Programme","Warehouse Construction Aid","Agri Startup Grant"];
  for (let i = db.govSchemes.length + 1; i <= 55; i++) {
    const st = rand(schemeStates); const tp = rand(schemeTypes);
    db.govSchemes.push({
      id: i, name: `${rand(schemeNames)} (${st})`, category: i % 2 === 0 ? "State" : "Central", type: tp,
      description: `${tp} scheme providing structured support to farmers in ${st} for improving productivity, income and sustainability.`,
      benefit: rand(["50% subsidy", "₹25,000 grant", "4% interest loan", "₹10,000/acre", "Free equipment"]),
      eligibility: "Registered farmers with valid land records", documents: "AADHAR Card, Land Records, Bank Account",
      deadline: dateOff(rng(15, 180)), applicants: rng(50000, 5000000), status: i % 9 === 0 ? "Closing Soon" : "Open",
      applyMode: "Apply online or at District Agriculture Office", objective: `Support ${tp.toLowerCase()} for farmers in ${st}.`,
      contact: "District Agriculture Officer, Toll-free: 1800-180-1551",
      faq: "Q: Who can apply? A: All eligible registered farmers. Q: Processing time? A: 15-30 days."
    });
  }

  // ========== WEATHER DATA (90 days) ==========
  for (let i = 0; i < 90; i++) {
    const d = new Date(); d.setDate(d.getDate() + i - 30);
    db.weatherData.push({
      date: d.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' }),
      temp: { max: rng(28,38), min: rng(18,26) },
      humidity: `${rng(50,85)}%`, rainfall: rng(0,40),
      windSpeed: `${rng(5,25)} km/h`, condition: rand(["Sunny","Partly Cloudy","Cloudy","Light Rain","Heavy Rain","Thunderstorm","Clear"]),
      uvIndex: rng(3,9), sunrise: "6:12 AM", sunset: "6:48 PM",
      icon: rand(["fa-sun","fa-cloud-sun","fa-cloud","fa-cloud-rain","fa-cloud-showers-heavy","fa-bolt","fa-smog"])
    });
  }

  // ========== EXPANDED NEWS (40+ articles with full content) ==========
  db.newsArticles = [
    {id:1,headline:"India's Basmati Export Breaks Record, Prices Surge 22%",category:"Export",source:"AgriMarket Pulse",summary:"India exported 4.6 million tonnes of basmati rice worth ₹48,000 crore in 2025-26, setting a new record driven by demand from Middle East, USA, and Europe.",full:"India's basmati rice exports have reached an all-time high of 4.6 million tonnes, valued at approximately ₹48,000 crore. The surge is driven by strong demand from traditional markets in the Middle East and new markets in Europe and America. The government's focus on quality certification and GI tagging has helped Indian basmati command premium prices. Experts predict continued growth as global demand for premium rice varieties increases.",image:"fa-plant",related:[2,5,10],bookmarked:false,date:dateOff(-1),author:"Priya Sharma",readTime:"4 min read"},
    {id:2,headline:"Early Monsoon Forecast: IMD Predicts Above-Normal Rainfall",category:"Weather",source:"IMD",summary:"The India Meteorological Department predicts above-normal monsoon rainfall at 106% of LPA, bringing relief to farmers ahead of the Kharif sowing season.",full:"The India Meteorological Department (IMD) has released its long-range forecast for the 2026 southwest monsoon, predicting above-normal rainfall at 106% of the Long Period Average (LPA). This is excellent news for the Kharif crop season, with normal or above-normal rainfall expected across most parts of the country except some pockets in the northeast. Farmers are advised to prepare for early sowing with adequate seed and fertilizer arrangements.",image:"fa-cloud-rain",related:[1,3,7],bookmarked:false,date:dateOff(-2),author:"Dr. S. Kumar",readTime:"3 min read"},
    {id:3,headline:"New Pest-Resistant Cotton Variety Released by CICR",category:"Research",source:"ICAR",summary:"The Central Institute for Cotton Research has developed a new pest-resistant cotton variety that reduces pesticide use by 40% while increasing yield by 15%.",full:"CICR Nagpur has released a breakthrough cotton variety, 'CICR-Cot-2026', which shows remarkable resistance to major cotton pests including bollworm, jassids, and whitefly. Field trials across 12 states showed 40% reduction in pesticide requirements and 15% higher yields compared to conventional varieties. The variety is suitable for both rainfed and irrigated conditions and is expected to significantly reduce farmer input costs.",image:"fa-seedling",related:[1,5,8],bookmarked:false,date:dateOff(-3),author:"Dr. Arvind Patel",readTime:"5 min read"},
    {id:4,headline:"MSP Hiked for Kharif Crops 2026 - Largest Increase in Decade",category:"Agriculture",source:"PIB",summary:"Government announces 8-12% MSP increase for all Kharif crops, with paddy MSP rising to ₹2,300/qtl and cotton to ₹7,100/qtl - highest ever.",full:"In a major boost for farmers ahead of the Kharif season, the Cabinet Committee on Economic Affairs has approved the highest-ever MSP hike for all notified Kharif crops. Paddy (common) MSP increased to ₹2,300 per quintal, cotton (medium staple) to ₹7,100, maize to ₹2,100, and groundnut to ₹5,700 per quintal. The government assured that procurement will continue at these enhanced prices through NAFED and state agencies.",image:"fa-chart-line",related:[4,7,10],bookmarked:false,date:dateOff(-4),author:"Government of India",readTime:"3 min read"},
    {id:5,headline:"Drone Technology Revolutionizing Indian Agriculture",category:"Technology",source:"Agritech Today",summary:"Over 10,000 farmers have adopted drone technology for crop monitoring, pesticide spraying, and NDVI analysis, with 60% government subsidy available.",full:"Drone technology is rapidly transforming Indian agriculture, with over 10,000 farmers now using drones for various agricultural operations. The 'Namami Drone Didi' scheme has trained 3,000 women as drone pilots. Drones are being used for precision pesticide spraying, crop health monitoring through NDVI sensors, and even for fish feed dispersal in aquaculture. The government provides 60% subsidy on drone purchases through the SMAM scheme.",image:"fa-helicopter",related:[1,3,8],bookmarked:false,date:dateOff(-5),author:"Rajesh Kumar",readTime:"4 min read"},
    {id:6,headline:"Dairy Sector Growth: India Becomes Largest Milk Producer",category:"Livestock",source:"NDDB",summary:"India's milk production reaches 230 million tonnes, becoming the world's largest dairy producer with a growth rate of 6.2% annually.",full:"India has cemented its position as the world's largest milk producer with annual production reaching 230 million tonnes. The dairy sector is growing at 6.2% annually, driven by improved breed programs, better feed management, and supportive government schemes. The 'Rashtriya Gokul Mission' has contributed significantly to genetic improvement of indigenous breeds. The cooperative model, particularly Amul, continues to serve as a benchmark for dairy development.",image:"fa-cow",related:[2,4,7],bookmarked:false,date:dateOff(-6),author:"Dairy Board Report",readTime:"4 min read"},
    {id:7,headline:"Natural Farming - 15 Lakh Farmers Adopt Zero-Budget Method",category:"Agriculture",source:"Krishi Vigyan",summary:"The government's push for natural farming sees 15 lakh farmers adopting zero-budget natural farming across 8 lakh hectares with promising results.",full:"The 'Bharatiya Prakritik Krishi Paddhati' programme has seen remarkable adoption with 15 lakh farmers transitioning to zero-budget natural farming across 8 lakh hectares. Farmers report 25-30% reduction in input costs and 10-15% premium prices for naturally grown produce. States like Andhra Pradesh, Gujarat, and Kerala are leading the adoption. The government has set a target of bringing 20 lakh hectares under natural farming by 2027.",image:"fa-leaf",related:[1,4,10],bookmarked:false,date:dateOff(-7),author:"Dr. Meera Deshmukh",readTime:"3 min read"},
    {id:8,headline:"Solar Pump Scheme KUSUM Crosses 3 Lakh Installations",category:"Government",source:"MNRE",summary:"Over 3 lakh solar pumps installed under PM-KUSUM scheme, saving farmers ₹2,500 crore annually in electricity costs and reducing carbon emissions.",full:"The PM-KUSUM scheme has achieved a milestone with over 3 lakh solar pumps installed across India. Farmers are saving an average of ₹8,000-12,000 per year on electricity bills, with total savings estimated at ₹2,500 crore annually. The scheme has also contributed to carbon emission reduction of 1.2 million tonnes per year. The government has extended the scheme with a target of 20 lakh solar pumps by 2028.",image:"fa-solar-panel",related:[2,5,10],bookmarked:false,date:dateOff(-8),author:"MNRE Report",readTime:"3 min read"},
    {id:9,headline:"Mandi Prices: Onion Touches ₹3,500/qtl, Government Steps In",category:"Markets",source:"AgriMarket Pulse",summary:"Onion prices have surged to ₹3,500 per quintal due to supply shortages. Government releases 2 lakh tonnes from buffer stock to control prices.",full:"Onion prices have touched ₹3,500 per quintal in major mandis across the country, driven by supply shortages following unseasonal rains in key growing regions of Maharashtra and Karnataka. In response, the government has released 2 lakh tonnes of onions from the buffer stock. Farmers are advised to take advantage of the high prices while consumers may see some relief in the coming weeks. The government is also facilitating imports to bridge the supply gap.",image:"fa-onion",related:[1,4,6],bookmarked:false,date:dateOff(-9),author:"Market Desk",readTime:"3 min read"},
    {id:10,headline:"Organic Fertilizer Subsidy Increased to 60%",category:"Government",source:"PIB",summary:"Government raises subsidy on organic fertilizers from 50% to 60% under PKVY scheme. Bio-fertilizers and vermicompost to become more affordable.",full:"To promote sustainable agriculture, the government has increased the subsidy on organic fertilizers from 50% to 60% under the Paramparagat Krishi Vikas Yojana (PKVY). This includes vermicompost, bio-fertilizers, neem cake, and other organic inputs. The decision will benefit over 2 million farmers practicing or transitioning to organic farming. The subsidy will be directly transferred to farmers' bank accounts upon purchase from authorized dealers.",image:"fa-recycle",related:[3,5,7],bookmarked:false,date:dateOff(-10),author:"Agriculture Ministry",readTime:"4 min read"},
    {id:11,headline:"AI-Powered Crop Disease Detection App Launched",category:"Technology",source:"Agritech Today",summary:"ICAR launches 'CropDoc' AI app that detects 50+ crop diseases using smartphone photos with 95% accuracy. Available in 12 Indian languages.",full:"The Indian Council of Agricultural Research (ICAR) has launched 'CropDoc', an AI-powered mobile application that can detect over 50 crop diseases through smartphone photos with 95% accuracy. The app works offline and supports 12 Indian languages. Farmers simply take a photo of the affected plant part and receive instant diagnosis with treatment recommendations. The app also connects farmers to nearby agricultural experts and input dealers.",image:"fa-robot",related:[1,3,5],bookmarked:false,date:dateOff(-11),author:"ICAR Team",readTime:"5 min read"},
    {id:12,headline:"e-NAM Trading Crosses ₹1 Lakh Crore Mark",category:"Markets",source:"AgriMarket Pulse",summary:"Electronic trading on the e-NAM platform has crossed ₹1 lakh crore in annual trade volume, with 1.7 crore farmers registered on the platform.",full:"The National Agriculture Market (e-NAM) platform has achieved a historic milestone, crossing ₹1 lakh crore in annual trading volume. With 1.7 crore registered farmers and 3,000+ mandis integrated, the platform is transforming agricultural marketing in India. Farmers selling through e-NAM report 15-20% higher prices on average due to competitive bidding. The government plans to integrate all 7,000 mandis under the platform by 2028.",image:"fa-laptop",related:[1,4,9],bookmarked:false,date:dateOff(-12),author:"e-NAM Report",readTime:"3 min read"},
    {id:13,headline:"Heatwave Alert: Farmers Advised on Crop Protection",category:"Weather",source:"IMD",summary:"IMD issues heatwave warning for central India. Farmers advised to provide shade, increase irrigation frequency, and use mulching to protect crops.",full:"The India Meteorological Department has issued a heatwave warning for parts of central India including Maharashtra, Madhya Pradesh, and Rajasthan for the next 5 days. Temperatures are expected to reach 44°C in some areas. Farmers are advised to provide shade to young plants, increase irrigation frequency during early morning or evening hours, apply mulching to conserve soil moisture, and protect livestock with adequate water and shade. Horticulture crops are particularly vulnerable.",image:"fa-temperature-high",related:[2,4,8],bookmarked:false,date:dateOff(-13),author:"IMD Advisory",readTime:"3 min read"},
    {id:14,headline:"Breeder Seed Production Target Set at 2.5 Lakh Quintals",category:"Agriculture",source:"ICAR",summary:"India targets production of 2.5 lakh quintals of breeder seeds for 2026-27 to ensure availability of quality seeds for all major crops.",full:"The government has set an ambitious target of producing 2.5 lakh quintals of breeder seeds for the 2026-27 cropping season. This will ensure adequate availability of quality foundation and certified seeds for farmers. The focus will be on climate-resilient varieties, biofortified crops, and high-yielding hybrids. ICAR and state agricultural universities will lead the production across 500+ seed production centres.",image:"fa-seedling",related:[1,3,7],bookmarked:false,date:dateOff(-14),author:"ICAR HQ",readTime:"4 min read"},
    {id:15,headline:"Farm Loan Waiver: ₹2 Lakh Crore Debt Relief Announced",category:"Government",source:"PIB",summary:"Government announces comprehensive farm loan waiver of ₹2 lakh crore benefiting 5 crore small and marginal farmers across all states.",full:"In a landmark decision, the government has announced a farm loan waiver of ₹2 lakh crore to benefit 5 crore small and marginal farmers. The waiver covers agricultural loans up to ₹2 lakh per farmer. Banks have been directed to issue no-dues certificates within 30 days. The scheme is expected to provide significant relief to distressed farmers and improve their access to fresh credit. States have been asked to identify eligible beneficiaries within 60 days.",image:"fa-file-invoice",related:[4,6,10],bookmarked:false,date:dateOff(-15),author:"Finance Ministry",readTime:"4 min read"}
  ];

  // ========== LEARNING COURSES (20+ courses) ==========
  db.learningCourses = [
    {id:1,title:"Advanced Hydroponics: Soil-less Farming Mastery",category:"tech",level:"Advanced",duration:"4h 12 Lessons",rating:4.9,students:12450,image:"fa-seedling",instructor:"Dr. Arvind Swaminathan",description:"Master hydroponic farming techniques including NFT, DWC, aeroponics, and vertical farming systems. Hands-on with nutrient management.",price:"Free",certificate:true,lessons:[{title:"Introduction to Hydroponics",duration:"22 min",completed:true},{title:"Nutrient Solutions Management",duration:"28 min",completed:true},{title:"NFT System Setup & Maintenance",duration:"35 min",completed:false},{title:"Deep Water Culture Techniques",duration:"25 min",completed:false},{title:"Aeroponics for Root Crops",duration:"30 min",completed:false},{title:"Pest Management in Soilless Systems",duration:"20 min",completed:false},{title:"Commercial Scale Planning",duration:"40 min",completed:false},{title:"Harvesting & Post-Harvest Handling",duration:"25 min",completed:false}],progress:38},
    {id:2,title:"Organic Soil Biology & Fertility Management",category:"soil",level:"Intermediate",duration:"2.5h 8 Lessons",rating:4.8,students:8930,image:"fa-earth-asia",instructor:"Dr. Meera Deshmukh",description:"Understand soil microbiology, organic matter management, composting techniques, and natural fertility enhancement for sustainable farming.",price:"Free",certificate:true,lessons:[{title:"Soil Food Web Fundamentals",duration:"20 min",completed:true},{title:"Composting Methods",duration:"25 min",completed:true},{title:"Vermicompost Production",duration:"18 min",completed:true},{title:"Green Manure Cover Crops",duration:"22 min",completed:false},{title:"Bio-fertilizer Application",duration:"20 min",completed:false},{title:"Soil pH Management",duration:"15 min",completed:false},{title:"Nutrient Cycling",duration:"25 min",completed:false}],progress:52},
    {id:3,title:"Dairy Cow Health & Management",category:"livestock",level:"Intermediate",duration:"5h 16 Lessons",rating:4.7,students:15670,image:"fa-cow",instructor:"Dr. Rajesh Patel",description:"Complete dairy management covering cow health, nutrition, breeding, milk production optimization, and disease prevention strategies.",price:"Free",certificate:true,lessons:[{title:"Dairy Breeds Selection",duration:"20 min"},{title:"Housing & Sanitation",duration:"25 min"},{title:"Feeding & Nutrition",duration:"30 min"},{title:"Health Monitoring Systems",duration:"22 min"},{title:"Vaccination Schedule",duration:"15 min"},{title:"Milk Production Optimization",duration:"28 min"},{title:"Breeding & Reproduction",duration:"25 min"},{title:"Common Diseases & Treatment",duration:"30 min"}],progress:0},
    {id:4,title:"Mandi Markets, Export & Farm Business",category:"finance",level:"Advanced",duration:"3h 10 Lessons",rating:4.6,students:7230,image:"fa-chart-line",instructor:"Ananya Sen",description:"Learn market dynamics, mandi trading, export procedures, pricing strategies, and business management for profitable farming.",price:"Free",certificate:true,lessons:[{title:"Understanding Mandi Systems",duration:"20 min",completed:true},{title:"Price Discovery Mechanisms",duration:"18 min",completed:true},{title:"e-NAM Platform Trading",duration:"25 min",completed:true},{title:"Export Documentation",duration:"30 min",completed:false},{title:"Quality Certification",duration:"20 min",completed:false},{title:"Supply Chain Management",duration:"22 min",completed:false},{title:"Farm Profitability Analysis",duration:"25 min",completed:false},{title:"Tax & Compliance",duration:"20 min",completed:false}],progress:42},
    {id:5,title:"Drone Crop Surveys & NDVI Analysis",category:"tech",level:"Advanced",duration:"6h 18 Lessons",rating:4.9,students:5120,image:"fa-helicopter",instructor:"Vijay Rao",description:"Professional drone piloting for agriculture. Learn flight planning, NDVI/NDMI mapping, multispectral analysis, and crop health reporting.",price:"Free",certificate:true,lessons:[{title:"Drone Types for Agriculture",duration:"20 min"},{title:"Flight Planning & Regulations",duration:"30 min"},{title:"NDVI Sensor Technology",duration:"25 min"},{title:"Mission Planning Software",duration:"28 min"},{title:"Data Collection Best Practices",duration:"22 min"},{title:"Image Processing & Analysis",duration:"35 min"},{title:"Health Report Generation",duration:"20 min"},{title:"Variable Rate Application",duration:"25 min"}],progress:5},
    {id:6,title:"Smart Irrigation Management",category:"water",level:"Intermediate",duration:"4h 12 Lessons",rating:4.8,students:10230,image:"fa-water",instructor:"Prof. G.S. Randhawa",description:"Design, implement, and manage efficient irrigation systems. Covers drip, sprinkler, pivot irrigation, and IoT-based smart water management.",price:"Free",certificate:true,lessons:[{title:"Irrigation Systems Overview",duration:"20 min",completed:true},{title:"Drip Irrigation Design",duration:"30 min",completed:true},{title:"Sprinkler Systems",duration:"25 min",completed:true},{title:"Soil Moisture Monitoring",duration:"22 min",completed:false},{title:"IoT Smart Irrigation",duration:"28 min",completed:false},{title:"Water Budgeting",duration:"20 min",completed:false},{title:"Maintenance & Troubleshooting",duration:"18 min",completed:false}],progress:48},
    {id:7,title:"Organic Pest Control & IPM",category:"pest",level:"Intermediate",duration:"3h 9 Lessons",rating:4.7,students:7890,image:"fa-bug",instructor:"Dr. Sarah Patel",description:"Integrated Pest Management strategies using biological controls, botanical pesticides, trap crops, and beneficial insects for organic farming.",price:"Free",certificate:true,lessons:[{title:"IPM Principles",duration:"20 min"},{title:"Beneficial Insects Identification",duration:"25 min"},{title:"Botanical Pesticides",duration:"22 min"},{title:"Trap Cropping Strategy",duration:"18 min"},{title:"Pheromone Traps",duration:"15 min"},{title:"Biological Control Agents",duration:"28 min"},{title:"Disease Forecasting",duration:"22 min"}],progress:0},
    {id:8,title:"Precision Agriculture with IoT Sensors",category:"tech",level:"Advanced",duration:"5h 15 Lessons",rating:4.9,students:3450,image:"fa-microchip",instructor:"TechAgri Solutions",description:"Implement IoT sensor networks for real-time field monitoring. Soil sensors, weather stations, automated irrigation, and data analytics dashboard.",price:"Free",certificate:true,lessons:[{title:"IoT in Agriculture Overview",duration:"20 min"},{title:"Sensor Types & Selection",duration:"25 min"},{title:"Network Architecture",duration:"30 min"},{title:"Data Collection Systems",duration:"22 min"},{title:"Dashboard Development",duration:"35 min"},{title:"Automated Control Systems",duration:"28 min"},{title:"Data Analytics & Insights",duration:"25 min"}],progress:0},
    {id:9,title:"Post-Harvest Management & Value Addition",category:"agri",level:"Intermediate",duration:"3.5h 10 Lessons",rating:4.6,students:6780,image:"fa-warehouse",instructor:"Dr. Sunita Devi",description:"Learn post-harvest handling, storage techniques, cold chain management, processing, and value addition to reduce losses and increase farm income.",price:"Free",certificate:true,lessons:[{title:"Harvest Maturity Indices",duration:"18 min"},{title:"Grading & Sorting",duration:"22 min"},{title:"Cold Storage Management",duration:"25 min"},{title:"Packaging Technology",duration:"20 min"},{title:"Food Processing Basics",duration:"30 min"},{title:"Value-Added Products",duration:"28 min"},{title:"Marketing & Distribution",duration:"22 min"}],progress:0},
    {id:10,title:"Farm Mechanization & Equipment Operation",category:"mechanization",level:"Beginner",duration:"2h 6 Lessons",rating:4.5,students:12340,image:"fa-tractor",instructor:"Ramesh Kumar",description:"Introduction to farm machinery - tractors, harvesters, planters, sprayers. Safe operation, maintenance, and cost-benefit analysis of farm equipment.",price:"Free",certificate:true,lessons:[{title:"Tractor Types & Selection",duration:"20 min",completed:true},{title:"Tillage Equipment",duration:"18 min",completed:true},{title:"Sowing & Planting Machinery",duration:"22 min",completed:true},{title:"Plant Protection Equipment",duration:"20 min",completed:false},{title:"Harvesting Machinery",duration:"25 min",completed:false},{title:"Safety & Maintenance",duration:"15 min",completed:false}],progress:65},
    {id:11,title:"Vermicompost & Organic Fertilizer Production",category:"soil",level:"Beginner",duration:"1.5h 5 Lessons",rating:4.8,students:18760,image:"fa-leaf",instructor:"Green Earth Foundation",description:"Start your own vermicompost production unit. Learn vermi-bed preparation, worm species, harvesting, packaging, and marketing organic fertilizers.",price:"Free",certificate:true,lessons:[{title:"Introduction to Vermicompost",duration:"15 min",completed:true},{title:"Worm Species Selection",duration:"18 min",completed:true},{title:"Bed Preparation",duration:"22 min",completed:true},{title:"Harvesting Methods",duration:"20 min",completed:true},{title:"Marketing & Sales",duration:"15 min",completed:false}],progress:82},
    {id:12,title:"Mushroom Cultivation for Beginners",category:"agri",level:"Beginner",duration:"2h 6 Lessons",rating:4.7,students:21540,image:"fa-mushroom",instructor:"Dr. Anil Verma",description:"Complete guide to mushroom farming - button, oyster, and paddy straw mushrooms. Low-cost technology for small farmers with high returns.",price:"Free",certificate:true,lessons:[{title:"Introduction to Mushroom Farming",duration:"15 min",completed:true},{title:"Spawn Production",duration:"20 min",completed:true},{title:"Growing Medium Preparation",duration:"25 min",completed:true},{title:"Environmental Control",duration:"18 min",completed:false},{title:"Harvesting & Storage",duration:"15 min",completed:false},{title:"Disease Management",duration:"20 min",completed:false}],progress:55},
    {id:13,title:"Sustainable Water Harvesting & Conservation",category:"water",level:"Intermediate",duration:"3h 9 Lessons",rating:4.8,students:8920,image:"fa-cloud-rain",instructor:"EcoWater India",description:"Rainwater harvesting, farm pond design, check dams, recharge structures, and water budgeting for sustainable agriculture in rainfed areas.",price:"Free",certificate:true,lessons:[{title:"Water Scenario in Agriculture",duration:"20 min"},{title:"Rainwater Harvesting Systems",duration:"30 min"},{title:"Farm Pond Design",duration:"25 min"},{title:"Check Dam Construction",duration:"22 min"},{title:"Groundwater Recharge",duration:"20 min"},{title:"Water Budgeting Tools",duration:"18 min"},{title:"Community Water Management",duration:"25 min"}],progress:0},
    {id:14,title:"Beekeeping for Crop Pollination & Honey",category:"livestock",level:"Beginner",duration:"2h 7 Lessons",rating:4.6,students:5670,image:"fa-dove",instructor:"Dr. Prakash Rao",description:"Start beekeeping for increased crop pollination (30% higher yields) and honey production. Hive management, queen rearing, and honey processing.",price:"Free",certificate:true,lessons:[{title:"Introduction to Apiculture",duration:"15 min"},{title:"Bee Species & Hive Types",duration:"20 min"},{title:"Hive Installation",duration:"18 min"},{title:"Seasonal Management",duration:"22 min"},{title:"Pest & Disease Control",duration:"20 min"},{title:"Honey Harvesting & Processing",duration:"25 min"},{title:"Marketing Honey Products",duration:"15 min"}],progress:0},
    {id:15,title:"Climate-Smart Agriculture Practices",category:"agri",level:"Advanced",duration:"4h 12 Lessons",rating:4.7,students:4300,image:"fa-globe",instructor:"Dr. Rajiv Mehta",description:"Adaptation strategies for climate change - drought-resistant varieties, weather forecasting integration, carbon farming, and climate risk management.",price:"Free",certificate:true,lessons:[{title:"Climate Change Impacts",duration:"25 min"},{title:"Resilient Crop Varieties",duration:"30 min"},{title:"Weather Forecasting Integration",duration:"22 min"},{title:"Carbon Sequestration",duration:"28 min"},{title:"Risk Management Tools",duration:"20 min"},{title:"Climate-Smart Villages",duration:"25 min"},{title:"Policy & Support Programs",duration:"18 min"}],progress:0}
  ];

  // ========== SUSTAINABILITY DATA ==========
  db.sustainabilityData = {
    waterConserved: 245000,
    co2Reduced: 128,
    treesPlanted: 3500,
    organicArea: 185,
    solarCapacity: 45,
    biodiversityScore: 78,
    carbonFootprint: 320,
    environmentalScore: 82,
    waterUsageAnalytics: [
      {month:"Jan",usage:420,rainfall:15},{month:"Feb",usage:380,rainfall:8},{month:"Mar",usage:510,rainfall:3},
      {month:"Apr",usage:580,rainfall:0},{month:"May",usage:620,rainfall:2},{month:"Jun",usage:480,rainfall:60},
      {month:"Jul",usage:350,rainfall:120},{month:"Aug",usage:330,rainfall:110},{month:"Sep",usage:360,rainfall:85}
    ],
    initiatives: [
      {title:"Rainwater Harvesting System",progress:100,status:"Completed",impact:"50,000L storage",icon:"fa-cloud-rain"},
      {title:"Solar Panel Installation",progress:100,status:"Completed",impact:"5kW capacity",icon:"fa-sun"},
      {title:"Organic Farming Certification",progress:65,status:"In Progress",impact:"Certification by Dec 2026",icon:"fa-leaf"},
      {title:"Tree Plantation Drive",progress:80,status:"In Progress",impact:"3,500 trees planted",icon:"fa-tree"},
      {title:"Vermicompost Unit",progress:100,status:"Completed",impact:"2 tons/month",icon:"fa-recycle"}
    ]
  };

  return db;
})();

if (typeof window !== 'undefined') window.FarmDB = FarmDB;
