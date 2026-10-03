import random
import string
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.config import settings
from app.models.user import User, OTPVerification, UserSession, LoginHistory, FarmerProfile, UserAddress
from app.models.customer import Customer
from app.schemas.auth import (
    RegisterRequest, LoginRequest, OTPRequest, OTPVerifyRequest,
    UserResponse, TokenResponse,
)
from app.schemas.customer import (
    CustomerRegisterRequest, CustomerOTPRequest, CustomerOTPVerifyRequest,
)
from app.services import customer_service, otp_service
from app.services.customer_service import (
    POINTS_REASON_WELCOME, WELCOME_POINTS, award_points,
    get_or_create_customer_settings, sync_customer_from_user,
)
from app.services.otp_service import OTPError
from app.utils.auth import (
    ROLE_CUSTOMER, ROLE_FARMER, assert_role_matches_selection,
    create_access_token, decode_token, generate_customer_id, generate_farmer_id,
    generate_id, get_current_user, hash_password, is_customer,
    normalize_customer_id, normalize_farmer_id, phone_lookup_candidates,
    revoke_session_by_jti, security, user_role, verify_password,
)
from app.utils.masking import (
    mask_aadhaar, mask_email, mask_farmer_card, mask_pan, mask_phone,
)

router = APIRouter(prefix="/api/v1", tags=["Authentication"])

HYDROPONICS_STATUSES = {"not_interested", "curious", "planning", "active"}


def join_csv(values):
    if values is None:
        return None
    if isinstance(values, str):
        return values.strip() or None
    parts = [str(value).strip() for value in values if str(value).strip()]
    return ", ".join(parts) if parts else None


def normalise_hydroponics_status(value):
    status_value = (value or "").strip().lower().replace(" ", "_").replace("-", "_")
    if not status_value:
        return None
    return status_value if status_value in HYDROPONICS_STATUSES else "curious"


def _issue_session(db: Session, user: User, token: str, device: Optional[str] = None) -> str:
    """Register the token's jti in user_sessions so logout can revoke it.

    A JWT stays cryptographically valid until it expires, so every token we
    hand out needs a server-side record; otherwise /auth/logout could only
    clear the browser copy and the credential would keep working.
    """
    payload = decode_token(token) or {}
    jti = payload.get("jti")
    if jti:
        db.add(UserSession(
            user_id=user.id,
            token_jti=jti,
            device=device,
            expires_at=datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        ))
        db.commit()
    return token


def _trailing4(value) -> str:
    """Last 4 characters of an identity number, for masked display only."""
    cleaned = "".join(ch for ch in str(value or "") if ch.isalnum()).upper()
    return cleaned[-4:] if len(cleaned) >= 4 else ""


def _mark_channel_verified(user, channel: str) -> None:
    """Record proof of ownership for the single channel that was verified."""
    if channel == otp_service.CHANNEL_PHONE:
        if user.phone_number:
            user.phone_verified = True
            user.phone_verified_at = datetime.utcnow()
    elif channel == otp_service.CHANNEL_EMAIL:
        if user.email:
            user.email_verified = True
            user.email_verified_at = datetime.utcnow()


def _farmer_profile_payload(profile: Optional[FarmerProfile]) -> Optional[dict]:
    """
    Farmer profile data safe for a normal (non-privileged) client.

    Aadhaar and PAN are never returned in full, never under their original key,
    and never logged. Only a masked form and a verification status are exposed.
    """
    if not profile:
        return None
    payload = {
        "date_of_birth": profile.date_of_birth,
        "gender": profile.gender,
        "farming_experience": profile.farming_experience,
        "preferred_crops": profile.preferred_crops,
        "irrigation_type": profile.irrigation_type,
        "farming_type": profile.farming_type,
        "farming_types": profile.farming_types,
        "farming_activities": profile.farming_activities,
        # Verification posture, not verification data.
        "identity_verification_status": profile.identity_verification_status or "not_provided",
        "aadhaar_provided": bool(profile.aadhaar_number or profile.aadhaar_last4),
        "aadhaar_masked": mask_aadhaar(profile.aadhaar_number or profile.aadhaar_last4),
        "aadhaar_verification_status": profile.aadhaar_verification_status or "not_provided",
        "pan_provided": bool(profile.pan_number or profile.pan_last4),
        "pan_masked": mask_pan(profile.pan_number or profile.pan_last4),
        "pan_verification_status": profile.pan_verification_status or "not_provided",
        "farmer_card_provided": bool(profile.farmer_card_number),
        "farmer_card_masked": (
            f"****{profile.farmer_card_last4}" if profile.farmer_card_last4 else ""
        ),
        "farmer_card_issuing_authority": profile.farmer_card_issuing_authority,
        "farmer_card_verification_status": profile.farmer_card_verification_status or "not_provided",
    }
    return payload


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
    customer_id: Optional[str] = None
    login_method: Optional[str] = "phone"
    # Which login form the person used ("farmer" or "customer"). Checked against
    # the role on the account that was actually found, so a Farmer ID typed into
    # the Customer form is refused instead of quietly logging a farmer in.
    role: Optional[str] = None
    # Optional label recorded against the revocable session (e.g. "android").
    # Not a raw user-agent dump, to avoid storing fingerprint data.
    device: Optional[str] = None


