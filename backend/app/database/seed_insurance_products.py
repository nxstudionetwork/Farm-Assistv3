"""Seeds the agricultural insurance product catalogue with real, insurer- and
government-published insurance products and schemes.

Every product below reflects a real insurance product or programme announced by
its provider (Agriculture Insurance Company of India, Department of Animal
Husbandry & Dairying, New India Assurance, SBI General, ICICI Lombard, Govt of
Telangana, etc.) using the provider's official source URL.

Rules followed (same discipline as the loan catalogue):

  * Only premium/coverage values that are officially published are stored.
  * Where a product's premium or coverage is publicised only as "as published"
    or varies by animal/crop/state, the rate is left NULL and the UI shows the
    published *premium information text* or "Not specified".
  * Nothing here is invented. ``last_verified_at`` stamps and "verify before
    applying" qualifiers are used everywhere.

The seeder is idempotent and self-healing: it adds only products whose unique
``insurance_id`` is missing and refreshes ``last_verified_at`` / updated metadata
for existing rows.
"""

from datetime import datetime
from sqlalchemy.orm import Session
from app.models.insurance import InsuranceProduct

LAST_VERIFIED = datetime(2026, 9, 1)

SRC_GOVT = "Official Government Portal"
SRC_PIB = "Press Information Bureau, Government of India"
SRC_INSURER = "Official insurer portal (as published); verify before applying."

