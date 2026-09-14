/**
 * Farm Assist - Mock Data Module
 * Provides realistic sample data for all pages during development.
 * Structure mirrors backend API responses for easy migration.
 */
window.AppMockData = (function () {
  'use strict';

  var data = {};

  // ======================================================================
  // AUTH / USER
  // ======================================================================
  data.user = {
    id: 'FA-AS-00000001',
    name: 'Ramesh Patel',
    email: 'ramesh@farmassist.in',
    phone: '+91 98765 43210',
    avatar: '',
    role: 'farmer',
    location: 'Nashik, Maharashtra',
    farmSize: '5.2 acres',
    joined: '2024-01-15',
    languages: ['Hindi', 'Marathi', 'English'],
    preferredLanguage: 'Hindi',
    kycVerified: true,
    subscription: 'premium',
    notifications: { email: true, sms: true, push: true }
  };

  // ======================================================================
  // DASHBOARD
  // ======================================================================
  data.dashboard = {
    summary: {
      activeCrops: 3,
      pendingTasks: 7,
      upcomingEvents: 2,
      unreadMessages: 4,
      weatherAlert: false,
      marketPricesUpdated: '2 hours ago'
    },
    quickActions: [
      { id: 'qa1', label: 'Add Farm Activity', icon: 'fa-plus-circle', href: 'farm.html#add-activity', color: '#22C55E' },
      { id: 'qa2', label: 'Check Weather', icon: 'fa-cloud-sun', href: 'weather.html', color: '#3B82F6' },
      { id: 'qa3', label: 'Market Prices', icon: 'fa-chart-line', href: 'marketplace.html', color: '#F59E0B' },
      { id: 'qa4', label: 'Messages', icon: 'fa-envelope', href: 'messages.html', color: '#10B981' },
      { id: 'qa5', label: 'AI Assistant', icon: 'fa-robot', href: 'ai.html', color: '#8B5CF6' },
      { id: 'qa6', label: 'Emergency', icon: 'fa-phone-alt', href: '#emergency', color: '#EF4444' }
    ],
    recentActivities: [
      { id: 'act1', type: 'crop', description: 'Wheat field irrigated', time: '2 hours ago', icon: 'fa-droplet', color: '#3B82F6' },
      { id: 'act2', type: 'market', description: 'Sold 50 kg Tomatoes for ₹2,500', time: '5 hours ago', icon: 'fa-sack-dollar', color: '#22C55E' },
      { id: 'act3', type: 'task', description: 'Completed: Fertilizer application for Plot B', time: 'Yesterday', icon: 'fa-check-circle', color: '#10B981' },
      { id: 'act4', type: 'weather', description: 'Heavy rain expected tomorrow', time: 'Yesterday', icon: 'fa-cloud-rain', color: '#6366F1' },
      { id: 'act5', type: 'alert', description: 'Pest alert: Aphids detected in Cotton field', time: '2 days ago', icon: 'fa-bug', color: '#EF4444' },
      { id: 'act6', type: 'finance', description: 'Insurance premium payment due in 5 days', time: '2 days ago', icon: 'fa-shield', color: '#F59E0B' }
    ],
    alerts: [
      { id: 'al1', type: 'weather', title: 'Heavy Rain Warning', description: '60% chance of rain tomorrow. Consider delaying harvest.', severity: 'warning', time: '1 hour ago' },
      { id: 'al2', type: 'pest', title: 'Pest Alert: Aphids', description: 'Aphid activity reported in nearby farms. Inspect crops.', severity: 'critical', time: '3 hours ago' },
      { id: 'al3', type: 'market', title: 'Tomato prices up 15%', description: 'Current rate: ₹45/kg. Good time to sell.', severity: 'info', time: '6 hours ago' }
    ],
    upcomingEvents: [
      { id: 'ev1', title: 'Fertilizer Application - Wheat', date: '2026-07-30', type: 'task' },
      { id: 'ev2', title: 'Market Visit - Sell Produce', date: '2026-08-02', type: 'market' },
      { id: 'ev3', title: 'Soil Testing Appointment', date: '2026-08-05', type: 'service' }
    ]
  };

  // ======================================================================
  // FARM / CROPS
  // ======================================================================
  data.farm = {
    farmName: 'Shiv Sai Farm',
    totalArea: '5.2 acres',
    soilType: 'Loamy',
    waterSource: 'Borewell + Canal',
    activeCrops: [
      { id: 'c1', name: 'Wheat', variety: 'GW-322', area: '2.5 acres', planted: '2026-06-15', expectedHarvest: '2026-10-20', stage: 'Vegetative Growth', health: 'Good', waterNeeded: 'Moderate', nextAction: 'Apply fertilizer on July 30' },
      { id: 'c2', name: 'Cotton', variety: 'Bt Cotton', area: '1.5 acres', planted: '2026-05-20', expectedHarvest: '2026-11-15', stage: 'Flowering', health: 'Fair', waterNeeded: 'High', nextAction: 'Monitor for pests' },
      { id: 'c3', name: 'Tomato', variety: 'Hybrid-101', area: '1.2 acres', planted: '2026-04-10', expectedHarvest: '2026-08-15', stage: 'Fruiting', health: 'Good', waterNeeded: 'High', nextAction: 'Harvest ready - check market prices' }
    ],
    soilData: { pH: 6.8, nitrogen: 'Medium', phosphorous: 'High', potassium: 'Medium', organic: '2.1%', lastTested: '2026-03-15' }
  };

  // ======================================================================
  // TASKS
  // ======================================================================
  data.tasks = [
    { id: 't1', title: 'Irrigate Wheat field', priority: 'high', dueDate: '2026-07-30', status: 'pending', category: 'irrigation', description: 'Drip irrigation for 2 hours in Plot A' },
    { id: 't2', title: 'Buy fertilizer for Cotton', priority: 'high', dueDate: '2026-07-29', status: 'in-progress', category: 'supplies', description: 'NPK 20-20-20, 50kg bag' },
    { id: 't3', title: 'Check pest traps', priority: 'medium', dueDate: '2026-07-31', status: 'pending', category: 'monitoring', description: 'Inspect all pheromone traps in Cotton field' },
    { id: 't4', title: 'Prepare harvest tools', priority: 'low', dueDate: '2026-08-08', status: 'pending', category: 'maintenance', description: 'Clean and sharpen harvesting tools' },
    { id: 't5', title: 'Submit soil sample for testing', priority: 'medium', dueDate: '2026-08-05', status: 'pending', category: 'testing', description: 'Take samples from Plot B and C' },
    { id: 't6', title: 'Pay electricity bill', priority: 'high', dueDate: '2026-07-28', status: 'completed', category: 'finance', description: 'Farm pump connection bill' },
    { id: 't7', title: 'Attend Kisan Sabha meeting', priority: 'medium', dueDate: '2026-08-01', status: 'pending', category: 'community', description: 'Monthly farmers meeting at village hall' },
    { id: 't8', title: 'Spray neem oil on Tomato plot', priority: 'high', dueDate: '2026-08-03', status: 'pending', category: 'pest-control', description: 'Organic pest prevention on fruiting Tomato plants' },
    { id: 't9', title: 'Repair drip line in Plot B', priority: 'medium', dueDate: '2026-08-04', status: 'pending', category: 'maintenance', description: 'Replace leaking emitters in cotton rows' },
    { id: 't10', title: 'Hire harvesting workers', priority: 'high', dueDate: '2026-08-07', status: 'in-progress', category: 'labour', description: 'Book 3 workers for Tomato harvest' },
    { id: 't11', title: 'Clean grain storage shed', priority: 'low', dueDate: '2026-08-10', status: 'pending', category: 'maintenance', description: 'Disinfect and prepare for new harvest' },
    { id: 't12', title: 'Order drip irrigation spare parts', priority: 'low', dueDate: '2026-08-12', status: 'pending', category: 'supplies', description: 'Filters, emitters, and end caps' },
    { id: 't13', title: 'Weed control in Wheat field', priority: 'medium', dueDate: '2026-08-06', status: 'pending', category: 'weeding', description: 'Manual weeding in Plot A' },
    { id: 't14', title: 'Update crop health records', priority: 'low', dueDate: '2026-08-09', status: 'pending', category: 'monitoring', description: 'Log weekly observations for all crops' },
    { id: 't15', title: 'Renew Kisan Credit Card', priority: 'high', dueDate: '2026-08-14', status: 'pending', category: 'finance', description: 'Carry land records and ID to bank' },
    { id: 't16', title: 'Check weather forecast', priority: 'medium', dueDate: '2026-07-30', status: 'completed', category: 'monitoring', description: 'Plan irrigation around expected rain' },
    { id: 't17', title: 'Service tractor', priority: 'medium', dueDate: '2026-08-15', status: 'pending', category: 'maintenance', description: 'Oil change and filter replacement' },
    { id: 't18', title: 'Sell surplus produce at mandi', priority: 'high', dueDate: '2026-08-02', status: 'pending', category: 'market', description: 'Check Tomato and Wheat mandi rates first' }
  ];

  // ======================================================================
  // MARKETPLACE
  // ======================================================================
  data.marketplace = {
    categories: ['Vegetables', 'Fruits', 'Grains', 'Seeds', 'Fertilizers', 'Tools'],
    products: [
      { id: 'p1', name: 'Organic Tomatoes', type: 'Vegetables', price: 42, unit: 'kg', qty: 500, farmer: 'Ramesh Patel', location: 'Nashik', listed: '2026-07-26', image: '', rating: 4.5 },
      { id: 'p2', name: 'Fresh Wheat Grain', type: 'Grains', price: 28, unit: 'kg', qty: 2000, farmer: 'Suresh Verma', location: 'Pune', listed: '2026-07-25', image: '', rating: 4.2 },
      { id: 'p3', name: 'BT Cotton Seeds', type: 'Seeds', price: 850, unit: 'pack', qty: 50, farmer: 'Krishna Seeds Co.', location: 'Mumbai', listed: '2026-07-20', image: '', rating: 4.7 },
      { id: 'p4', name: 'DAP Fertilizer', type: 'Fertilizers', price: 1200, unit: 'bag', qty: 100, farmer: 'AgriGrow Ltd.', location: 'Nashik', listed: '2026-07-22', image: '', rating: 4.0 },
      { id: 'p5', name: 'Mango (Alphonso)', type: 'Fruits', price: 120, unit: 'kg', qty: 200, farmer: 'Mohan Desai', location: 'Ratnagiri', listed: '2026-07-18', image: '', rating: 4.9 }
    ]
  };

  // ======================================================================
  // FINANCE
  // ======================================================================
  data.finance = {
    summary: { totalIncome: 284500, totalExpenses: 142300, netProfit: 142200, pendingPayments: 35000 },
    transactions: [
      { id: 'f1', type: 'income', category: 'Crop Sale', description: 'Sold Wheat - 200 kg', amount: 5600, date: '2026-07-25', method: 'UPI' },
      { id: 'f2', type: 'expense', category: 'Supplies', description: 'DAP Fertilizer - 2 bags', amount: 2400, date: '2026-07-22', method: 'Cash' },
      { id: 'f3', type: 'income', category: 'Subsidy', description: 'PM-KISAN installment', amount: 6000, date: '2026-07-15', method: 'Bank Transfer' },
      { id: 'f4', type: 'expense', category: 'Labor', description: 'Harvesting labor (3 workers)', amount: 4500, date: '2026-07-20', method: 'Cash' },
      { id: 'f5', type: 'income', category: 'Crop Sale', description: 'Sold Tomatoes - 80 kg', amount: 3600, date: '2026-07-28', method: 'UPI' }
    ]
  };

  // ======================================================================
  // INSURANCE
  // ======================================================================
  data.insurance = {
    summary: { activePolicies: 2, totalCoverage: 350000, totalPremium: 8750, pendingClaims: 1 },
    policies: [
      { id: 'ins1', name: 'PMFBY Crop Insurance - Wheat', number: 'PMFBY-2026-00142', crop: 'Wheat (2.5 acres)', coverage: 150000, premium: 3750, startDate: '2026-06-15', endDate: '2026-10-20', status: 'active' },
      { id: 'ins2', name: 'PMFBY Crop Insurance - Cotton', number: 'PMFBY-2026-00189', crop: 'Cotton (1.5 acres)', coverage: 200000, premium: 5000, startDate: '2026-05-20', endDate: '2026-11-15', status: 'active' }
    ],
    claims: [
      { id: 'cl1', policy: 'PMFBY - Cotton', amount: 45000, date: '2026-07-10', status: 'pending', reason: 'Pest damage - Aphid infestation' }
    ]
  };

  // ======================================================================
  // GOVERNMENT SCHEMES
  // ======================================================================
  data.schemes = [
    { id: 's1', name: 'PM-KISAN Samman Nidhi', benefit: '₹6,000/year', eligibility: 'All farmers', status: 'Enrolled', deadline: 'Ongoing', description: 'Direct income support of ₹6,000 per year in 3 installments' },
    { id: 's2', name: 'PMFBY Crop Insurance', benefit: 'Insurance coverage', eligibility: 'Crop loan borrowers', status: 'Enrolled', deadline: 'Seasonal', description: 'Comprehensive crop insurance at nominal premium' },
    { id: 's3', name: 'Kisan Credit Card', benefit: 'Up to ₹3L loan', eligibility: 'All farmers', status: 'Not Applied', deadline: 'Ongoing', description: 'Affordable credit for farming needs' },
    { id: 's4', name: 'Soil Health Card', benefit: 'Free soil testing', eligibility: 'All farmers', status: 'Applied', deadline: 'Apply by Dec', description: 'Get soil health assessment and recommendations' }
  ];

  // ======================================================================
  // WEATHER
  // ======================================================================
  data.weather = {
    current: { temp: 32, condition: 'Partly Cloudy', humidity: 65, windSpeed: 12, feelsLike: 34, uvIndex: 7 },
    forecast: [
      { day: 'Today', temp: 32, condition: 'Partly Cloudy', rain: '10%', icon: 'fa-cloud-sun' },
      { day: 'Wed', temp: 30, condition: 'Light Rain', rain: '60%', icon: 'fa-cloud-rain' },
      { day: 'Thu', temp: 29, condition: 'Rain', rain: '80%', icon: 'fa-cloud-showers-heavy' },
      { day: 'Fri', temp: 31, condition: 'Cloudy', rain: '30%', icon: 'fa-cloud' },
      { day: 'Sat', temp: 33, condition: 'Sunny', rain: '5%', icon: 'fa-sun' },
      { day: 'Sun', temp: 34, condition: 'Sunny', rain: '0%', icon: 'fa-sun' },
      { day: 'Mon', temp: 32, condition: 'Cloudy', rain: '20%', icon: 'fa-cloud' }
    ]
  };

  // ======================================================================
  // COMMUNITY
  // ======================================================================
  data.community = {
    groups: [
      { id: 'g1', name: 'Nashik Farmers Group', members: 245, posts: 1200, category: 'Regional', description: 'For farmers in Nashik district' },
      { id: 'g2', name: 'Organic Farming India', members: 15000, posts: 45000, category: 'Farming Method', description: 'Organic farming techniques and tips' },
      { id: 'g3', name: 'Crop Disease Help', members: 8200, posts: 18000, category: 'Health', description: 'Identify and treat crop diseases' }
    ],
    discussions: [
      { id: 'd1', title: 'Best wheat variety for late sowing?', author: 'Rajesh K.', replies: 12, likes: 45, time: '2 hours ago', group: 'Nashik Farmers' },
      { id: 'd2', title: 'Tomato price trend this week', author: 'Amit S.', replies: 8, likes: 32, time: '5 hours ago', group: 'Market Talk' }
    ]
  };

  // ======================================================================
  // EXPERT HUB
  // ======================================================================
  data.experts = [
    { id: 'e1', name: 'Dr. Suresh Patil', specialty: 'Agronomy', experience: '15 years', rating: 4.8, consultations: 340, available: true, fee: 'Free', languages: ['Marathi', 'Hindi', 'English'] },
    { id: 'e2', name: 'Dr. Meena Joshi', specialty: 'Plant Pathology', experience: '12 years', rating: 4.9, consultations: 280, available: false, fee: '₹199/session', languages: ['Hindi', 'English'] },
    { id: 'e3', name: 'Prof. Anil Deshmukh', specialty: 'Soil Science', experience: '20 years', rating: 4.7, consultations: 510, available: true, fee: 'Free', languages: ['Marathi', 'Hindi'] }
  ];

  // ======================================================================
  // MESSAGES / CHATS
  // ======================================================================
  data.contacts = [
    { id: 'c1', name: 'Dr. Suresh Patil', phone: '+91 98765 00001', lastMsg: 'Yes, I can visit your farm tomorrow at 10 AM', time: '10:32 AM', unread: 0, online: true, avatar: '' },
    { id: 'c2', name: 'Raju (Worker)', phone: '+91 98765 00002', lastMsg: 'Ok bhai, kal subah aata hu', time: '9:15 AM', unread: 2, online: true, avatar: '' },
    { id: 'c3', name: 'Market - Rakesh', phone: '+91 98765 00003', lastMsg: 'Tomato ka bhav aaj 45/kg hai', time: 'Yesterday', unread: 0, online: false, avatar: '' }
  ];
  data.conversations = {
    'c1': [
      { from: 'them', text: 'Hello Ramesh ji, how can I help you?', time: '10:00 AM' },
      { from: 'me', text: 'Doctor sahab, mere wheat mein keede lag gaye hain', time: '10:05 AM', status: 'read' },
      { from: 'them', text: 'Can you send me a photo of the affected leaves?', time: '10:08 AM' },
      { from: 'me', text: 'Haan ji, bhej raha hoon', time: '10:10 AM', status: 'read' },
      { from: 'me', text: '[Image]', time: '10:12 AM', status: 'read' },
      { from: 'them', text: 'This looks like aphid infestation. Use neem oil spray.', time: '10:20 AM' },
      { from: 'them', text: 'Yes, I can visit your farm tomorrow at 10 AM', time: '10:32 AM' }
    ],
    'c2': [
      { from: 'them', text: 'Ramesh bhai, kal ka kaam kya hai?', time: '8:50 AM' },
      { from: 'me', text: 'Kal ganna mein pani lagana hai', time: '8:55 AM', status: 'read' },
      { from: 'them', text: 'Theek hai bhai, karte hain', time: '9:00 AM' },
      { from: 'them', text: 'Ok bhai, kal subah aata hu', time: '9:15 AM' }
    ],
    'c3': [
      { from: 'them', text: 'Bhai, aaj tomato ka bhav 42/kg hai', time: 'Yesterday 4:00 PM' },
      { from: 'me', text: 'Achha, kitna stock chahiye?', time: 'Yesterday 4:15 PM', status: 'read' },
      { from: 'them', text: '100 kg le sakte hain aaj', time: 'Yesterday 4:20 PM', status: 'read' },
      { from: 'them', text: 'Tomato ka bhav aaj 45/kg hai', time: 'Yesterday 5:00 PM' }
    ]
  };

  // ======================================================================
  // SERVICES
  // ======================================================================
  data.services = {
    categories: [
      { id: 'svc1', name: 'Offline Support', icon: 'fa-wifi-slash', color: '#6B7280', desc: 'Get help when you\'re offline with cached resources', availability: 'available', response: 'Instant', badge: 'Free' },
      { id: 'svc2', name: 'Expert Consultation', icon: 'fa-stethoscope', color: '#8B5CF6', desc: 'Talk to agriculture experts via chat or call', availability: 'available', response: 'Within 15 min', badge: 'Free' },
      { id: 'svc3', name: 'Farm Visit', icon: 'fa-tractor', color: '#22C55E', desc: 'Schedule an on-farm visit by experts', availability: 'limited', response: 'Within 48 hrs', badge: '₹199' },
      { id: 'svc4', name: 'Soil Testing', icon: 'fa-flask', color: '#F59E0B', desc: 'Get soil tested and understand NPK levels', availability: 'available', response: 'Within 24 hrs', badge: '₹99' },
      { id: 'svc5', name: 'Crop Advisory', icon: 'fa-leaf', color: '#10B981', desc: 'Crop-specific guidance from sowing to harvest', availability: 'available', response: 'Within 1 hr', badge: 'Free' },
      { id: 'svc6', name: 'Scheme Assistance', icon: 'fa-file-invoice', color: '#3B82F6', desc: 'Help with applications, documents, tracking', availability: 'available', response: 'Within 2 hrs', badge: 'Free' },
      { id: 'svc7', name: 'Insurance Assistance', icon: 'fa-shield-halved', color: '#6366F1', desc: 'Policy selection, claims, renewals help', availability: 'available', response: 'Within 2 hrs', badge: 'Free' },
      { id: 'svc8', name: 'Loan Assistance', icon: 'fa-indian-rupee-sign', color: '#EC4899', desc: 'Find and apply for agriculture loans', availability: 'available', response: 'Within 4 hrs', badge: 'Free' },
      { id: 'svc9', name: 'Documentation', icon: 'fa-file-pen', color: '#F97316', desc: 'Help with land records, certificates filing', availability: 'available', response: 'Within 6 hrs', badge: '₹49' },
      { id: 'svc10', name: 'Equipment Help', icon: 'fa-screwdriver-wrench', color: '#14B8A6', desc: 'Find and book farm equipment', availability: 'limited', response: 'Within 12 hrs', badge: 'Varies' },
      { id: 'svc11', name: 'Worker Assistance', icon: 'fa-users-gear', color: '#E11D48', desc: 'Find skilled farm workers near you', availability: 'busy', response: 'Within 24 hrs', badge: 'Free' },
      { id: 'svc12', name: 'Technical Support', icon: 'fa-headset', color: '#7C3AED', desc: 'App and device technical assistance', availability: 'available', response: 'Within 30 min', badge: 'Free' }
    ],
    requests: [
      { id: 'SR-001', service: 'Soil Testing', date: '2026-07-25', status: 'completed', tracking: 'ST-2026-4521' },
      { id: 'SR-002', service: 'Expert Consultation', date: '2026-07-28', status: 'in-progress', tracking: 'EC-2026-7832' },
      { id: 'SR-003', service: 'Farm Visit', date: '2026-07-30', status: 'pending', tracking: 'FV-2026-1245' }
    ]
  };

  // ======================================================================
  // AI ASSISTANT
  // ======================================================================
  data.ai = {
    suggestions: [
      'What crops should I plant this season?',
      'How to control aphids in wheat?',
      'What is the market price of tomatoes?',
      'Which fertilizer is best for cotton?',
      'How to apply for PM-KISAN?'
    ],
    chatHistory: [
      { from: 'ai', text: 'Hello! I\'m your Farm Assistant. How can I help you today?', time: 'Just now' },
      { from: 'user', text: 'What crops should I plant this season?', time: 'Just now' },
      { from: 'ai', text: 'Based on your location (Nashik) and soil type (Loamy), I recommend:\n1. **Wheat** - Good for rabi season, high demand\n2. **Chickpeas** - Low water requirement, good profits\n3. **Mustard** - Short duration, good returns\n\nWould you like detailed information about any of these?', time: 'Just now' }
    ],
    weatherAlert: 'Heavy rain expected Wednesday. Consider delaying harvest.'
  };

  // ======================================================================
  // FARM MAP
  // ======================================================================
  data.farmMap = {
    center: { lat: 19.9975, lng: 73.7898 },
    plots: [
      { id: 'plot1', name: 'Plot A - Wheat', area: '2.5 acres', soilType: 'Loamy', crop: 'Wheat', status: 'Active' },
      { id: 'plot2', name: 'Plot B - Cotton', area: '1.5 acres', soilType: 'Clay Loam', crop: 'Cotton', status: 'Active' },
      { id: 'plot3', name: 'Plot C - Vegetables', area: '1.2 acres', soilType: 'Sandy Loam', crop: 'Tomato', status: 'Active' }
    ],
    markers: [
      { lat: 19.9975, lng: 73.7898, title: 'Borewell', type: 'water' },
      { lat: 19.9980, lng: 73.7890, title: 'Storage Shed', type: 'structure' }
    ]
  };

  // ======================================================================
  // CALENDAR
  // ======================================================================
  data.calendar = {
    events: [
      { id: 'cal1', title: 'Irrigate Wheat', date: '2026-07-30', type: 'task', priority: 'high' },
      { id: 'cal2', title: 'Market Visit - Sell Tomatoes', date: '2026-08-02', type: 'market', priority: 'medium' },
      { id: 'cal3', title: 'Fertilizer - Cotton', date: '2026-08-05', type: 'task', priority: 'high' },
      { id: 'cal4', title: 'Soil Testing Appointment', date: '2026-08-05', type: 'service', priority: 'medium' },
      { id: 'cal5', title: 'Kisan Sabha Meeting', date: '2026-08-01', type: 'community', priority: 'low' }
    ]
  };

  // ======================================================================
  // SETTINGS
  // ======================================================================
  data.settings = {
    language: 'Hindi',
    theme: 'light',
    notifications: { email: true, sms: true, push: true, marketAlerts: true, weatherAlerts: true, schemeUpdates: true },
    privacy: { profileVisible: true, locationSharing: true, activityStatus: true },
    app: { autoUpdate: true, cacheData: true, reduceData: false, fontSize: 'medium' }
  };

  // ======================================================================
  // HELP & SUPPORT
  // ======================================================================
  data.help = {
    faq: [
      { q: 'How do I add a new crop to my farm?', a: 'Go to My Farm page and click "Add Crop" button.' },
      { q: 'How do I reset my password?', a: 'Go to Settings → Security → Change Password.' },
      { q: 'How do I contact an expert?', a: 'Go to Expert Hub and click "Consult" on any expert.' }
    ],
    contacts: { email: 'support@farmassist.in', phone: '+91 1800-123-4567', hours: 'Mon-Sat, 9 AM - 6 PM' }
  };

  return data;
})();