class OTPRequest(BaseModel):
    phone_number: Optional[str] = None
    email: Optional[str] = None
    # Optional expected role. When supplied, a code is only ever sent to a
    # destination owned by an account of that role.
    role: Optional[str] = None


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
    # Optional expected role, cross-checked against the resolved account.
    role: Optional[str] = None


class ForgotPinRequest(BaseModel):
    phone_number: Optional[str] = None
    email: Optional[str] = None
    new_pin: str


class ProfileLookupRequest(BaseModel):
    phone_number: Optional[str] = None
    email: Optional[str] = None
    farmer_id: Optional[str] = None
    customer_id: Optional[str] = None
    # Expected role for the lookup, so the login screen can tell "no such ID"
    # apart from "that ID belongs to the other kind of account".
    role: Optional[str] = None


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

    # Government identity is never collected silently. If the request carries
    # any identity value it must also carry the farmer's recorded consent.
    identity_values = {
        "aadhaar_number": payload.aadhaar_number,
        "pan_number": payload.pan_number,
        "farmer_card_number": payload.farmer_card_number,
    }
    wants_identity = any(identity_values.values())
    if wants_identity and not payload.identity_consent_given:
        raise HTTPException(
            status_code=400,
            detail=(
                "Consent is required before government identity details can be stored. "
                "Please review and accept the identity disclosure."
            ),
        )

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
        phone_verified=False,
        email_verified=False,
        # Consent ledger: what was agreed, and when.
        identity_consent_given=bool(payload.identity_consent_given),
        identity_consent_version=payload.identity_consent_version if payload.identity_consent_given else None,
        identity_consent_at=datetime.utcnow() if payload.identity_consent_given else None,
        onboarding_status=payload.onboarding_status or "registered",
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
        # Self-declared at signup and format-checked only. Nothing here has been
        # checked against any authority, so the status records that honestly.
        aadhaar_last4=_trailing4(payload.aadhaar_number),
        aadhaar_verification_status="pending" if payload.aadhaar_number else "not_provided",
        pan_last4=_trailing4(payload.pan_number),
        pan_verification_status="pending" if payload.pan_number else "not_provided",
        identity_verification_status="pending" if (payload.aadhaar_number or payload.pan_number) else "not_provided",
        farmer_card_number=payload.farmer_card_number,
        farmer_card_issuing_authority=payload.farmer_card_issuing_authority,
        farmer_card_last4=_trailing4(payload.farmer_card_number),
        farmer_card_verification_status=(
            "pending" if payload.farmer_card_number else "not_provided"
        ),
        irrigation_type=payload.irrigation_type,
        farming_types=join_csv(payload.farming_types),
        farming_type=(payload.farming_types or [None])[0],
        farming_activities=join_csv(payload.farming_activities),
        hydroponics_status=normalise_hydroponics_status(payload.hydroponics_status),
        hydroponics_units_count=payload.hydroponics_units_count,
        hydroponics_system=payload.hydroponics_system,
        hydroponics_crops=join_csv(payload.hydroponics_crops),
        hydroponics_area=payload.hydroponics_area,
        hydroponics_area_unit=payload.hydroponics_area_unit,
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
        latitude=payload.latitude,
        longitude=payload.longitude,
    )
    db.add(farm)
    db.flush()
    farm.farm_id = generate_id("FA-FARM", db, Farm)

    db.commit()
    db.refresh(user)

    token = _issue_session(db, user, create_access_token(data={"sub": user.id, "phone": user.phone_number}))

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