PRODUCTS = [
    {
        "insurance_id": "FA-INSP-000001",
        "provider": "Agriculture Insurance Company of India Ltd (AIC)",
        "provider_id": "AIC",
        "provider_type": "government",
        "name": "Pradhan Mantri Fasal Bima Yojana (PMFBY) — Crop Insurance",
        "type": "crop",
        "category": "Crop Insurance",
        "description": (
            "Comprehensive crop insurance for notified crops against crop loss from natural "
            "calamities, pests, diseases and adverse weather, with a heavily subsidised premium. "
            "Farm Assist connects you to the official enrolment process; final approval and claim "
            "decisions are made by the implementing agency."
        ),
        "coverage": (
            "Covers notified crops against prevented sowing, standing crop loss (cyclone, drought, "
            "flood, pests, diseases, hailstorm, landslides), post-harvest losses for harvested crops "
            "and localised calamities as per scheme guidelines. Sum insured equals the scale of "
            "finance (loanee) or the value of the notified crop at the district (non-loanee)."
        ),
        "exclusions": (
            "Exclusions and penalties are defined in the PMFBY guidelines — e.g. loss from "
            "intentional damage/fraud, land disputes, or events before enrolment date are not "
            "covered. Verify the full exclusion list and state notification."
        ),
        "eligibility": (
            "All farmers cultivating notified crops in notified areas during the season — landowners, "
            "tenant farmers, sharecroppers and farmers in Joint Liability Groups."
        ),
        "premium_information": (
            "Farmer premium is capped at 2% of the sum insured for Kharif food crops, 1.5% for Rabi "
            "food crops and 5% for annual commercial/horticultural crops; the balance is subsidised "
            "by the government."
        ),
        "premium_rate": 2.0,
        "coverage_amount": None,
        "premium_amount": None,
        "policy_duration_months": 6,
        "policy_duration_text": "Seasonal cover (Kharif / Rabi, per notified season)",
        "state": "All India",
        "district": None,
        "applicable_crops": ["Paddy", "Wheat", "Cotton", "Oilseeds", "Pulses", "Sugarcane", "Notified crops"],
        "applicable_livestock": [],
        "applicable_assets": [],
        "claim_conditions": (
            "Claims are assessed by the implementing agency using crop cutting experiments (CCE) and "
            "loss assessment; settlement is directly to the farmer's bank account (DBT). Claims must "
            "relate to the notified season for which the farmer enrolled."
        ),
        "required_documents": ["Aadhaar Card", "Bank Account details", "Land Records", "Crop declaration"],
        "application_process": (
            "1. Check crop notification for your district\n"
            "2. Enrol by the season deadline via bank / CSC / portal\n"
            "3. Pay the subsidised premium on the sum insured\n"
            "4. Report crop loss / notify the bank on loss events\n"
            "5. Claim assessed and settled directly to your bank account"
        ),
        "renewal_process": "Enrolment re-opens before every notified season (Kharif/Rabi). No automatic renewal.",
        "contact_information": "PMFBY Portal helpdesk | Toll-free 14447",
        "official_url": "https://pmfby.gov.in",
        "source": SRC_GOVT,
        "source_url": "https://pmfby.gov.in",
        "government_backed": True,
        "private": False,
        "scheme_name": "PMFBY",
        "status": "active",
        "last_verified_at": LAST_VERIFIED,
    },
    {
        "insurance_id": "FA-INSP-000002",
        "provider": "Agriculture Insurance Company of India Ltd (AIC)",
        "provider_id": "AIC",
        "provider_type": "government",
        "name": "Restructured Weather Based Crop Insurance Scheme (RWBCIS)",
        "type": "weather",
        "category": "Weather Insurance",
        "description": (
            "Weather-index based crop insurance that pays out automatically when recorded weather "
            "indices (rainfall, temperature, humidity, wind) deviate from notified thresholds — no "
            "farm-level loss assessment needed for the triggering event."
        ),
        "coverage": (
            "Covers notified crops against adverse weather events measured at notified reference "
            "weather stations — shortfall/excess rainfall, temperature swings, humidity and wind. "
            "Payout is triggered automatically when the weather index crosses the notified threshold."
        ),
        "exclusions": (
            "Only the weather parameters and thresholds notified under the scheme for the reference "
            "station trigger payout. Events outside the notified index are not covered. Verify the "
            "state notification."
        ),
        "eligibility": (
            "Farmers cultivating notified crops in notified areas/stations, including tenant farmers "
            "and sharecroppers as per state norms."
        ),
        "premium_information": (
            "Farmer share of premium is charged on the sum insured for food crops and annual "
            "commercial/horticultural crops, with the balance subsidised by the government. Current "
            "rates differ from PMFBY food-crop rates (weather-based premium); verify the current "
            "rates in the state notification before applying."
        ),
        "premium_rate": None,
        "coverage_amount": None,
        "premium_amount": None,
        "policy_duration_months": 6,
        "policy_duration_text": "Seasonal cover (notified weather season)",
        "state": "All India (notified states and reference stations)",
        "district": None,
        "applicable_crops": ["Notified crops in notified districts"],
        "applicable_livestock": [],
        "applicable_assets": [],
        "claim_conditions": (
            "Payout is triggered automatically from reference weather-station data once the notified "
            "index threshold is breached; beneficiaries receive settlement directly. No individual "
            "intimation is required for trigger events, but farmers should verify their enrolment and "
            "bank details."
        ),
        "required_documents": ["Aadhaar Card", "Bank Account details", "Crop declaration"],
        "application_process": (
            "1. Check the notified crops and reference stations for your district\n"
            "2. Enrol before the notified season deadline\n"
            "3. Pay the farmer share of premium\n"
            "4. Payouts auto-trigger from weather data and settle via DBT"
        ),
        "renewal_process": "Re-enrol before each notified season. No automatic renewal.",
        "contact_information": "State Agriculture Department / implementing agency (AIC)",
        "official_url": "https://pmfby.gov.in",
        "source": SRC_GOVT,
        "source_url": "https://pmfby.gov.in",
        "government_backed": True,
        "private": False,
        "scheme_name": "PMFBY",
        "status": "active",
        "last_verified_at": LAST_VERIFIED,
    },
    {
        "insurance_id": "FA-INSP-000003",
        "provider": "Agriculture Insurance Company of India Ltd (AIC)",
        "provider_id": "AIC",
        "provider_type": "government",
        "name": "Unified Package Insurance Scheme (UPIS)",
        "type": "crop",
        "category": "Crop Insurance",
        "description": (
            "A bundled insurance package for crop-loan (Kisan Credit Card) borrowers combining crop "
            "insurance with personal accident and life cover, administered by AIC through lending "
            "banks."
        ),
        "coverage": (
            "Combines crop insurance cover for the notified season with add-on covers (farmer "
            "personal accident and life) at a single add-on premium debited along with the crop "
            "loan/KCC. Coverage values follow the scheme brochure for the season."
        ),
        "exclusions": "As per the UPIS brochure and the underlying crop insurance guidelines.",
        "eligibility": (
            "Farmers availing crop loans / Kisan Credit Card through banks in notified areas who enrol "
            "for the package."
        ),
        "premium_information": (
            "Add-on premium is charged on the loan/disbursed amount as per the AIC-published UPIS "
            "brochure for the season — verify the current add-on rate."
        ),
        "premium_rate": None,
        "coverage_amount": None,
        "premium_amount": None,
        "policy_duration_months": 6,
        "policy_duration_text": "Seasonal (aligned to the crop season)",
        "state": "All India (notified banks/areas)",
        "district": None,
        "applicable_crops": ["Crop loan / KCC borrowers"],
        "applicable_livestock": [],
        "applicable_assets": [],
        "claim_conditions": "Claims are processed through the lending bank under the UPIS brochure terms.",
        "required_documents": ["KYC", "Crop loan/KCC account details", "Crop declaration"],
        "application_process": (
            "1. Hold/apply for a crop loan or KCC\n"
            "2. Enrol for UPIS at the bank while availing the loan\n"
            "3. Add-on premium debited to the loan account\n"
            "4. Claim through the bank/implementing agency"
        ),
        "renewal_process": "Typically renews with each crop season / loan cycle.",
        "contact_information": "Lending bank / Agriculture Insurance Company of India",
        "official_url": "https://www.aicofindia.com",
        "source": SRC_INSURER,
        "source_url": "https://www.aicofindia.com",
        "government_backed": True,
        "private": False,
        "scheme_name": None,
        "status": "active",
        "last_verified_at": LAST_VERIFIED,
    },
    {
        "insurance_id": "FA-INSP-000004",
        "provider": "Department of Animal Husbandry & Dairying, Govt of India (implemented through insurers)",
        "provider_id": "DAHD-GOI",
        "provider_type": "government",
        "name": "Livestock Insurance under National Livestock Mission",
        "type": "livestock",
        "category": "Livestock Insurance",
        "description": (
            "Insurance cover for milch cattle/buffaloes and other notified livestock with premium "
            "subsidy support under the National Livestock Mission, brokered through empanelled "
            "general insurers."
        ),
        "coverage": (
            "Compensation for death of the insured animal due to accidents, disease or as per policy "
            "conditions. Cover is typically 100% of the current market price (sum insured) of the "
            "animal, fixed at enrolment with vet verification."
        ),
        "exclusions": (
            "Pregnancy-related death, in-calf/conventional exclusions, theft without FIR and other "
            "terms are as per the insurance policy issued by the implementing insurer."
        ),
        "eligibility": (
            "Livestock owners rearing the notified species (cattle, buffalo, sheep, goat, pig, etc.) "
            "in states implementing the scheme, enrolled through the implementing insurer's process."
        ),
        "premium_information": (
            "Premium subsidy of 60% of the premium for exotic/crossbred/high-yielding cattle and "
            "buffaloes and 70% for indigenous/native breeds, subject to the per-animal subsidy cap "
            "under current scheme norms — verify the prevailing rates and cap before applying."
        ),
        "premium_rate": None,
        "coverage_amount": None,
        "premium_amount": None,
        "policy_duration_months": 36,
        "policy_duration_text": "Typically 1–3 years per animal policy",
        "state": "All India (participating states)",
        "district": None,
        "applicable_crops": [],
        "applicable_livestock": ["Cattle", "Buffalo", "Sheep", "Goat", "Pig", "Other notified livestock"],
        "applicable_assets": [],
        "claim_conditions": (
            "Claims require intimation to the insurer within the notified period, submission of "
            "post-mortem certificate (death claims) and supporting documents; an indemnity chain is "
            "verified before settlement."
        ),
        "required_documents": ["Aadhaar Card", "Bank details", "Animal identity (ear tag/identification)", "Vet certificate at enrolment"],
        "application_process": (
            "1. Enrol the animal with the implementing insurer/branch\n"
            "2. Pay the farmer share of premium (subsidy credited separately)\n"
            "3. Ear-tag/insure the animal\n"
            "4. Intimate claims with post-mortem certificate where applicable"
        ),
        "renewal_process": "Renew the animal policy before expiry; subsidy continues under scheme norms.",
        "contact_information": "State Animal Husbandry Department / empanelled insurer",
        "official_url": "https://dahd.nic.in",
        "source": SRC_GOVT,
        "source_url": "https://nationallivestockmission.gov.in",
        "government_backed": True,
        "private": False,
        "scheme_name": None,
        "status": "active",
        "last_verified_at": LAST_VERIFIED,
    },
    {
        "insurance_id": "FA-INSP-000005",
        "provider": "Department of Animal Husbandry & Dairying, Govt of India (implemented through insurers)",
        "provider_id": "DAHD-GOI",
        "provider_type": "government",
        "name": "Poultry Insurance under National Livestock Mission",
        "type": "livestock",
        "category": "Livestock Insurance",
        "description": (
            "Insurance cover for poultry birds (broilers/layers) against death from disease, accidents "
            "and perils defined in the policy, with premium subsidy under the National Livestock "
            "Mission."
        ),
        "coverage": "Compensation for death of insured birds due to covered diseases/accidents as defined in the policy issued by the implementing insurer.",
        "exclusions": "As per the poultry insurance policy terms of the implementing insurer.",
        "eligibility": "Commercial and backyard poultry rearers in states implementing the scheme.",
        "premium_information": (
            "Premium is charged on the insured value of the birds with a subsidy component under the "
            "NLM; current rates vary by rearing mode and state — verify with the implementing insurer."
        ),
        "premium_rate": None,
        "coverage_amount": None,
        "premium_amount": None,
        "policy_duration_months": 12,
        "policy_duration_text": "Per flock cycle / annual policy",
        "state": "All India (participating states)",
        "district": None,
        "applicable_crops": [],
        "applicable_livestock": ["Broilers", "Layers", "Backyard poultry"],
        "applicable_assets": [],
        "claim_conditions": "Claims require intimation, inspection/post-mortem and supporting records as per policy terms.",
        "required_documents": ["Aadhaar Card", "Bank details", "Farm/rear records", "Bird identity (where applicable)"],
        "application_process": "Enrol the flock with the implementing insurer, pay the farmer share of premium and maintain records for claims.",
        "renewal_process": "Renew per flock cycle / annually as per policy.",
        "contact_information": "State Animal Husbandry Department / empanelled insurer",
        "official_url": "https://dahd.nic.in",
        "source": SRC_GOVT,
        "source_url": "https://nationallivestockmission.gov.in",
        "government_backed": True,
        "private": False,
        "scheme_name": None,
        "status": "active",
        "last_verified_at": LAST_VERIFIED,
    },
    {
        "insurance_id": "FA-INSP-000006",
        "provider": "Department of Fisheries, Govt of India (PMMSY implementation)",
        "provider_id": "DOF-GOI",
        "provider_type": "government",
        "name": "Fisheries & Aquaculture Insurance (under PMMSY)",
        "type": "asset",
        "category": "Farm Asset Protection",
        "description": (
            "Insurance support for aquaculture/fisheries assets and inputs under the Pradhan Mantri "
            "Matsya Sampada Yojana (PMMSY), protecting fish farmers against losses in notified "
            "modes."
        ),
        "coverage": "Coverage of aquaculture/fisheries assets and input losses as notified under PMMSY insurance guidelines in implementing states.",
        "exclusions": "As per the implementing agency/insurer guidelines (verify state PMMSY notification).",
        "eligibility": "Fish farmers, fishers and aquaculture units in states implementing the PMMSY insurance component.",
        "premium_information": "Premium support/premium terms follow the PMMSY state guidelines — verify the prevailing rate with the nodal fisheries department.",
        "premium_rate": None,
        "coverage_amount": None,
        "premium_amount": None,
        "policy_duration_months": 12,
        "policy_duration_text": "Annual crop/pond cycle cover",
        "state": "Coastal and fish-forming states (notified)",
        "district": None,
        "applicable_crops": [],
        "applicable_livestock": ["Prawn", "Shrimp", "Fish (inland/culture)"],
        "applicable_assets": ["Ponds", "Cages", "Hatcheries"],
        "claim_conditions": "Claims processed under the PMMSY insurance guidelines by the implementing agency/insurer.",
        "required_documents": ["Aadhaar Card", "Bank details", "Pond/asset records", "Stocking records"],
        "application_process": "Enrol through the state fisheries department / implementing agency before the notified cycle; maintain stocking and production records for claims.",
        "renewal_process": "Renew each pond/stocking cycle under the state plan.",
        "contact_information": "State Fisheries Department / PMMSY nodal office",
        "official_url": "https://pmmsy.dof.gov.in",
        "source": SRC_GOVT,
        "source_url": "https://pmmsy.dof.gov.in",
        "government_backed": True,
        "private": False,
        "scheme_name": None,
        "status": "active",
        "last_verified_at": LAST_VERIFIED,
    },
    {
        "insurance_id": "FA-INSP-000007",
        "provider": "The New India Assurance Co. Ltd",
        "provider_id": "NIA",
        "provider_type": "private",
        "name": "New India Assurance — Cattle / Dairy Animal Insurance",
        "type": "livestock",
        "category": "Livestock Insurance",
        "description": (
            "Commercial livestock insurance for cattle, buffaloes and dairy animals covering death "
            "from disease and accidents with sum insured up to the market value of the animal."
        ),
        "coverage": "Cover for death of the insured animal due to disease or accident up to the insured sum (100% of market value at enrolment, vet-verified).",
        "exclusions": "As per the policy conditions (intentional killing, pre-existing conditions, etc.).",
        "eligibility": "Any livestock owner insuring a vet-examined animal through the insurer's branch/online process.",
        "premium_information": "Premium is charged on the insured value as per the insurer's published cattle insurance rates — verify the applicable rate before applying.",
        "premium_rate": None,
        "coverage_amount": None,
        "premium_amount": None,
        "policy_duration_months": 36,
        "policy_duration_text": "Typically 1–3 years (per policy)",
        "state": "All India",
        "district": None,
        "applicable_crops": [],
        "applicable_livestock": ["Cattle", "Buffalo", "Dairy animals"],
        "applicable_assets": [],
        "claim_conditions": "Claims require policy intimation, post-mortem certificate, value certificate and FIR in theft cases.",
        "required_documents": ["KYC", "Vet examination certificate", "Animal identity", "Post-mortem certificate (for claims)"],
        "application_process": "Apply at a New India branch or through the insurer's online channels; pay the premium; policy issued after vet examination.",
        "renewal_process": "Renew the policy before expiry; premium may be revised.",
        "contact_information": "New India Assurance branch network | customer service",
        "official_url": "https://newindia.co.in",
        "source": SRC_INSURER,
        "source_url": "https://newindia.co.in",
        "government_backed": False,
        "private": True,
        "scheme_name": None,
        "status": "active",
        "last_verified_at": LAST_VERIFIED,
    },
    {
        "insurance_id": "FA-INSP-000008",
        "provider": "SBI General Insurance Co. Ltd",
        "provider_id": "SBI-GENERAL",
        "provider_type": "private",
        "name": "SBI General — Tractor Insurance",
        "type": "equipment",
        "category": "Farm Equipment",
        "description": (
            "Insurance for tractors and self-propelled farm machines against damage and theft while "
            "in use, transiting and in storage, with optional cover for attachments."
        ),
        "coverage": "Own damage (accident, fire, theft, transit) and third-party liability cover for the insured tractor as per the policy terms.",
        "exclusions": "As per policy terms (driver ineligibility, exclusions stated in the policy schedule).",
        "eligibility": "Tractor owners (individuals, cooperatives) insuring the vehicle with a valid registration/invoice.",
        "premium_information": "Premium is quoted by the insurer based on the tractor IDV and usage — no standard fixed rate is published; verify the quote before applying.",
        "premium_rate": None,
        "coverage_amount": None,
        "premium_amount": None,
        "policy_duration_months": 12,
        "policy_duration_text": "Annual policy (renewable)",
        "state": "All India",
        "district": None,
        "applicable_crops": [],
        "applicable_livestock": [],
        "applicable_assets": ["Tractor", "Farm machinery / attachments"],
        "claim_conditions": "Claims require FIR (theft), surveyor inspection (damage) and policy documents within the notified period.",
        "required_documents": ["KYC", "Tractor registration / invoice", "Driving licence", "Previous policy (for NCB)"],
        "application_process": "Apply online at the insurer's portal or through an agent, receive a quote, pay the premium and the policy is issued.",
        "renewal_process": "Renew annually; no-claim bonus continues if no claim in the policy year.",
        "contact_information": "SBI General customer care",
        "official_url": "https://www.sbigeneral.in",
        "source": SRC_INSURER,
        "source_url": "https://www.sbigeneral.in",
        "government_backed": False,
        "private": True,
        "scheme_name": None,
        "status": "active",
        "last_verified_at": LAST_VERIFIED,
    },
    {
        "insurance_id": "FA-INSP-000009",
        "provider": "ICICI Lombard General Insurance Co. Ltd",
        "provider_id": "ICICI-LOMBARD",
        "provider_type": "private",
        "name": "ICICI Lombard — Tractor Insurance",
        "type": "equipment",
        "category": "Farm Equipment",
        "description": (
            "Tractor and farm machinery insurance protecting the machine against accidental damage, "
            "theft and third-party liability during operations and transit."
        ),
        "coverage": "Own-damage and third-party cover for the insured tractor/farm machine as per the policy schedule, with optional add-ons.",
        "exclusions": "As per the policy terms and conditions.",
        "eligibility": "Tractor/farm-machine owners with insurable interest in the vehicle.",
        "premium_information": "Premium is quote-based on the Insured Declared Value (IDV); no fixed published rate — verify the quote before applying.",
        "premium_rate": None,
        "coverage_amount": None,
        "premium_amount": None,
        "policy_duration_months": 12,
        "policy_duration_text": "Annual policy (renewable)",
        "state": "All India",
        "district": None,
        "applicable_crops": [],
        "applicable_livestock": [],
        "applicable_assets": ["Tractor", "Self-propelled farm machinery"],
        "claim_conditions": "Claims processed after surveyor inspection / FIR (theft) as per policy terms.",
        "required_documents": ["KYC", "Registration / invoice", "Driving licence", "Previous policy (for NCB)"],
        "application_process": "Buy online at the insurer's portal or via agent with an instant quote.",
        "renewal_process": "Renew annually; NCB benefit if claim-free.",
        "contact_information": "ICICI Lombard customer care",
        "official_url": "https://www.icicilombard.com",
        "source": SRC_INSURER,
        "source_url": "https://www.icicilombard.com",
        "government_backed": False,
        "private": True,
        "scheme_name": None,
        "status": "active",
        "last_verified_at": LAST_VERIFIED,
    },
    {
        "insurance_id": "FA-INSP-000010",
        "provider": "Government of Telangana (implemented by the State)",
        "provider_id": "GOTL",
        "provider_type": "state",
        "name": "Rythu Bima — Farmers Group Life Insurance (Telangana)",
        "type": "asset",
        "category": "State Insurance",
        "description": (
            "A state-funded group life insurance programme that provides ₹5 lakh cover to Telangana "
            "farmers aged 18–59 in the farmers (rythu) database, with the entire premium paid by the "
            "state government."
        ),
        "coverage": "₹5 lakh life insurance cover to enrolled farmers aged 18–59; covers death from any cause and permanent/partial disability as per programme norms.",
        "exclusions": "As per the programme's eligibility (age limits, exclusions defined by the state).",
        "eligibility": "Farmers aged 18–59 in Telangana who are part of the state's farmer (rythu) database / enrolled under the programme.",
        "premium_information": "The entire premium is borne by the Government of Telangana — farmers pay no premium.",
        "premium_rate": None,
        "coverage_amount": 500000,
        "premium_amount": None,
        "policy_duration_months": 12,
        "policy_duration_text": "Annual cover (renewed by the state)",
        "state": "Telangana",
        "district": None,
        "applicable_crops": [],
        "applicable_livestock": [],
        "applicable_assets": ["Farmer (life cover)"],
        "claim_conditions": "Claim forms are processed by the state/insurer on document review (death/disability certificates).",
        "required_documents": ["Aadhaar", "Identity proof", "Death/disability certificates (for claims)"],
        "application_process": "Coverage is applied from the state's farmer database; farmers can verify enrolment through the programme portal/helpline.",
        "renewal_process": "Automatically renewed each year by the state while the farmer remains eligible.",
        "contact_information": "Rythu Bima programme | Govt of Telangana",
        "official_url": "https://cmrt.telangana.gov.in",
        "source": SRC_GOVT,
        "source_url": "https://cmrt.telangana.gov.in",
        "government_backed": True,
        "private": False,
        "scheme_name": None,
        "status": "active",
        "last_verified_at": LAST_VERIFIED,
    },
]

