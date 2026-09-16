import random
import string
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.config import settings
from app.models.user import User, OTPVerification, UserSession, LoginHistory, FarmerProfile, UserAddress
from app.schemas.auth import (
    RegisterRequest, LoginRequest, OTPRequest, OTPVerifyRequest,
    UserResponse, TokenResponse,
)
from app.utils.auth import (
    create_access_token, hash_password, verify_password,
    get_current_user, generate_farmer_id, generate_id, normalize_farmer_id,
    phone_lookup_candidates,
)

router = APIRouter(prefix="/api/v1", tags=["Authentication"])

LOCATIONS = {
    "Telangana": {
        "Hyderabad": {
            "Secunderabad": ["Trimulgherry", "Malkajgiri", "Karkhana", "Alwal"],
            "Charminar": ["Laad Bazaar", "Purani Haveli", "Salarjung", "Falaknuma"],
            "Banjara Hills": ["Road No 12", "Road No 36", "Jubilee Hills", "Film Nagar"],
            "Madhapur": ["HITEC City", "Kondapur", "Gachibowli", "Miyapur"]
        },
        "Warangal": {
            "Warangal Urban": ["Kazipet", "Hanamkonda", "Narsampet", "Parkal"],
            "Warangal Rural": ["Jangaon", "Yellandu", "Bhupalpally", "Mahabubabad"],
            "Hanamkonda": ["Wardhannapet", "Nellikud", "Parvathagiri", "Doddurpeta"]
        },
        "Nalgonda": {
            "Nalgonda": ["Rajampur", "Devarakonda", "Miryalaguda", "Huzurnagar"],
            "Suryapet": ["Suryapet Town", "Huzurnagar", "Kodad", "Thipparthy"],
            "Mahabubnagar": ["Mahabubnagar Town", "Kollapur", "Wanaparthy", "Achampet"]
        },
        "Karimnagar": {
            "Karimnagar": ["Karimnagar Town", "Huzurabad", "Mancherial", "Peddapalli"],
            "Jagtial": ["Jagtial Town", "Korutla", "Metpally", "Raikal"],
            "Siddipet": ["Siddipet Town", "Dubbaka", "Mirdoddi", "Cheriyal"]
        },
        "Khammam": {
            "Khammam": ["Khammam Town", "Kusumanchi", "Yerrupalem", "Mudigal"],
            "Bhadrachalam": ["Bhadrachalam Town", "Manuguru", "Ashwaraopeta", "Burkacharla"],
            "Kothagudem": ["Kothagudem Town", "Paloncha", "Yellandu", "Cherla"]
        },
        "Adilabad": {
            "Adilabad": ["Adilabad Town", "Bela", "Tandur", "Nirmal"],
            "Mancherial": ["Mancherial Town", "Ramagundam", "Bellampalli", "Chennur"],
            "Nizamabad": ["Nizamabad Town", "Bodhan", "Jakranpally", "Banswada"]
        },
        "Rangareddy": {
            "Rangareddy": ["LB Nagar", "Uppal", "Medipally", "Ghatkesar"],
            "Vikarabad": ["Vikarabad Town", "Tandur", "Doma", "Mominpet"],
            "Sangareddy": ["Sangareddy Town", "Medak", "Narayankhed", "Zaheerabad"]
        },
        "Medak": {
            "Medak": ["Medak Town", "Siddipet", "Dubbak", "Cherial"],
            "Sangareddy": ["Sangareddy Town", "Patancheru", "Ramachandrapuram", "Jinnaram"]
        },
        "Mahabubnagar": {
            "Mahabubnagar": ["Mahabubnagar Town", "Kollapur", "Wanaparthy", "Achampet"],
            "Narayanpet": ["Narayanpet Town", "Makthal", "Kosgi", "Kollapur"],
            "Jadcherla": ["Jadcherla Town", "Shadnagar", "Kondurg", "Farooqnagar"]
        },
        "Nizamabad": {
            "Nizamabad": ["Nizamabad Town", "Bodhan", "Armur", "Banswada"],
            "Kamareddy": ["Kamareddy Town", "Yellareddy", "Nagireddipet", "Bichkonda"]
        }
    },
    "Andhra Pradesh": {
        "Guntur": {
            "Guntur": ["Guntur Town", "Tenali", "Mangalagiri", "Sattenapalli"],
            "Tenali": ["Tenali Town", "Cherukuru", "Vatticherukuru", "Kollipara"],
            "Bapatla": ["Bapatla Town", "Ponnur", "Sattenapalli", "Repalle"]
        },
        "Krishna": {
            "Vijayawada": ["Vijayawada Town", "Gannavaram", "Kankipadu", "Penamaluru"],
            "Machilipatnam": ["Machilipatnam Town", "Gudivada", "Bapulapadu", "Nandivada"],
            "Nuzvid": ["Nuzvid Town", "Gannavaram", "Vuyyuru", "Pamarru"]
        },
        "East Godavari": {
            "Rajahmundry": ["Rajahmundry Town", "Kovvur", "Diviseema", "Kadiam"],
            "Kakinada": ["Kakinada Town", "Pithapuram", "Peddapuram", "Samalkot"],
            "Amalapuram": ["Amalapuram Town", "Mummidivaram", "Razole", "Allavaram"]
        },
        "West Godavari": {
            "Eluru": ["Eluru Town", "Bhimavaram", "Narsapur", "Tanuku"],
            "Bhimavaram": ["Bhimavaram Town", "Palakollu", "Narsapur", "Akividu"],
            "Tadepalligudem": ["Tadepalligudem Town", "Tanuku", "Nidadavole", "Undi"]
        },
        "Prakasam": {
            "Ongole": ["Ongole Town", "Chirala", "Kandukur", "Markapur"],
            "Chirala": ["Chirala Town", "Bapatla", "Repalle", "Ponnur"],
            "Kandukur": ["Kandukur Town", "Cumbum", "Giddalur", "Rajupalem"]
        },
        "Nellore": {
            "Nellore": ["Nellore Town", "Gudur", "Kavali", "Venkatagiri"],
            "Kavali": ["Kavali Town", "Atmakur", "Udayagiri", "Kondapi"],
            "Gudur": ["Gudur Town", "Sullurpeta", "Tada", "Venkatagiri"]
        },
        "Chittoor": {
            "Chittoor": ["Chittoor Town", "Tirupati", "Puttur", "Vepanapalli"],
            "Tirupati": ["Tirupati Town", "Tirumala", "Renigunta", "Chandragiri"],
            "Kadapa": ["Kadapa Town", "Proddatur", "Rajampet", "Jammalamadugu"]
        },
        "Anantapur": {
            "Anantapur": ["Anantapur Town", "Hindupur", "Kadiri", "Dharmavaram"],
            "Hindupur": ["Hindupur Town", "Penukonda", "Madakasira", "Gudipalli"],
            "Kurnool": ["Kurnool Town", "Nandyal", "Yemmiganur", "Adoni"]
        },
        "Vizianagaram": {
            "Vizianagaram": ["Vizianagaram Town", "Srungavarapukota", "Gajapathinagaram", "Bobbili"],
            "Srikakulam": ["Srikakulam Town", "Palasa", "Amadalavalasa", "Ichapuram"]
        },
        "Visakhapatnam": {
            "Visakhapatnam": ["Visakhapatnam Town", "Gajuwaka", "Anakapalle", "Padmanabham"],
            "Anakapalle": ["Anakapalle Town", "Chodavaram", "S.Rayavaram", "Nakkapalli"]
        },
        "Vizianagaram": {
            "Vizianagaram": ["Vizianagaram Town", "Bobbili", "Salur", "Nellimarla"],
            "Parvathipuram": ["Parvathipuram Town", "Palakonda", "Seethampeta", "Bhamini"]
        }
    },
    "Karnataka": {
        "Bangalore": {
            "Bangalore Urban": ["HSR Layout", "Koramangala", "Whitefield", "Electronic City"],
            "Bangalore Rural": ["Devanahalli", "Hoskote", "Nelamangala", "Ramanagara"]
        },
        "Mysore": {
            "Mysore": ["Mysore City", "Nanjangud", "Hunsur", "Tirumakudal"],
            "Chamarajanagar": ["Chamarajanagar Town", "Gundlupet", "Kollegal", "Yelandur"]
        },
        "Mandya": {
            "Mandya": ["Mandya Town", "Srirangapatna", "Pandavapura", "Krishnarajpet"],
            "Hassan": ["Hassan Town", "Arsikere", "Belur", "Chikmagalur"]
        },
        "Dharwad": {
            "Dharwad": ["Dharwad Town", "Hubli", "Kundgol", "Navalgund"],
            "Gadag": ["Gadag Town", "Betageri", "Nargund", "Lakshmeshwar"]
        },
        "Belgaum": {
            "Belgaum": ["Belgaum Town", "Dharwad", "Saundatti", "Hukkeri"],
            "Bagalkot": ["Bagalkot Town", "Bilgi", "Jamkhandi", "Mudhol"]
        },
        "Gulbarga": {
            "Gulbarga": ["Gulbarga Town", "Yadgir", "Shahpur", "Chincholi"],
            "Bidar": ["Bidar Town", "Basavakalyan", "Bhalki", "Humnabad"]
        },
        "Shimoga": {
            "Shimoga": ["Shimoga Town", "Bhadravati", "Sagar", "Tirthahalli"],
            "Chickmagalur": ["Chickmagalur Town", "Kadur", "Mudigere", "Tarikere"]
        },
        "Davangere": {
            "Davangere": ["Davangere Town", "Harihar", "Harpanahalli", "Channagiri"],
            "Chitradurga": ["Chitradurga Town", "Hiriyur", "Holalkere", "Molakalmuru"]
        },
        "Raichur": {
            "Raichur": ["Raichur Town", "Manvi", "Yadgir", "Sedam"],
            "Bellary": ["Bellary Town", "Hospet", "Sandur", "Kudligi"]
        },
        "Udupi": {
            "Udupi": ["Udupi Town", "Karkala", "Kapu", "Brahmavara"],
            "Dakshina Kannada": ["Mangalore Town", "Puttur", "Sullia", "Bantwal"]
        }
    },
    "Maharashtra": {
        "Pune": {
            "Pune City": ["Shivajinagar", "Kothrud", "Hadapsar", "Wanowrie"],
            "Pune Rural": ["Indapur", "Baramati", "Saswad", "Purandar"],
            "Baramati": ["Baramati Town", "Indapur", "Daund", "Bhor"]
        },
        "Mumbai": {
            "Mumbai City": ["Andheri", "Bandra", "Dadar", "Colaba"],
            "Mumbai Suburban": ["Borivali", "Malad", "Kurla", "Goregaon"],
            "Thane": ["Thane City", "Kalyan", "Dombivli", "Ulhasnagar"]
        },
        "Nagpur": {
            "Nagpur": ["Nagpur City", "Wardha", "Ramtek", "Katol"],
            "Chandrapur": ["Chandrapur Town", "Ballarpur", "Warora", "Brahmapuri"]
        },
        "Nashik": {
            "Nashik": ["Nashik City", "Malegaon", "Sinnar", "Igatpuri"],
            "Dhule": ["Dhule Town", "Nandurbar", "Shirpur", "Pusad"]
        },
        "Kolhapur": {
            "Kolhapur": ["Kolhapur City", "Ichalkaranji", "Hatkanangle", "Gadhinglaj"],
            "Sangli": ["Sangli Town", "Miraj", "Wai", "Tasgaon"]
        },
        "Aurangabad": {
            "Aurangabad": ["Aurangabad City", "Jalna", "Beed", "Parbhani"],
            "Latur": ["Latur Town", "Osmanabad", "Nanded", "Hingoli"]
        },
        "Solapur": {
            "Solapur": ["Solapur City", "Pandharpur", "Sangole", "Mangalvedhe"],
            "Satara": ["Satara Town", "Karad", "Wai", "Khed"]
        },
        "Amravati": {
            "Amravati": ["Amravati City", "Akola", "Buldhana", "Washim"],
            "Akola": ["Akola Town", "Akot", "Washim", "Patur"]
        },
        "Jalgaon": {
            "Jalgaon": ["Jalgaon Town", "Bhusawal", "Chalisgaon", "Yawal"],
            "Dhule": ["Dhule Town", "Nandurbar", "Shirpur", "Pusad"]
        }
    },
    "Tamil Nadu": {
        "Chennai": {
            "Chennai": ["T. Nagar", "Adyar", "Anna Nagar", "Mylapore"],
            "Kancheepuram": ["Kancheepuram Town", "Sriperumbudur", "Uthiramerur", "Kundrathur"],
            "Tiruvallur": ["Tiruvallur Town", "Poonamallee", "Ambattur", "Avadi"]
        },
        "Coimbatore": {
            "Coimbatore": ["Coimbatore City", "Mettupalayam", "Pollachi", "Sulur"],
            "Tiruppur": ["Tiruppur Town", "Kangeyam", "Dharapuram", "Udumalpet"]
        },
        "Madurai": {
            "Madurai": ["Madurai City", "Melur", "Vadipatti", "Usilampatti"],
            "Dindigul": ["Dindigul Town", "Palani", "Oddanchatram", "Kodaikanal"]
        },
        "Salem": {
            "Salem": ["Salem City", "Attur", "Mettur", "Omalur"],
            "Namakkal": ["Namakkal Town", "Rasipuram", "Tiruchengode", "Paramathi"]
        },
        "Tiruchirappalli": {
            "Tiruchirappalli": ["Trichy City", "Lalgudi", "Musiri", "Thuraiyur"],
            "Karur": ["Karur Town", "Kulithalai", "Krishnarayapuram", "Aravakurichi"]
        },
        "Thanjavur": {
            "Thanjavur": ["Thanjavur Town", "Kumbakonam", "Papanasam", "Pattukkottai"],
            "Thiruvarur": ["Thiruvarur Town", "Mannargudi", "Nannilam", "Needamangalam"]
        },
        "Erode": {
            "Erode": ["Erode City", "Gobichettipalayam", "Bhavani", "Sathyamangalam"],
            "Nilgiris": ["Udhagamandalam", "Coonoor", "Kotagiri", "Gudalur"]
        },
        "Vellore": {
            "Vellore": ["Vellore City", "Gudiyatham", "Arni", "Arcot"],
            "Krishnagiri": ["Krishnagiri Town", "Hosur", "Pochampalli", "Uthangarai"]
        }
    },
    "Madhya Pradesh": {
        "Bhopal": {
            "Bhopal": ["Bhopal City", "Huzur", "Berasia", "Kolar"],
            "Raisen": ["Raisen Town", "Sanchi", "Begamganj", "Goharganj"]
        },
        "Indore": {
            "Indore": ["Indore City", "Mhow", "Depalpur", "Sanwer"],
            "Dhar": ["Dhar Town", "Khandwa", "Barwani", "Manawar"]
        },
        "Jabalpur": {
            "Jabalpur": ["Jabalpur City", "Panagar", "Shahpura", "Mandla"],
            "Narsinghpur": ["Narsinghpur Town", "Kareli", "Tendukheda", "Gotegaon"]
        },
        "Gwalior": {
            "Gwalior": ["Gwalior City", "Dabra", "Bhitarwar", "Chiromi"],
            "Datia": ["Datia Town", "Seondha", "Bhander", "Indergarh"]
        },
        "Ujjain": {
            "Ujjain": ["Ujjain City", "Mahidpur", "Tarana", "Badnagar"],
            "Dewas": ["Dewas Town", "Sonkatch", "Khategaon", "Bagli"]
        },
        "Sagar": {
            "Sagar": ["Sagar City", "Khurai", "Rahatgarh", "Banda"],
            "Damoh": ["Damoh Town", "Patharia", "Hata", "Jabalpur"]
        },
        "Satna": {
            "Satna": ["Satna Town", "Maihar", "Amarpatan", "Nagod"],
            "Rewa": ["Rewa Town", "Mauganj", "Sirmaur", "Teonthar"]
        },
        "Chhindwara": {
            "Chhindwara": ["Chhindwara Town", "Parasia", "Amarwara", "Chourai"],
            "Betul": ["Betul Town", "Amla", "Bhainsdehi", "Multai"]
        },
        "Balaghat": {
            "Balaghat": ["Balaghat Town", "Katangi", "Baihar", "Lanji"],
            "Seoni": ["Seoni Town", "Lakhnadon", "Keolari", "Barghat"]
        }
    },
    "Rajasthan": {
        "Jaipur": {
            "Jaipur": ["Jaipur City", "Amber", "Jhotwara", "Sanganer"],
            "Dausa": ["Dausa Town", "Bandikui", "Lalsot", "Mahwa"]
        },
        "Jodhpur": {
            "Jodhpur": ["Jodhpur City", "Shergarh", "Bhopalgarh", "Bilara"],
            "Pali": ["Pali Town", "Jaitaran", "Sojat", "Marwar Junction"]
        },
        "Udaipur": {
            "Udaipur": ["Udaipur City", "Salumbar", "Gogunda", "Mavli"],
            "Chittorgarh": ["Chittorgarh Town", "Nimbahera", "Begun", "Rawatbhata"]
        },
        "Kota": {
            "Kota": ["Kota City", "Baran", "Anta", "Kotri"],
            "Baran": ["Baran Town", "Atru", "Kishanganj", "Shahbad"]
        },
        "Ajmer": {
            "Ajmer": ["Ajmer City", "Kishangarh", "Beawar", "Nasirabad"],
            "Bhilwara": ["Bhilwara Town", "Mandalia", "Sahpura", "Hamirpur"]
        },
        "Alwar": {
            "Alwar": ["Alwar Town", "Bharatpur", "Kathumar", "Neemrana"],
            "Bharatpur": ["Bharatpur Town", "Deeg", "Kumher", "Nagar"]
        },
        "Sikar": {
            "Sikar": ["Sikar Town", "Laxmangarh", "Fatehpur", "Shrimadhopur"],
            "Jhunjhunu": ["Jhunjhunu Town", "Chirawa", "Nawalgarh", "Malsisar"]
        },
        "Jalore": {
            "Jalore": ["Jalore Town", "Sanchore", "Raniwara", "Bhinmal"],
            "Barmer": ["Barmer Town", "Balotra", "Sheo", "Pachpadra"]
        },
        "Bikaner": {
            "Bikaner": ["Bikaner City", "Lunkaransar", "Kolayat", "Nokha"],
            "Churu": ["Churu Town", "Sardarshahar", "Ratangarh", "Taranagar"]
        },
        "Kota": {
            "Kota": ["Kota City", "Baran", "Anta", "Kotri"],
            "Jhalawar": ["Jhalawar Town", "Aklera", "Jhalarapatan", "Bhawani Mandi"]
        }
    },
    "Gujarat": {
        "Ahmedabad": {
            "Ahmedabad": ["Ahmedabad City", "Daskroi", "Dholka", "Sanand"],
            "Gandhinagar": ["Gandhinagar City", "Kalol", "Mansa", "Dahegam"]
        },
        "Surat": {
            "Surat": ["Surat City", "Choryasi", "Bardoli", "Mahuva"],
            "Bharuch": ["Bharuch Town", "Ankleshwar", "Jhagadia", "Valsad"]
        },
        "Vadodara": {
            "Vadodara": ["Vadodara City", "Padra", "Savli", "Karjan"],
            "Anand": ["Anand Town", "Nadiad", "Khambhat", "Borsad"]
        },
        "Rajkot": {
            "Rajkot": ["Rajkot City", "Gondal", "Jetpur", "Dhoraji"],
            "Jamnagar": ["Jamnagar Town", "Dwarka", "Bhanvad", "Kalavad"]
        },
        "Junagadh": {
            "Junagadh": ["Junagadh Town", "Mangrol", "Veraval", "Kodinar"],
            "Amreli": ["Amreli Town", "Bhavnagar", "Gondal", "Lathi"]
        },
        "Gandhinagar": {
            "Gandhinagar": ["Gandhinagar City", "Kalol", "Mansa", "Dehgam"],
            "Mehsana": ["Mehsana Town", "Unjha", "Visnagar", "Kadi"]
        },
        "Bharuch": {
            "Bharuch": ["Bharuch Town", "Ankleshwar", "Jhagadia", "Rajpipla"],
            "Narmada": ["Rajpipla Town", "Nandod", "Dediapada", "Tilakwada"]
        },
        "Patan": {
            "Patan": ["Patan Town", "Sidhpur", "Harij", "Santalpur"],
            "Mehsana": ["Mehsana Town", "Unjha", "Visnagar", "Kadi"]
        }
    },
    "Uttar Pradesh": {
        "Lucknow": {
            "Lucknow": ["Lucknow City", "Mohanlalganj", "Malihabad", "Bakshi Ka Tabil"],
            "Unnao": ["Unnao Town", "Purwa", "Safipur", "Bichia"]
        },
        "Agra": {
            "Agra": ["Agra City", "Fatehpur Sikri", "Kiraoli", "Khairagarh"],
            "Firozabad": ["Firozabad Town", "Shikohabad", "Tundla", "Jasrana"]
        },
        "Varanasi": {
            "Varanasi": ["Varanasi City", "Cholapur", "Araziline", "Sarnath"],
            "Jaunpur": ["Jaunpur Town", "Shahganj", "Machhlishahr", "Kerakat"]
        },
        "Meerut": {
            "Meerut": ["Meerut City", "Muzaffarnagar", "Baghpat", "Ghaziabad"],
            "Ghaziabad": ["Ghaziabad City", "Indirapuram", "Kaushambi", "Vaishali"]
        },
        "Allahabad": {
            "Allahabad": ["Allahabad City", "Phulpur", "Soraon", "Karchana"],
            "Fatehpur": ["Fatehpur Town", "Bindki", "Khaga", "Jahanabad"]
        },
        "Kanpur": {
            "Kanpur": ["Kanpur City", "Kanpur Dehat", "Akbarpur", "Bilhaur"],
            "Kanpur Dehat": ["Akbarpur Town", "Bilhaur", "Rasulabad", "Bhognipur"]
        },
        "Gorakhpur": {
            "Gorakhpur": ["Gorakhpur City", "Cantonment", "Sahjanwa", "Chauri Chaura"],
            "Maharajganj": ["Maharajganj Town", "Nautanwa", "Pharenda", "Siswa Bazar"]
        },
        "Azamgarh": {
            "Azamgarh": ["Azamgarh Town", "Mau", "Ballia", "Bansdih"],
            "Mau": ["Mau Town", "Madhuban", "Ratanpura", "Ghosi"]
        },
        "Bareilly": {
            "Bareilly": ["Bareilly City", "Aonla", "Baheri", "Meerganj"],
            "Budaun": ["Budaun Town", "Bisauli", "Sahaswan", "Gunnaur"]
        },
        "Noida": {
            "Gautam Buddh Nagar": ["Noida", "Greater Noida", "Dadri", "Jewar"],
            "Ghaziabad": ["Ghaziabad City", "Indirapuram", "Vaishali", "Kaushambi"]
        }
    },
    "West Bengal": {
        "Kolkata": {
            "Kolkata": ["Kolkata City", "Alipore", "Salt Lake", "Howrah"],
            "Howrah": ["Howrah Town", "Uluberia", "Shyampur", "Bagnan"]
        },
        "Bardhaman": {
            "Bardhaman": ["Bardhaman Town", "Durgapur", "Asansol", "Katwa"],
            "Birbhum": ["Suri Town", "Rampurhat", "Bolpur", "Nanoor"]
        },
        "Murshidabad": {
            "Murshidabad": ["Berhampore Town", "Jiagunj", "Lalbagh", "Bharatpur"],
            "Nadia": ["Krishnanagar Town", "Ranaghat", "Kalyani", "Tehatta"]
        },
        "Birbhum": {
            "Birbhum": ["Suri Town", "Rampurhat", "Bolpur", "Nanoor"],
            "Bardhaman": ["Bardhaman Town", "Durgapur", "Asansol", "Katwa"]
        },
        "24 Parganas": {
            "North 24 Parganas": ["Baranagar", "Barrackpore", "Basirhat", "Bangur"],
            "South 24 Parganas": ["Alipore", "Diamond Harbour", "Canning", "Baruipur"]
        },
        "Medinipur": {
            "West Medinipur": ["Medinipur Town", "Kharagpur", "Jhargram", "Keshiary"],
            "East Medinipur": ["Tamluk Town", "Haldia", "Contai", "Digha"]
        }
    },
    "Punjab": {
        "Ludhiana": {
            "Ludhiana": ["Ludhiana City", "Samrala", "Khanna", "Raikot"],
            "Jalandhar": ["Jalandhar City", "Phillaur", "Nakodar", "Lohian Khas"]
        },
        "Amritsar": {
            "Amritsar": ["Amritsar City", "Tarn Taran", "Ajnala", "Patti"],
            "Tarn Taran": ["Tarn Taran Town", "Patti", "Khadur Sahib", "Bhikhiwind"]
        },
        "Patiala": {
            "Patiala": ["Patiala City", "Rajpura", "Samana", "Nabha"],
            "Sangrur": ["Sangrur Town", "Sunam", "Dhuri", "Lehra Gaga"]
        },
        "Bathinda": {
            "Bathinda": ["Bathinda Town", "Mansa", "Muktsar", "Faridkot"],
            "Mansa": ["Mansa Town", "Budhlada", "Sardulgarh", "Jhunir"]
        },
        "Gurdaspur": {
            "Gurdaspur": ["Gurdaspur Town", "Batala", "Dinanagar", "Pathankot"],
            "Hoshiarpur": ["Hoshiarpur Town", "Dasuya", "Mukerian", "Tanda Urmur"]
        },
        "Kapurthala": {
            "Kapurthala": ["Kapurthala Town", "Jalandhar", "Phagwara", "Nakodar"],
            "Jalandhar": ["Jalandhar City", "Phillaur", "Nakodar", "Lohian Khas"]
        }
    },
    "Bihar": {
        "Patna": {
            "Patna": ["Patna City", "Danapur", "Khagaul", "Phulwari Sharif"],
            "Nalanda": ["Biharsharif Town", "Rajgir", "Hilsa", "Ekangarsarai"]
        },
        "Gaya": {
            "Gaya": ["Gaya Town", "Bodh Gaya", "Tekari", "Belaganj"],
            "Nawada": ["Nawada Town", "Rajauli", "Hisua", "Kakolat"]
        },
        "Muzaffarpur": {
            "Muzaffarpur": ["Muzaffarpur Town", "Sitamarhi", "Sheohar", "Riga"],
            "Sitamarhi": ["Sitamarhi Town", "Dumra", "Pupri", "Bathnaha"]
        },
        "Bhagalpur": {
            "Bhagalpur": ["Bhagalpur Town", "Naugachia", "Kahalgaon", "Sultanganj"],
            "Munger": ["Munger Town", "Jamalpur", "Khagaria", "Begusarai"]
        },
        "Darbhanga": {
            "Darbhanga": ["Darbhanga Town", "Madhubani", "Rosera", "Benipur"],
            "Madhubani": ["Madhubani Town", "Jhanjharpur", "Lakhisarai", "Bibhutipur"]
        },
        "Vaishali": {
            "Vaishali": ["Hajipur Town", "Muzaffarpur", "Mahua", "Raghopur"],
            "Saran": ["Chapra Town", "Garkha", "Dighwara", "Marhaura"]
        }
    },
    "Odisha": {
        "Bhubaneswar": {
            "Khordha": ["Bhubaneswar City", "Jatni", "Banpur", "Tangi"],
            "Cuttack": ["Cuttack City", "Niali", "Tigiria", "Banki"]
        },
        "Cuttack": {
            "Cuttack": ["Cuttack City", "Niali", "Tigiria", "Banki"],
            "Jagatsinghpur": ["Jagatsinghpur Town", "Paradeep", "Tirtol", "Kujang"]
        },
        "Berhampur": {
            "Ganjam": ["Berhampur Town", "Chhatrapur", "Bhanjanagar", "Khinjili"],
            "Gajapati": ["Paralakhemundi Town", "Rayagada", "Mohana", "R Udaygiri"]
        },
        "Sambalpur": {
            "Sambalpur": ["Sambalpur Town", "Rengali", "Kuchinda", "Burla"],
            "Deogarh": ["Deogarh Town", "Talcher", "Angul", "Sambalpur"]
        },
        "Rourkela": {
            "Sundargarh": ["Rourkela Town", "Sundargarh", "Bonai", "Bisra"],
            "Jharsuguda": ["Jharsuguda Town", "Lakhanpur", "Belpahar", "Banharpali"]
        },
        "Balasore": {
            "Balasore": ["Balasore Town", "Soro", "Nilagiri", "Basta"],
            "Bhadrak": ["Bhadrak Town", "Dhamnagar", "Chandabali", "Tihidi"]
        }
    },
    "Jharkhand": {
        "Ranchi": {
            "Ranchi": ["Ranchi City", "Kanke", "Bundu", "Sonahatu"],
            "Hazaribag": ["Hazaribag Town", "Chatra", "Koderma", "Giridih"]
        },
        "Jamshedpur": {
            "East Singhbhum": ["Jamshedpur City", "Jadugora", "Musabani", "Potka"],
            "West Singhbhum": ["Chaibasa Town", "Chakradharpur", "Sonua", "Manoharpur"]
        },
        "Dhanbad": {
            "Dhanbad": ["Dhanbad Town", "Jharia", "Katras", "Bermo"],
            "Bokaro": ["Bokaro Town", "Chas", "Petarbar", "Pindra"]
        },
        "Gumla": {
            "Gumla": ["Gumla Town", "Lohardaga", "Torpa", "Kurdeg"],
            "Lohardaga": ["Lohardaga Town", "Bhandra", "Kuru", "Sisai"]
        },
        "Deoghar": {
            "Deoghar": ["Deoghar Town", "Madhupur", "Jamtara", "Nirsa"],
            "Dumka": ["Dumka Town", "Masalia", "Jarmundi", "Gopikandar"]
        },
        "Hazaribag": {
            "Hazaribag": ["Hazaribag Town", "Chatra", "Koderma", "Giridih"],
            "Koderma": ["Koderma Town", "Jainagar", "Domchanch", "Markacho"]
        }
    },
    "Chhattisgarh": {
        "Raipur": {
            "Raipur": ["Raipur City", "Arang", "Abhanpur", "Tilda"],
            "Durg": ["Durg Town", "Bhilai", "Rajnandgaon", "Kumhari"]
        },
        "Bilaspur": {
            "Bilaspur": ["Bilaspur Town", "Bhatapara", "Masturi", "Takhatpur"],
            "Korba": ["Korba Town", "Katghora", "Pali", "Khunti"]
        },
        "Ambikapur": {
            "Surguja": ["Ambikapur Town", "Lakhanpur", "Ramanujganj", "Manendragarh"],
            "Jashpur": ["Jashpur Town", "Pathalgaon", "Kunkuri", "Tapkara"]
        },
        "Dantewada": {
            "Dantewada": ["Dantewada Town", "Bacheli", "Dornapal", "Geedam"],
            "Bastar": ["Jagdalpur Town", "Bastar", "Dantewada", "Kondagaon"]
        },
        "Korba": {
            "Korba": ["Korba Town", "Katghora", "Pali", "Khunti"],
            "Bilaspur": ["Bilaspur Town", "Bhatapara", "Masturi", "Takhatpur"]
        }
    },
    "Kerala": {
        "Thiruvananthapuram": {
            "Thiruvananthapuram": ["Thiruvananthapuram City", "Neyyattinkara", "Attingal", "Varkala"],
            "Kollam": ["Kollam Town", "Punalur", "Karunagappally", "Kottarakkara"]
        },
        "Kochi": {
            "Ernakulam": ["Kochi City", "Aluva", "Perumbavoor", "Muvattupuzha"],
            "Thrissur": ["Thrissur Town", "Chalakudy", "Kodungallur", "Mukundapuram"]
        },
        "Kozhikode": {
            "Kozhikode": ["Kozhikode City", "Vadakara", "Koyilandy", "Feroke"],
            "Malappuram": ["Malappuram Town", "Manjeri", "Perinthalmanna", "Tirur"]
        },
        "Palakkad": {
            "Palakkad": ["Palakkad Town", "Ottapalam", "Chittur", "Mannarkkad"],
            "Malappuram": ["Malappuram Town", "Manjeri", "Perinthalmanna", "Tirur"]
        },
        "Kottayam": {
            "Kottayam": ["Kottayam Town", "Changanassery", "Pala", "Ettumanoor"],
            "Pathanamthitta": ["Pathanamthitta Town", "Pandalam", "Thiruvalla", "Ranni"]
        },
        "Idukki": {
            "Idukki": ["Idukki Town", "Munnar", "Adoor", "Kattappana"],
            "Wayanad": ["Kalpetta Town", "Mananthavady", "Sulthan Bathery", "Vythiri"]
        }
    },
    "Haryana": {
        "Gurgaon": {
            "Gurgaon": ["Gurgaon City", "Sohna", "Pataudi", "Farrukhnagar"],
            "Faridabad": ["Faridabad Town", "Palwal", "Hathin", "Nagina"]
        },
        "Ambala": {
            "Ambala": ["Ambala City", "Ambala Cantt", "Shahzadpur", "Naraingarh"],
            "Yamunanagar": ["Yamunanagar Town", "Sadhaura", "Chhachhrauli", "Mustafabad"]
        },
        "Karnal": {
            "Karnal": ["Karnal Town", "Assandh", "Gharaunda", "Nilokheri"],
            "Panipat": ["Panipat Town", "Samalkha", "Israna", "Baprola"]
        },
        "Hisar": {
            "Hisar": ["Hisar Town", "Adampur", "Hansi", "Uklana"],
            "Sirsa": ["Sirsa Town", "Dabwali", "Rania", "Kalanwali"]
        },
        "Rohtak": {
            "Rohtak": ["Rohtak City", "Bahadurgarh", "Jhajjar", "Meham"],
            "Jhajjar": ["Jhajjar Town", "Beri", "Salhawas", "Dadri"]
        },
        "Kurukshetra": {
            "Kurukshetra": ["Kurukshetra Town", "Thanesar", "Pehowa", "Shahabad"],
            "Kaithal": ["Kaithal Town", "Guhla", "Pundri", "Rajaund"]
        }
    }
}