def _otp_http_error(exc: OTPError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.message)


@router.post("/auth/register/customer", response_model=dict, status_code=status.HTTP_201_CREATED)
def register_customer(payload: CustomerRegisterRequest, db: Session = Depends(get_db)):
    """Create a customer account and issue its Customer ID.

    A separate endpoint from ``/auth/register`` on purpose. The farmer path is
    the original one, complete with farm, plot and identity fields, and it is
    left exactly as it was so no existing registration changes behaviour. This
    one collects only what a customer actually needs and creates no farm.

    The returned ``customer_id`` is the canonical ``FA-CS-######`` value and is
    what the customer types to log in next time. It is allocated by the database
    sequence, not by anything the client sent.
    """
    existing = db.query(User).filter(
        User.phone_number.in_(phone_lookup_candidates(payload.phone_number))
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Phone number already registered")

    if payload.email:
        email_exists = db.query(User).filter(User.email == payload.email).first()
        if email_exists:
            raise HTTPException(status_code=400, detail="Email already registered")

    pin_value = payload.pin or payload.password
    if not pin_value:
        raise HTTPException(status_code=400, detail="PIN is required for registration")
    if len(str(pin_value)) < 4:
        raise HTTPException(status_code=400, detail="PIN must be at least 4 characters")

    user = User(
        full_name=payload.full_name,
        phone_number=payload.phone_number,
        email=payload.email,
        password_hash=hash_password(str(pin_value)),
        preferred_language=payload.preferred_language or "en",
        # role is the only thing that decides which dashboard and which API
        # surface this account can reach, so it is written explicitly here.
        role=ROLE_CUSTOMER,
        is_verified=False,
        phone_verified=False,
        email_verified=False,
        onboarding_status="registered",
        is_active=True,
        created_at=datetime.utcnow(),
    )
    db.add(user)
    db.flush()

    # A customer has no farmer_id. Leaving it NULL keeps the two public ID
    # namespaces disjoint: a Farmer ID can never be mistaken for a Customer ID,
    # and the login forms can reject each other's IDs with a clear message.
    customer_id = generate_customer_id(db)
    customer = Customer(
        user_id=user.id,
        customer_id=customer_id,
        full_name=payload.full_name,
        phone_number=payload.phone_number,
        email=payload.email,
        date_of_birth=payload.date_of_birth,
        gender=payload.gender,
        verification_status="pending",
        phone_verified=False,
        email_verified=False,
        points_balance=0,
        preferred_language=payload.preferred_language or "en",
        created_at=datetime.utcnow(),
    )
    db.add(customer)

    if any([
        payload.address_line, payload.city, payload.district,
        payload.state, payload.pincode,
    ]):
        db.add(UserAddress(
            user_id=user.id,
            address_line=payload.address_line,
            village=payload.city or payload.village,
            mandal=payload.mandal,
            district=payload.district,
            state=payload.state,
            country="India",
            pincode=payload.pincode,
            latitude=payload.latitude,
            longitude=payload.longitude,
            is_primary=True,
        ))

    # Real, recorded loyalty credit rather than a hard-coded number: the badge
    # in the header is backed by this ledger row.
    award_points(
        db, customer, WELCOME_POINTS, POINTS_REASON_WELCOME,
        reference_type="registration", reference_id=customer_id,
    )
    get_or_create_customer_settings(db, user)

    db.commit()
    db.refresh(user)
    db.refresh(customer)

    token = _issue_session(db, user, create_access_token(data={"sub": user.id, "phone": user.phone_number}))

    profile_data = UserResponse.model_validate(user).model_dump()
    profile_data["role"] = user_role(user)

    return {
        "status": "success",
        "message": "Registration successful",
        "data": {
            "customer_id": customer_id,
            "access_token": token,
            "token_type": "bearer",
            "role": profile_data["role"],
            "points_balance": int(customer.points_balance or 0),
            # A brand new account has proved nothing yet. Say so rather than
            # leaving the client to guess from a missing field.
            "verification_status": customer.verification_status or "pending",
            "user": profile_data,
            "customer": customer_service.customer_summary_payload(db, user, customer),
        },
    }


@router.post("/auth/send-otp", response_model=dict)
def send_otp(payload: OTPRequest, db: Session = Depends(get_db)):
    if not payload.phone_number and not payload.email:
        raise HTTPException(status_code=400, detail="Phone number or email required")

    channel = otp_service.CHANNEL_PHONE if payload.phone_number else otp_service.CHANNEL_EMAIL
    destination = payload.phone_number if payload.phone_number else payload.email

    user = None
    if channel == otp_service.CHANNEL_PHONE:
        user = db.query(User).filter(
            User.phone_number.in_(phone_lookup_candidates(destination))
        ).first()
    else:
        user = db.query(User).filter(User.email == destination).first()

    # When the login page told us which form is being used, hold the lookup to
    # that role so a code is never sent to the other kind of account.
    if user is not None and payload.role:
        assert_role_matches_selection(user, payload.role)

    # Bind the code to the account when one exists, so verification cannot be
    # satisfied by an OTP minted for a different destination.
    try:
        return otp_service.issue_otp(
            db,
            channel=channel,
            destination=destination,
            user_id=user.id if user else None,
        )
    except OTPError as exc:
        raise _otp_http_error(exc)


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

    try:
        return otp_service.issue_otp(
            db,
            channel=channel,
            destination=phone if channel == "phone" else email,
            user_id=user.id,
        )
    except OTPError as exc:
        raise _otp_http_error(exc)


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

    try:
        otp_record = otp_service.consume_otp(
            db,
            channel=channel,
            destination=lookup_phone or lookup_email or "",
            code=payload.otp_code,
        )
    except OTPError as exc:
        raise _otp_http_error(exc)

    otp_record.user_id = user.id
    user.is_verified = True
    _mark_channel_verified(user, channel)
    db.commit()

    token = _issue_session(db, user, create_access_token(data={"sub": user.id, "phone": user.phone_number}))
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

    channel = otp_service.CHANNEL_PHONE if lookup_phone else otp_service.CHANNEL_EMAIL
    destination = lookup_phone if lookup_phone else lookup_email

    try:
        otp_record = otp_service.consume_otp(
            db, channel=channel, destination=destination, code=payload.otp_code
        )
    except OTPError as exc:
        raise _otp_http_error(exc)

    user = None
    if channel == otp_service.CHANNEL_PHONE:
        user = db.query(User).filter(
            User.phone_number.in_(phone_lookup_candidates(lookup_phone))
        ).first()
    else:
        user = db.query(User).filter(User.email == lookup_email).first()

    if user:
        # The record was bound to a user at issue time; refuse to let a code
        # minted for one account verify a different one.
        if otp_record.user_id and otp_record.user_id != user.id:
            db.rollback()
            raise HTTPException(
                status_code=400,
                detail="That code is invalid or has expired. Please request a new one.",
            )
        # If the caller declared which form they are on, refuse to verify the
        # other kind of account with it.
        if payload.role:
            assert_role_matches_selection(user, payload.role)
        otp_record.user_id = user.id
        user.is_verified = True
        _mark_channel_verified(user, channel)

    db.commit()

    token = None
    if user:
        token = _issue_session(db, user, create_access_token(data={"sub": user.id, "phone": user.phone_number}))

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


CUSTOMER_ID_FORMAT_HINT = "Customer ID should look like FA-CS-000001"

#: Message used when a Customer ID is offered to the Farmer form. Matching on the
#: prefix means a genuinely mistyped digit still reports "not found", while an ID
#: that really exists under the other namespace gets the useful answer.
CUSTOMER_ID_PREFIX = "FA-CS-"


def _load_user_for_customer_id(raw_customer_id: str, db: Session):
    """Resolve a typed Customer ID to its account, rejecting other namespaces."""
    normalized = normalize_customer_id(raw_customer_id)
    if not normalized:
        _raise_missing_id(raw_customer_id, ROLE_CUSTOMER)

    customer = db.query(Customer).filter(Customer.customer_id == normalized).first()
    if customer is None:
        _raise_missing_id(raw_customer_id, ROLE_CUSTOMER)

    user = db.query(User).filter(User.id == customer.user_id).first()
    if user is None or user_role(user) != ROLE_CUSTOMER:
        raise HTTPException(
            status_code=403,
            detail="This ID belongs to a Farmer account. Please use Farmer Login.",
        )
    return user, customer


@router.post("/auth/send-customer-otp", response_model=dict)
def send_customer_otp(payload: CustomerOTPRequest, db: Session = Depends(get_db)):
    """Send a verification code to a customer, using the existing OTP service.

    Not a new verification mechanism: the same issue/consume/rate-limit path the
    farmer flow already uses, so codes, expiry and resend limits behave
    identically for customers.
    """
    user, _customer = _load_user_for_customer_id(payload.customer_id, db)

    channel = (payload.channel or "phone").lower()
    if channel not in ("phone", "email"):
        raise HTTPException(status_code=400, detail="Channel must be 'phone' or 'email'")

    phone = user.phone_number
    email = user.email
    if channel == "phone" and not phone:
        raise HTTPException(status_code=400, detail="No registered phone number found")
    if channel == "email" and not email:
        raise HTTPException(status_code=400, detail="No registered email found")

    try:
        return otp_service.issue_otp(
            db,
            channel=channel,
            destination=phone if channel == "phone" else email,
            user_id=user.id,
        )
    except OTPError as exc:
        raise _otp_http_error(exc)


@router.post("/auth/verify-customer-otp", response_model=dict)
def verify_customer_otp(payload: CustomerOTPVerifyRequest, db: Session = Depends(get_db)):
    """Verify a customer OTP and mark that channel verified on the account."""
    user, customer = _load_user_for_customer_id(payload.customer_id, db)

    channel = (payload.channel or "phone").lower()
    destination = (user.phone_number if channel == "phone" else user.email) or ""

    try:
        otp_record = otp_service.consume_otp(
            db, channel=channel, destination=destination, code=payload.otp_code
        )
    except OTPError as exc:
        raise _otp_http_error(exc)

    # A code minted for a different account must not verify this one.
    if otp_record.user_id and otp_record.user_id != user.id:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail="That code is invalid or has expired. Please request a new one.",
        )

    otp_record.user_id = user.id
    user.is_verified = True
    _mark_channel_verified(user, channel)
    # Reflect the newly verified channel on the customer profile, so the profile
    # screen and the header badge agree with what the OTP service confirmed.
    sync_customer_from_user(db, user, customer)
    db.commit()

    token = _issue_session(db, user, create_access_token(data={"sub": user.id, "phone": user.phone_number}))
    return {
        "status": "success",
        "message": "OTP verified successfully",
        "data": {
            "customer_id": customer.customer_id,
            "access_token": token,
            "token_type": "bearer",
            "user": UserResponse.model_validate(user).model_dump(),
            "customer": customer_service.customer_summary_payload(db, user, customer),
        },
    }