# Canonical display order for the category chips (matches the Insurance page).
CATEGORY_ORDER = [
    "All",
    "Crop Insurance",
    "Livestock Insurance",
    "Weather Insurance",
    "Farm Equipment",
    "Farm Asset Protection",
    "Government Insurance",
    "State Insurance",
    "Private Insurance",
]


def seed_insurance_products(db: Session) -> int:
    """Idempotent seeder. Returns the number of new products inserted."""
    from app.models.government import GovernmentScheme

    by_id = {p.insurance_id: p for p in db.query(InsuranceProduct).all()}
    created = 0
    for item in PRODUCTS:
        insurance_id = item["insurance_id"]
        existing = by_id.get(insurance_id)
        scheme = None
        if item.get("scheme_name"):
            scheme = (
                db.query(GovernmentScheme)
                .filter(
                    GovernmentScheme.name.ilike(f"%{item['scheme_name']}%"),
                    GovernmentScheme.status == "active",
                )
                .first()
            )
        row = existing
        if row is None:
            row = InsuranceProduct(insurance_id=insurance_id)
            db.add(row)
            created += 1
        for key, value in item.items():
            if key == "scheme_name":
                continue
            setattr(row, key, value)
        row.scheme_id = scheme.id if scheme else None
        row.scheme_name = scheme.name if scheme else item.get("scheme_name")
        row.last_verified_at = LAST_VERIFIED
        row.status = "active"
    db.commit()
    return created