class ProfileUpdateRequest(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None
    profile_image: Optional[str] = None
    preferred_language: Optional[str] = None


class AddressRequest(BaseModel):
    address_line: Optional[str] = None
    village: Optional[str] = None
    mandal: Optional[str] = None
    district: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = "India"
    pincode: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class LoginRequest(BaseModel):
    phone_number: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    pin: Optional[str] = None
    password: Optional[str] = None
    farmer_id: Optional[str] = None
    login_method: Optional[str] = "phone"


class OTPRequest(BaseModel):
    phone_number: Optional[str] = None
    email: Optional[str] = None


class FarmerOTPRequest(BaseModel):
    farmer_id: str
    channel: str = "phone"


class FarmerOTPVerifyRequest(BaseModel):
    farmer_id: str
    channel: str = "phone"
    otp_code: str


class OTPVerifyRequest(BaseModel):
    phone_number: Optional[str] = None
    email: Optional[str] = None
    otp_code: str


class ForgotPinRequest(BaseModel):
    phone_number: Optional[str] = None
    email: Optional[str] = None
    new_pin: str


class ProfileLookupRequest(BaseModel):
    phone_number: Optional[str] = None
    email: Optional[str] = None
    farmer_id: Optional[str] = None


@router.post("/auth/register", response_model=dict, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    existing = db.query(User).filter(
        User.phone_number.in_(phone_lookup_candidates(payload.phone_number))
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Phone number already registered")

    if payload.email:
        email_exists = db.query(User).filter(User.email == payload.email).first()
        if email_exists:
            raise HTTPException(status_code=400, detail="Email already registered")

    farmer_id = generate_farmer_id(db)
    pin_value = payload.pin or payload.password
    if not pin_value:
        raise HTTPException(status_code=400, detail="PIN is required for registration")
    password_hash = hash_password(pin_value)

    user = User(
        farmer_id=farmer_id,
        full_name=payload.full_name,
        phone_number=payload.phone_number,
        email=payload.email,
        password_hash=password_hash,
        preferred_language=payload.preferred_language or "en",
        is_verified=False,
        is_active=True,
    )
    db.add(user)
    db.flush()

    profile = FarmerProfile(
        user_id=user.id,
        farmer_id=farmer_id,
        date_of_birth=payload.date_of_birth,
        gender=payload.gender,
        occupation="Farmer",
        farming_experience=payload.farming_experience,
        preferred_crops=payload.preferred_crops,
        aadhaar_number=payload.aadhaar_number,
        pan_number=payload.pan_number,
        irrigation_type=payload.irrigation_type,
    )
    db.add(profile)

    if payload.state or payload.district or payload.address_line or payload.pincode:
        address = UserAddress(
            user_id=user.id,
            address_line=payload.address_line,
            state=payload.state,
            district=payload.district,
            mandal=payload.mandal,
            village=payload.village,
            pincode=payload.pincode,
            country="India",
            is_primary=True,
        )
        db.add(address)

    from app.models.farm import Farm
    farm = Farm(
        user_id=user.id,
        farm_name=payload.farm_name or f"{payload.full_name.split()[0]}'s Farm",
        district=payload.district,
        mandal=payload.mandal,
        village=payload.village,
        state=payload.state,
        farm_type=payload.farm_type,
        total_area=payload.total_area,
        area_unit=payload.area_unit or "Acres",
        soil_type=payload.soil_type,
    )
    db.add(farm)
    db.flush()
    farm.farm_id = generate_id("FA-FARM", db, Farm)

    db.commit()
    db.refresh(user)

    token = create_access_token(data={"sub": user.id, "phone": user.phone_number})

    return {
        "status": "success",
        "message": "Registration successful",
        "data": {
            "farmer_id": farmer_id,
            "farm_id": farm.farm_id,
            "access_token": token,
            "token_type": "bearer",
            "user": UserResponse.model_validate(user).model_dump(),
        },
    }


@router.post("/auth/send-otp", response_model=dict)
def send_otp(payload: OTPRequest, db: Session = Depends(get_db)):
    if not payload.phone_number and not payload.email:
        raise HTTPException(status_code=400, detail="Phone number or email required")

    otp_code = f"{random.randint(0, 9999):04d}"
    otp_hash = hash_password(otp_code)
    expires_at = datetime.utcnow() + timedelta(minutes=10)

    user = None
    if payload.phone_number:
        user = db.query(User).filter(
            User.phone_number.in_(phone_lookup_candidates(payload.phone_number))
        ).first()
    elif payload.email:
        user = db.query(User).filter(User.email == payload.email).first()

    otp_record = OTPVerification(
        user_id=user.id if user else None,
        phone=payload.phone_number or "",
        email=payload.email,
        otp_hash=otp_hash,
        expires_at=expires_at,
    )
    db.add(otp_record)
    db.commit()

    # Development/Test mode: expose the OTP in the API response so the app can
    # display it inside the UI for easy testing. Automatically disabled when a
    # real SMS or email provider is configured.
    real_provider_configured = bool(
        settings.SMS_API_KEY or (settings.SMTP_HOST and settings.SMTP_USER)
    )
    response = {
        "status": "success",
        "message": "OTP sent successfully",
        "expires_in_seconds": 600,
    }
    if settings.DEBUG and not real_provider_configured:
        response["debug_otp"] = otp_code
        response["debug_mode"] = True

    return response


@router.post("/auth/send-farmer-otp", response_model=dict)
def send_farmer_otp(payload: FarmerOTPRequest, db: Session = Depends(get_db)):
    normalized_farmer_id = normalize_farmer_id(payload.farmer_id)
    user = db.query(User).filter(User.farmer_id == normalized_farmer_id).first()
    if not user:
        digits = ''.join(ch for ch in str(payload.farmer_id) if ch.isdigit())
        if digits:
            normalized_candidate = f"FA-AS-{digits.zfill(8)}"
            user = db.query(User).filter(User.farmer_id == normalized_candidate).first()
    if not user:
        raise HTTPException(status_code=404, detail="Farmer ID not found")

    channel = (payload.channel or "phone").lower()
    if channel not in ("phone", "email"):
        raise HTTPException(status_code=400, detail="Channel must be 'phone' or 'email'")

    phone = user.phone_number
    email = user.email
    if channel == "phone" and not phone:
        raise HTTPException(status_code=400, detail="No registered phone number found")
    if channel == "email" and not email:
        raise HTTPException(status_code=400, detail="No registered email found")

    otp_code = f"{random.randint(0, 9999):04d}"
    otp_hash = hash_password(otp_code)
    expires_at = datetime.utcnow() + timedelta(minutes=10)

    otp_record = OTPVerification(
        user_id=user.id,
        phone=phone if channel == "phone" else "",
        email=email if channel == "email" else None,
        otp_hash=otp_hash,
        expires_at=expires_at,
    )
    db.add(otp_record)
    db.commit()

    masked = None
    if channel == "phone" and phone and len(phone) >= 5:
        masked = phone[:3] + "****" + phone[-2:]
    elif channel == "email" and email and "@" in email:
        masked = email[:2] + "***@" + email.split("@")[1]

    real_provider_configured = bool(
        settings.SMS_API_KEY or (settings.SMTP_HOST and settings.SMTP_USER)
    )
    response = {
        "status": "success",
        "message": "OTP sent successfully",
        "channel": channel,
        "masked": masked,
        "expires_in_seconds": 600,
    }
    if settings.DEBUG and not real_provider_configured:
        response["debug_otp"] = otp_code
        response["debug_mode"] = True

    return response


@router.post("/auth/verify-farmer-otp", response_model=dict)
def verify_farmer_otp(payload: FarmerOTPVerifyRequest, db: Session = Depends(get_db)):
    normalized_farmer_id = normalize_farmer_id(payload.farmer_id)
    user = db.query(User).filter(User.farmer_id == normalized_farmer_id).first()
    if not user:
        digits = ''.join(ch for ch in str(payload.farmer_id) if ch.isdigit())
        if digits:
            normalized_candidate = f"FA-AS-{digits.zfill(8)}"
            user = db.query(User).filter(User.farmer_id == normalized_candidate).first()
    if not user:
        raise HTTPException(status_code=404, detail="Farmer ID not found")

    channel = (payload.channel or "phone").lower()
    lookup_phone = user.phone_number if channel == "phone" else None
    lookup_email = user.email if channel == "email" else None

    q = db.query(OTPVerification).filter(
        OTPVerification.verified_at.is_(None),
        OTPVerification.expires_at > datetime.utcnow(),
    )
    if lookup_phone:
        q = q.filter(OTPVerification.phone == lookup_phone)
    if lookup_email:
        q = q.filter(OTPVerification.email == lookup_email)

    otp_record = q.order_by(OTPVerification.created_at.desc()).first()
    if not otp_record:
        raise HTTPException(status_code=400, detail="Invalid or expired OTP")
    if otp_record.attempts >= 5:
        raise HTTPException(status_code=400, detail="Too many attempts. Request a new OTP.")

    otp_record.attempts += 1
    if not verify_password(payload.otp_code, otp_record.otp_hash):
        db.commit()
        raise HTTPException(status_code=400, detail="Incorrect OTP")

    otp_record.verified_at = datetime.utcnow()
    otp_record.user_id = user.id
    user.is_verified = True
    db.commit()

    token = create_access_token(data={"sub": user.id, "phone": user.phone_number})
    return {
        "status": "success",
        "message": "OTP verified successfully",
        "data": {
            "access_token": token,
            "token_type": "bearer",
            "user": UserResponse.model_validate(user).model_dump(),
            "is_existing_user": True,
        },
    }


@router.post("/auth/verify-otp", response_model=dict)
def verify_otp(payload: OTPVerifyRequest, db: Session = Depends(get_db)):
    lookup_phone = payload.phone_number
    lookup_email = payload.email

    if not lookup_phone and not lookup_email:
        raise HTTPException(status_code=400, detail="Phone number or email required")

    q = db.query(OTPVerification).filter(
        OTPVerification.verified_at.is_(None),
        OTPVerification.expires_at > datetime.utcnow(),
    )
    if lookup_phone:
        q = q.filter(OTPVerification.phone == lookup_phone)
    if lookup_email:
        q = q.filter(OTPVerification.email == lookup_email)

    otp_record = q.order_by(OTPVerification.created_at.desc()).first()
    if not otp_record:
        raise HTTPException(status_code=400, detail="Invalid or expired OTP")

    if otp_record.attempts >= 5:
        raise HTTPException(status_code=400, detail="Too many attempts. Request a new OTP.")

    otp_record.attempts += 1
    if not verify_password(payload.otp_code, otp_record.otp_hash):
        db.commit()
        raise HTTPException(status_code=400, detail="Incorrect OTP")

    otp_record.verified_at = datetime.utcnow()

    user = None
    if lookup_phone:
        user = db.query(User).filter(
            User.phone_number.in_(phone_lookup_candidates(lookup_phone))
        ).first()
    elif lookup_email:
        user = db.query(User).filter(User.email == lookup_email).first()

    if user:
        user.is_verified = True
        otp_record.user_id = user.id

    db.commit()

    token = None
    if user:
        token = create_access_token(data={"sub": user.id, "phone": user.phone_number})

    return {
        "status": "success",
        "message": "OTP verified successfully",
        "data": {
            "access_token": token,
            "token_type": "bearer" if token else None,
            "user": UserResponse.model_validate(user).model_dump() if user else None,
            "is_existing_user": user is not None,
        },
    }


@router.post("/auth/login", response_model=dict)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = None

    if payload.farmer_id:
        normalized_farmer_id = normalize_farmer_id(payload.farmer_id)
        candidates = {normalized_farmer_id}
        if payload.farmer_id:
            digits = ''.join(ch for ch in str(payload.farmer_id) if ch.isdigit())
            if digits:
                candidates.add(f"FA-AS-{digits.zfill(8)}")
                candidates.add(digits)
        user = db.query(User).filter(User.farmer_id.in_(list(candidates))).first()
        if not user:
            raise HTTPException(status_code=401, detail="Farmer ID not found")
        pin = payload.pin or payload.password
        if not pin or not user.password_hash or not verify_password(pin, user.password_hash):
            raise HTTPException(status_code=401, detail="Invalid PIN")
    elif payload.email:
        user = db.query(User).filter(User.email == payload.email).first()
        if not user:
            raise HTTPException(status_code=401, detail="Email not found")
        pin = payload.pin or payload.password
        if not pin or not user.password_hash or not verify_password(pin, user.password_hash):
            raise HTTPException(status_code=401, detail="Invalid PIN")
    elif payload.phone_number or payload.phone:
        phone_input = payload.phone_number or payload.phone
        user = db.query(User).filter(
            User.phone_number.in_(phone_lookup_candidates(phone_input))
        ).first()
        if not user:
            raise HTTPException(status_code=401, detail="Phone number not found")
        pwd = payload.pin or payload.password
        if not pwd or not user.password_hash or not verify_password(pwd, user.password_hash):
            raise HTTPException(status_code=401, detail="Invalid PIN/Password")
    else:
        raise HTTPException(status_code=400, detail="Phone, email, or Farmer ID required")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is deactivated")

    token = create_access_token(data={"sub": user.id, "phone": user.phone_number})

    login_entry = LoginHistory(user_id=user.id)
    db.add(login_entry)
    db.commit()

    profile_data = UserResponse.model_validate(user).model_dump()
    address = db.query(UserAddress).filter(
        UserAddress.user_id == user.id, UserAddress.is_primary == True
    ).first()
    if address:
        profile_data["address"] = {
            "address_line": address.address_line,
            "state": address.state,
            "district": address.district,
            "mandal": address.mandal,
            "village": address.village,
            "pincode": address.pincode,
        }
    farmer_profile = db.query(FarmerProfile).filter(FarmerProfile.user_id == user.id).first()
    if farmer_profile:
        profile_data["farmer_profile"] = {
            "date_of_birth": farmer_profile.date_of_birth,
            "gender": farmer_profile.gender,
            "farming_experience": farmer_profile.farming_experience,
            "preferred_crops": farmer_profile.preferred_crops,
            "aadhaar_number": farmer_profile.aadhaar_number,
            "pan_number": farmer_profile.pan_number,
            "irrigation_type": farmer_profile.irrigation_type,
        }

    return {
        "status": "success",
        "data": {
            "access_token": token,
            "token_type": "bearer",
            "user": profile_data,
        },
    }


@router.post("/auth/forgot-pin", response_model=dict)
def forgot_pin(payload: ForgotPinRequest, db: Session = Depends(get_db)):
    if not payload.phone_number and not payload.email:
        raise HTTPException(status_code=400, detail="Phone number or email required")

    user = None
    if payload.phone_number:
        user = db.query(User).filter(
            User.phone_number.in_(phone_lookup_candidates(payload.phone_number))
        ).first()
    elif payload.email:
        user = db.query(User).filter(User.email == payload.email).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    latest_otp = None
    q = db.query(OTPVerification).filter(
        OTPVerification.verified_at.isnot(None),
    )
    if payload.phone_number:
        q = q.filter(OTPVerification.phone == payload.phone_number)
    elif payload.email:
        q = q.filter(OTPVerification.email == payload.email)
    latest_otp = q.order_by(OTPVerification.created_at.desc()).first()

    if not latest_otp:
        raise HTTPException(status_code=400, detail="Please verify OTP first before changing PIN")

    # Security: the verified OTP must belong to the same user, be unexpired, and be fresh
    # (verified within the last 10 minutes) to prevent PIN reset via a stale/foreign OTP.
    now = datetime.utcnow()
    expires_at = latest_otp.expires_at
    if expires_at.tzinfo is not None:
        now_aware = now.replace(tzinfo=expires_at.tzinfo)
        expired = now_aware > expires_at
    else:
        expired = now > expires_at
    if latest_otp.user_id and latest_otp.user_id != user.id:
        raise HTTPException(status_code=403, detail="OTP does not belong to this account")
    if expired:
        raise HTTPException(status_code=400, detail="OTP has expired. Please request a new one.")
    if latest_otp.verified_at:
        if latest_otp.verified_at.tzinfo is not None:
            v_now = now.replace(tzinfo=latest_otp.verified_at.tzinfo)
            fresh = (v_now - latest_otp.verified_at).total_seconds() <= 600
        else:
            fresh = (now - latest_otp.verified_at).total_seconds() <= 600
        if not fresh:
            raise HTTPException(
                status_code=400,
                detail="OTP verification too old. Please verify a new OTP to change PIN.",
            )

    user.password_hash = hash_password(payload.new_pin)
    db.commit()

    return {
        "status": "success",
        "message": "PIN reset successfully. Please login with new PIN.",
    }


@router.post("/auth/lookup-profile", response_model=dict)
def lookup_profile(payload: ProfileLookupRequest, db: Session = Depends(get_db)):
    user = None
    if payload.phone_number:
        user = db.query(User).filter(
            User.phone_number.in_(phone_lookup_candidates(payload.phone_number))
        ).first()
    elif payload.email:
        user = db.query(User).filter(User.email == payload.email).first()
    elif payload.farmer_id:
        normalized = normalize_farmer_id(payload.farmer_id)
        candidates = {normalized}
        digits = ''.join(ch for ch in str(payload.farmer_id) if ch.isdigit())
        if digits:
            candidates.add(f"FA-AS-{digits.zfill(8)}")
            candidates.add(digits)
        user = db.query(User).filter(User.farmer_id.in_(list(candidates))).first()

    if not user:
        return {
            "status": "success",
            "data": None,
            "message": "No account found",
        }

    return {
        "status": "success",
        "data": {
            "full_name": user.full_name,
            "farmer_id": user.farmer_id,
            "profile_image": user.profile_image,
            "phone_masked": user.phone_number[:3] + "****" + user.phone_number[-2:] if user.phone_number and len(user.phone_number) >= 5 else None,
            "email_masked": user.email[:2] + "***@" + user.email.split("@")[1] if user.email and "@" in user.email else None,
        },
        "message": "Profile found",
    }


@router.post("/auth/logout", response_model=dict)
def logout(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    login_entry = (
        db.query(LoginHistory)
        .filter(LoginHistory.user_id == current_user.id, LoginHistory.logout_time.is_(None))
        .order_by(LoginHistory.login_time.desc())
        .first()
    )
    if login_entry:
        login_entry.logout_time = datetime.utcnow()
        db.commit()

    return {"status": "success", "message": "Logged out successfully"}


@router.get("/auth/me", response_model=dict)
def get_me(current_user: User = Depends(get_current_user)):
    profile_data = UserResponse.model_validate(current_user).model_dump()
    address = None
    farmer_profile = None
    try:
        address = current_user.addresses[0] if current_user.addresses else None
    except Exception:
        pass
    try:
        farmer_profile = current_user.farmer_profile
    except Exception:
        pass

    if address:
        profile_data["address"] = {
            "address_line": address.address_line,
            "village": address.village,
            "mandal": address.mandal,
            "district": address.district,
            "state": address.state,
            "country": address.country,
            "pincode": address.pincode,
            "latitude": address.latitude,
            "longitude": address.longitude,
        }
    if farmer_profile:
        profile_data["farmer_profile"] = {
            "date_of_birth": farmer_profile.date_of_birth,
            "gender": farmer_profile.gender,
            "occupation": farmer_profile.occupation,
            "farming_experience": farmer_profile.farming_experience,
            "preferred_crops": farmer_profile.preferred_crops,
        }

    return {
        "status": "success",
        "data": profile_data,
    }


@router.put("/auth/change-pin", response_model=dict)
def change_pin(
    payload: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    old_pin = payload.get("old_pin", "")
    new_pin = payload.get("new_pin", "")

    if not old_pin or not new_pin:
        raise HTTPException(status_code=400, detail="Old PIN and new PIN required")

    if len(new_pin) < 4:
        raise HTTPException(status_code=400, detail="PIN must be at least 4 digits")

    if current_user.password_hash and not verify_password(old_pin, current_user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect old PIN")

    current_user.password_hash = hash_password(new_pin)
    db.commit()

    return {
        "status": "success",
        "message": "PIN changed successfully",
    }


@router.post("/auth/normalize-farmer-id")
def normalize_fid(payload: dict, db: Session = Depends(get_db)):
    raw = payload.get("farmer_id", "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="farmer_id is required")

    normalized = normalize_farmer_id(raw)
    user = db.query(User).filter(User.farmer_id == normalized).first()

    return {
        "status": "success",
        "data": {
            "original": raw,
            "normalized": normalized,
            "exists": user is not None,
        },
    }


@router.post("/auth/send-phone-change-otp", response_model=dict)
def send_phone_change_otp(
    payload: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    new_phone = (payload.get("new_phone_number") or "").strip()
    if not new_phone or not new_phone.isdigit() or len(new_phone) != 10 or new_phone[0] not in "6789":
        raise HTTPException(status_code=400, detail="Invalid 10-digit phone number")
    if new_phone == current_user.phone_number:
        raise HTTPException(status_code=400, detail="New phone number is same as current")
    existing = db.query(User).filter(User.phone_number == new_phone, User.id != current_user.id).first()
    if existing:
        raise HTTPException(status_code=400, detail="Phone number already registered to another account")

    otp_code = f"{random.randint(0, 999999):06d}"
    otp_hash = hash_password(otp_code)
    expires_at = datetime.utcnow() + timedelta(minutes=10)

    otp_record = OTPVerification(
        user_id=current_user.id,
        phone=new_phone,
        otp_hash=otp_hash,
        expires_at=expires_at,
    )
    db.add(otp_record)
    db.commit()

    real_provider_configured = bool(
        settings.SMS_API_KEY or (settings.SMTP_HOST and settings.SMTP_USER)
    )
    masked = new_phone[:3] + "****" + new_phone[-2:]
    response = {
        "status": "success",
        "message": f"OTP sent to {masked}",
        "masked_phone": masked,
        "expires_in_seconds": 600,
    }
    if settings.DEBUG and not real_provider_configured:
        response["debug_otp"] = otp_code
        response["debug_mode"] = True
    return response


@router.post("/auth/verify-phone-change-otp", response_model=dict)
def verify_phone_change_otp(
    payload: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    new_phone = (payload.get("new_phone_number") or "").strip()
    otp_code = (payload.get("otp_code") or "").strip()
    if not new_phone or not otp_code:
        raise HTTPException(status_code=400, detail="Phone number and OTP code required")

    q = db.query(OTPVerification).filter(
        OTPVerification.user_id == current_user.id,
        OTPVerification.phone == new_phone,
        OTPVerification.verified_at.is_(None),
        OTPVerification.expires_at > datetime.utcnow(),
    )
    otp_record = q.order_by(OTPVerification.created_at.desc()).first()
    if not otp_record:
        raise HTTPException(status_code=400, detail="Invalid or expired OTP")
    if otp_record.attempts >= 5:
        raise HTTPException(status_code=400, detail="Too many attempts. Request a new OTP.")

    otp_record.attempts += 1
    if not verify_password(otp_code, otp_record.otp_hash):
        db.commit()
        raise HTTPException(status_code=400, detail="Incorrect OTP")

    otp_record.verified_at = datetime.utcnow()
    current_user.phone_number = new_phone
    current_user.is_verified = True
    db.commit()

    profile_data = UserResponse.model_validate(current_user).model_dump()
    return {
        "status": "success",
        "message": "Phone number updated successfully",
        "data": {
            "user": profile_data,
        },
    }