def _raise_missing_id(raw_id, expected_role: str):
    """Raise the most useful error for an ID that did not resolve.

    Three distinct situations, deliberately kept distinct for the person typing:
    a Customer ID in the Farmer form, a Farmer ID in the Customer form, and an ID
    that simply does not exist.
    """
    text = str(raw_id or "").strip().upper()
    if expected_role == ROLE_FARMER:
        if text.startswith(CUSTOMER_ID_PREFIX):
            raise HTTPException(
                status_code=403,
                detail="This ID belongs to a Customer account. Please use Customer Login.",
            )
        raise HTTPException(status_code=401, detail="Farmer ID not found")

    # Customer form.
    if text.startswith("FA-AS-"):
        raise HTTPException(
            status_code=403,
            detail="This ID belongs to a Farmer account. Please use Farmer Login.",
        )
    if not normalize_customer_id(raw_id):
        raise HTTPException(status_code=400, detail=CUSTOMER_ID_FORMAT_HINT)
    raise HTTPException(
        status_code=401,
        detail="Customer ID not found. Please check your ID and try again.",
    )


def _resolve_customer_login(payload: LoginRequest, db: Session):
    """Find the account behind a Customer ID and check it really is a customer.

    Three separate checks, all server-side: the ID must be a real row in
    ``customers``, the user behind it must carry the customer role, and the role
    the login form claimed must match. A correctly formatted ID that nobody owns
    is not a login.
    """
    expected_role = payload.role or ROLE_CUSTOMER
    normalized = normalize_customer_id(payload.customer_id)
    if not normalized:
        _raise_missing_id(payload.customer_id, expected_role)

    customer = (
        db.query(Customer)
        .filter(Customer.customer_id == normalized)
        .first()
    )
    if customer is None:
        _raise_missing_id(payload.customer_id, expected_role)

    user = db.query(User).filter(User.id == customer.user_id).first()
    if user is None:
        raise HTTPException(status_code=401, detail="Customer ID not found. Please check your ID and try again.")

    # The role on the users row is the authority, not the role sent by the
    # client and not the mere existence of a customer profile.
    if user_role(user) != ROLE_CUSTOMER:
        raise HTTPException(
            status_code=403,
            detail="This ID belongs to a Farmer account. Please use Farmer Login.",
        )
    assert_role_matches_selection(user, expected_role)

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is deactivated")

    return user, customer


@router.post("/auth/login", response_model=dict)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    """Authenticate a Farmer or a Customer.

    Four credential shapes are accepted -- Customer ID, Farmer ID, email and
    phone -- and every one of them ends the same way: the account is loaded from
    the database, its role is read off that row, the selected login type is
    checked against it, and the token is issued only if both the credential and
    the role agree.
    """
    user = None

    if payload.customer_id:
        user, customer = _resolve_customer_login(payload, db)
        pin = payload.pin or payload.password
        if not pin or not user.password_hash or not verify_password(pin, user.password_hash):
            raise HTTPException(status_code=401, detail="Invalid PIN")
    elif payload.farmer_id:
        normalized_farmer_id = normalize_farmer_id(payload.farmer_id)
        candidates = {normalized_farmer_id}
        digits = ''.join(ch for ch in str(payload.farmer_id) if ch.isdigit())
        if digits:
            candidates.add(f"FA-AS-{digits.zfill(8)}")
            candidates.add(digits)
        user = db.query(User).filter(User.farmer_id.in_(list(candidates))).first()
        if not user:
            _raise_missing_id(payload.farmer_id, ROLE_FARMER)
        # A Customer ID is a real, well-formed identifier, so recognise it and
        # say which form to use instead of reporting it as simply missing.
        assert_role_matches_selection(user, payload.role or ROLE_FARMER)
        pin = payload.pin or payload.password
        if not pin or not user.password_hash or not verify_password(pin, user.password_hash):
            raise HTTPException(status_code=401, detail="Invalid PIN")
    elif payload.email:
        user = db.query(User).filter(User.email == payload.email).first()
        if not user:
            raise HTTPException(status_code=401, detail="Email not found")
        assert_role_matches_selection(user, payload.role)
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
        # Phone and email are shared by both account types, so this is the path
        # where "you used the wrong form" actually bites.
        assert_role_matches_selection(user, payload.role)
        pwd = payload.pin or payload.password
        if not pwd or not user.password_hash or not verify_password(pwd, user.password_hash):
            raise HTTPException(status_code=401, detail="Invalid PIN/Password")
    else:
        raise HTTPException(
            status_code=400,
            detail="Customer ID, Farmer ID, phone number or email required",
        )

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is deactivated")

    token = create_access_token(data={"sub": user.id, "phone": user.phone_number})

    login_entry = LoginHistory(user_id=user.id)
    db.add(login_entry)
    db.commit()
    _issue_session(db, user, token, device=payload.device)

    profile_data = UserResponse.model_validate(user).model_dump()
    # Always report the canonical role, never the role the client claimed, so the
    # frontend routes on what the backend decided.
    profile_data["role"] = user_role(user)
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
    safe_profile = _farmer_profile_payload(farmer_profile)
    if safe_profile:
        profile_data["farmer_profile"] = safe_profile
    customer = customer_service.get_customer_for_user(db, user)
    if customer is not None:
        profile_data["customer"] = customer_service.customer_summary_payload(
            db, user, customer
        )

    response_data = {
        "access_token": token,
        "token_type": "bearer",
        "user": profile_data,
    }
    # Repeated at the top level so a client can read the Customer ID and the
    # points balance without walking into the nested profile. Absent for
    # farmers, who have neither.
    if customer is not None:
        response_data["role"] = profile_data["role"]
        response_data["customer_id"] = customer.customer_id
        response_data["points_balance"] = int(customer.points_balance or 0)
        response_data["verification_status"] = customer.verification_status or "pending"

    return {"status": "success", "data": response_data}


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
    customer = None
    if payload.customer_id:
        # Mirrors the login path: a Farmer ID typed into the customer form is
        # reported as such instead of as a missing account.
        normalized = normalize_customer_id(payload.customer_id)
        if normalized:
            customer = db.query(Customer).filter(Customer.customer_id == normalized).first()
            if customer:
                user = db.query(User).filter(User.id == customer.user_id).first()
        if user is None:
            _raise_missing_id(payload.customer_id, payload.role or ROLE_CUSTOMER)
    elif payload.phone_number:
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

    # The role that comes back is the one on the users row, so the login screen
    # routes on the server's answer rather than on what it typed.
    role = user_role(user)

    # Only the customer_id branch loads the Customer row. A customer reached by
    # phone or email still needs it for the Customer ID shown before the PIN
    # step, so resolve it from the user whenever the role says it is a customer.
    if role == ROLE_CUSTOMER and customer is None:
        customer = db.query(Customer).filter(Customer.user_id == user.id).first()
        if customer is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Customer account is incomplete. Please contact support.",
            )

    data = {
        "full_name": user.full_name,
        "role": role,
        "farmer_id": user.farmer_id if role == ROLE_FARMER else None,
        "customer_id": customer.customer_id if role == ROLE_CUSTOMER else None,
        "profile_image": user.profile_image,
        "phone_masked": user.phone_number[:3] + "****" + user.phone_number[-2:] if user.phone_number and len(user.phone_number) >= 5 else None,
        "email_masked": user.email[:2] + "***@" + user.email.split("@")[1] if user.email and "@" in user.email else None,
    }

    # When the caller declared a form, an account of the other kind is refused
    # here rather than shown on the wrong screen.
    if payload.role:
        assert_role_matches_selection(user, payload.role)

    if customer is not None and role == ROLE_CUSTOMER:
        data["points_balance"] = int(customer.points_balance or 0)
        data["verification_status"] = customer.verification_status or customer_service.verification_status_for(user)

    return {
        "status": "success",
        "data": data,
        "message": "Profile found",
    }


@router.post("/auth/logout", response_model=dict)
def logout(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    # Revoke the presented token server side. Clearing the local copy in the
    # browser alone leaves a usable credential for the rest of its lifetime.
    token_revoked = False
    if credentials and credentials.credentials:
        token_revoked = revoke_session_by_jti(db, credentials.credentials)

    login_entry = (
        db.query(LoginHistory)
        .filter(LoginHistory.user_id == current_user.id, LoginHistory.logout_time.is_(None))
        .order_by(LoginHistory.login_time.desc())
        .first()
    )
    if login_entry:
        login_entry.logout_time = datetime.utcnow()
        db.commit()

    return {
        "status": "success",
        "message": "Logged out successfully",
        "token_revoked": token_revoked,
    }


@router.get("/auth/me", response_model=dict)
def get_me(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
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

    # The role reported here is the one stored on the account. The client is told
    # what it is, never allowed to decide it.
    profile_data["role"] = user_role(current_user)

    # A customer session carries its Customer ID and points with it, so the
    # dashboard header can render both straight from /auth/me.
    customer = customer_service.get_customer_for_user(db, current_user)
    if customer is not None:
        profile_data["customer_id"] = customer.customer_id
        profile_data["points_balance"] = int(customer.points_balance or 0)
        profile_data["verification_status"] = (
            customer.verification_status or customer_service.verification_status_for(current_user)
        )

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

    masked = new_phone[:3] + "****" + new_phone[-2:]
    response = {
        "status": "success",
        "message": f"OTP sent to {masked}",
        "masked_phone": masked,
        "expires_in_seconds": 600,
    }
    if settings.DEBUG:
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
    # Proof of ownership of the new number was just given, so record it. Without
    # this the verification flag stayed false after a successful change.
    _mark_channel_verified(current_user, otp_service.CHANNEL_PHONE)
    # The customer profile mirrors the phone number, so refresh it here too;
    # otherwise a customer's header would keep showing the old number.
    sync_customer_from_user(db, current_user)
    db.commit()

    profile_data = UserResponse.model_validate(current_user).model_dump()
    profile_data["role"] = user_role(current_user)
    return {
        "status": "success",
        "message": "Phone number updated successfully",
        "data": {
            "user": profile_data,
        },
    }
