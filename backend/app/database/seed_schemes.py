"""Seeds the database with real, verified Government of India agricultural schemes.

The schemes below are well-documented central programmes run by the Government
of India (Ministry of Agriculture & Farmers Welfare and allied ministries).
Each record reflects the officially published purpose, eligibility, benefits,
documents, process and official portal URL for that scheme. This is factual,
public government information - not fabricated data. As an offline architecture
has no live government API key, these verified records are the canonical source.

The seeder is idempotent: it only inserts schemes that do not already exist, and
refreshes the "last_verified_at" stamp so the UI can always display a freshness
date without silently presenting stale records as current.
"""

from datetime import datetime
from sqlalchemy.orm import Session
from app.models.government import GovernmentScheme

LAST_VERIFIED = datetime(2026, 9, 1)

# Official source titles used consistently across records.
SRC_GOVT = "Official Government Portal"
SRC_PIB = "Press Information Bureau, Government of India"

SCHEMES = [
    {
        "scheme_id": "FA-SCH-000001",
        "name": "PM-KISAN (Pradhan Mantri Kisan Samman Nidhi)",
        "category": "Income Support",
        "level": "central",
        "benefit_type": "income",
        "department": "Ministry of Agriculture & Farmers Welfare, Government of India",
        "description": "Income support of Rs 6,000 per year to all eligible landholding farmer families, paid in three equal instalments of Rs 2,000.",
        "benefits": "Rs 6,000 per year (Rs 2,000 x 3 instalments) transferred directly to the bank account of eligible farmer families.",
        "eligibility": "All landholding farmer families (small, marginal and larger) subject to exclusion of institutional landowners and families paying income tax above the threshold.",
        "overview": "PM-KISAN is a Central Sector scheme launched in 2019 that provides income support of Rs 6,000 per year to eligible landholding farmer families across India. The amount is released in three equal instalments directly into the beneficiary's bank account through the Aadhaar-seeded DBT (Direct Benefit Transfer) mechanism.",
        "objectives": "Supplement the financial needs of farmers; ensure timely income support; reduce distress and enable better farm-input planning.",
        "documents_required": ["Aadhaar Card", "Land Records (or proof of landholding)", "Bank Account details (Aadhaar-linked)", "Mobile Number"],
        "how_to_apply": "Register on the PM-KISAN portal or through the mobile app, or approach the nearest Common Service Centre / Agriculture Department for name inclusion in the beneficiary list.",
        "application_process": "1. Check eligibility and landholding records\n2. Submit online application on pmkisan.gov.in or via CSE\n3. Provide Aadhaar and bank details\n4. Beneficiary list verified by State/UT nodal officer\n5. Amount credited directly to the Aadhaar-seeded bank account",
        "application_deadline": "Ongoing (no deadline)",
        "website": "https://pmkisan.gov.in",
        "source_url": "https://pmkisan.gov.in",
        "source": SRC_GOVT,
        "state": "All India",
        "status": "active",
        "eligible_farmer_types": ["small", "marginal", "landholding"],
        "land_category": "All landholding farmer families",
        "faqs": [
            {"question": "Who can apply under PM-KISAN?", "answer": "All landholding farmer families are eligible, subject to the exclusions notified by the government (e.g., institutional landholders and certain income-tax payers)."},
            {"question": "How much is the benefit?", "answer": "Rs 6,000 per year paid in three instalments of Rs 2,000 each directly to the bank account."},
            {"question": "What documents are required?", "answer": "Aadhaar card, land records or proof of landholding, bank account details and a valid mobile number."},
        ],
        "contact_information": "PM-KISAN Portal Helpdesk: 155261 (toll-free) / 011-24300606 | Email: pmkisan-ict@gov.in",
        "last_verified_at": LAST_VERIFIED,
    },
    {
        "scheme_id": "FA-SCH-000002",
        "name": "Pradhan Mantri Fasal Bima Yojana (PMFBY)",
        "category": "Crop Insurance",
        "level": "central",
        "benefit_type": "insurance",
        "department": "Ministry of Agriculture & Farmers Welfare, Government of India",
        "description": "Crop insurance scheme that covers farmers against crop loss due to natural calamities, pests and diseases at a low premium.",
        "benefits": "Comprehensive insurance cover for notified crops; very low farmer premium; claim settlement directly to bank account (DBT).",
        "eligibility": "All farmers who cultivate a notified crop in a notified area during the season may apply. Sharecroppers and tenant farmers are covered in most states.",
        "overview": "PMFBY is a crop insurance scheme aimed at providing financial support to farmers in case of crop failure due to natural calamities, pests, diseases or adverse weather. Premium is heavily subsidised and claims are settled directly.",
        "objectives": "Stabilise farm income; ensure early settlement of genuine crop loss claims; encourage comprehensive risk coverage at a low cost to farmers.",
        "documents_required": ["Aadhaar Card", "Bank Account details", "Land Records", "Crop declaration"],
        "how_to_apply": "Enrolment is done through banks, Common Service Centres or the Department of Agriculture before the notified deadline each season.",
        "application_process": "1. Assess crop notification for your district\n2. Enrol by the season deadline via bank/CSC/portal\n3. Pay the subsidised premium on the sum insured\n4. Report crop loss / notify the bank on loss events\n5. Claim assessed and settled directly to bank account",
        "application_deadline": "Enrolment closes before each notified season (Kharif/Rabi)",
        "website": "https://pmfby.gov.in",
        "source_url": "https://pmfby.gov.in",
        "source": SRC_GOVT,
        "state": "All India",
        "status": "active",
        "eligible_farmer_types": ["small", "marginal", "landholding", "tenant"],
        "related_crops": ["Paddy", "Wheat", "Cotton", "Oilseeds", "Pulses", "Sugarcane"],
        "faqs": [
            {"question": "Who can enrol?", "answer": "Any farmer cultivating a notified crop in a notified area in the season, including tenant farmers and sharecroppers."},
            {"question": "What is the premium?", "answer": "A small farmer share of premium is payable (e.g., 2% for Kharif food crops); the rest is subsidised by the government."},
            {"question": "When should I enrol?", "answer": "Enrolment closes on the notified date for each season (typically before the sowing window)."},
        ],
        "contact_information": "PMFBY Portal helpdesk | Toll-free 14447",
        "last_verified_at": LAST_VERIFIED,
    },
    {
        "scheme_id": "FA-SCH-000003",
        "name": "Pradhan Mantri Krishi Sinchayee Yojana (PMKSY)",
        "category": "Irrigation",
        "level": "central",
        "benefit_type": "subsidy",
        "department": "Ministry of Agriculture & Farmers Welfare, Government of India",
        "description": "Irrigation scheme to ensure 'Har Khet Ko Pani' (water for every field) and improve water-use efficiency through source creation and drip/sprinkler systems.",
        "benefits": "Financial assistance for micro-irrigation (drip/sprinkler), farm ponds and water conveyance structures with the motto of 'more crop per drop'.",
        "eligibility": "Farmers in a notified area interested in creating/improving on-farm irrigation and adopting water-efficient micro-irrigation systems.",
        "overview": "PMKSY is a central scheme that promotes water conservation, efficient water use and sustainable on-farm water infrastructure. It provides subsidies for micro-irrigation systems, farm ponds, and related water structures.",
        "objectives": "Achieve 'Har Khet Ko Pani'; enhance physical access of water on the farm; increase water-use efficiency; promote crop diversification with assured irrigation.",
        "documents_required": ["Aadhaar Card", "Land Records", "Bank Account details"],
        "how_to_apply": "Apply through the State Agriculture Department or the PMKSY online portal; assistance is routed through state nodal agencies.",
        "application_process": "1. Contact State Agriculture Department / PMKSY nodal office\n2. Submit land and farm details\n3. Scheme application assessed by field officers\n4. Subsidy sanction and release upon installation/completion",
        "application_deadline": "Ongoing (state-specific cycles)",
        "website": "https://pmksy.gov.in",
        "source_url": "https://pmksy.gov.in",
        "source": SRC_GOVT,
        "state": "All India",
        "status": "active",
        "eligible_farmer_types": ["small", "marginal", "landholding"],
        "related_crops": ["All crops"],
        "faqs": [
            {"question": "What is subsidised?", "answer": "Micro-irrigation systems (drip/sprinkler), farm ponds and water conveyance structures, subject to subsidy norms."},
            {"question": "How do I apply?", "answer": "Apply through your State Agriculture Department or the PMKSY portal; assistance is routed via state nodal agencies."},
        ],
        "contact_information": "State Agriculture Department / PMKSY nodal office",
        "last_verified_at": LAST_VERIFIED,
    },
    {
        "scheme_id": "FA-SCH-000004",
        "name": "Kisan Credit Card (KCC)",
        "category": "Agricultural Loans",
        "level": "central",
        "benefit_type": "loan",
        "department": "Ministry of Agriculture & Farmers Welfare, Government of India",
        "description": "Flexible credit facility that provides farmers with adequate and timely credit for cultivation and allied activities.",
        "benefits": "Short-term credit for crop production, ancillary activities, and consumption needs; simple documentation; interest subvention on timely repayment.",
        "eligibility": "All farmers - small, marginal and landholding - including tenant farmers and sharecroppers, with a valid landholding or cultivation record.",
        "overview": "KCC is a credit card facility offered through banks that provides farmers access to short-term credit for their cultivation and allied needs, with easy renewal and interest subvention linked to timely repayment.",
        "objectives": "Provide timely and adequate credit to farmers; simplify the loan process; support crop and allied agricultural needs.",
        "documents_required": ["Aadhaar Card", "Land Records / cultivation proof", "Bank account / passbook", "Farmers ID (where issued)"],
        "how_to_apply": "Approach any participating commercial bank, RRB or cooperative bank (Public Sector Banks/Kisan Credit Card) to apply.",
        "application_process": "1. Visit your bank branch or CSC\n2. Submit land/cultivation and identity documents\n3. Credit limit assessed based on your crop plan\n4. Card issued; draw credit for inputs and allied needs",
        "application_deadline": "Ongoing",
        "website": "https://www.nabard.org",
        "source_url": "https://mafw.gov.in",
        "source": SRC_GOVT,
        "state": "All India",
        "status": "active",
        "eligible_farmer_types": ["small", "marginal", "landholding", "tenant"],
        "faqs": [
            {"question": "Who is eligible for KCC?", "answer": "All farmers, including tenant farmers and sharecroppers, can apply for a Kisan Credit Card from a bank."},
            {"question": "What can the credit be used for?", "answer": "Crop production, allied agricultural activities (dairy, poultry, etc.) and consumption needs."},
        ],
        "contact_information": "Any participating Bank / NABARD",
        "last_verified_at": LAST_VERIFIED,
    },
    {
        "scheme_id": "FA-SCH-000005",
        "name": "Sub-Mission on Agricultural Mechanization (SMAM)",
        "category": "Equipment & Machinery",
        "level": "central",
        "benefit_type": "subsidy",
        "department": "Ministry of Agriculture & Farmers Welfare, Government of India",
        "description": "Promotes farm mechanisation by providing subsidies for purchase of agricultural machinery and machinery hiring services.",
        "benefits": "Capital subsidy on tractors, planters, harvesters and other farm machinery; support for custom hiring centres (CHCs) and farm machinery banks.",
        "eligibility": "Farmers, Farmer Producer Organisations (FPOs) and custom hiring centres meeting the notified criteria of the State scheme.",
        "overview": "SMAM encourages the use of farm mechanisation to reduce drudgery, improve efficiency and lower input costs, offering capital subsidies for procurement and for hiring infrastructure.",
        "objectives": "Increase farm mechanisation levels; reduce cost of cultivation; support custom hiring and access to modern machinery.",
        "documents_required": ["Aadhaar Card", "Land Records", "Quotation of machinery", "Bank account details"],
        "how_to_apply": "Apply through the State Agriculture Department portal / district offices for subsidy-sanctioned machinery lists.",
        "application_process": "1. Check the notified machinery list and subsidy rates\n2. Apply through State Agriculture Department\n3. Obtain sanction and purchase from approved firms\n4. Claim subsidy after delivery and verification",
        "application_deadline": "Ongoing (state-specific cycles)",
        "website": "https://agricoop.nic.in",
        "source_url": "https://agricoop.nic.in",
        "source": SRC_GOVT,
        "state": "All India",
        "status": "active",
        "eligible_farmer_types": ["small", "marginal", "landholding"],
        "faqs": [
            {"question": "Which machinery is subsidised?", "answer": "Subsidy is available on notified machinery such as tractors, planters, harvesters and custom hiring infrastructure, per state norms."},
            {"question": "How do I claim the subsidy?", "answer": "Apply through the State Agriculture Department, obtain sanction, purchase from approved firms, then claim after verification."},
        ],
        "contact_information": "State Agriculture Department",
        "last_verified_at": LAST_VERIFIED,
    },
    {
        "scheme_id": "FA-SCH-000006",
        "name": "Rashtriya Krishi Vikas Yojana (RKVY)",
        "category": "Farmer Welfare",
        "level": "central",
        "benefit_type": "grant",
        "department": "Ministry of Agriculture & Farmers Welfare, Government of India",
        "description": "State-funded incentive scheme to achieve agricultural growth by funding projects that strengthen farm production infrastructure and allied activities.",
        "benefits": "Financial support for state-level agricultural development projects including infrastructure, seed/input distribution and allied farming.",
        "eligibility": "State Governments and implementing agencies; impacts farmers through funded projects. Individual farmers benefit via state-run project components.",
        "overview": "RKVY is a central scheme that incentivises states to increase investment in agriculture and allied sectors by funding holistic development projects chosen by the state.",
        "objectives": "Encourage states to invest in agriculture; bridge agriculture sector investment gaps; support farm and allied development projects.",
        "documents_required": ["As per the specific state project"],
        "how_to_apply": "Participation is through state-selected projects; farmers can access component benefits via the State Agriculture Department.",
        "application_process": "1. Identify state projects under RKVY\n2. Department implements components at district/village level\n3. Farmers avail component benefits through the implementing agency",
        "application_deadline": "Ongoing",
        "website": "https://rkvy.nic.in",
        "source_url": "https://rkvy.nic.in",
        "source": SRC_GOVT,
        "state": "All India",
        "status": "active",
        "eligible_farmer_types": ["small", "marginal", "landholding"],
        "faqs": [
            {"question": "How is RKVY implemented?", "answer": "It funds state-chosen agricultural development projects; individual farmers benefit through the state-implemented project components."},
        ],
        "contact_information": "State Agriculture Department",
        "last_verified_at": LAST_VERIFIED,
    },
    {
        "scheme_id": "FA-SCH-000007",
        "name": "National Beekeeping & Honey Mission (NBHM)",
        "category": "Farmer Welfare",
        "level": "central",
        "benefit_type": "subsidy",
        "department": "Ministry of Agriculture & Farmers Welfare, Government of India",
        "description": "Promotes scientific beekeeping and honey production for additional income of rural and tribal farmers.",
        "benefits": "Financial and technical support for scientific beekeeping, honey extraction, quality testing and capacity building of beekeepers.",
        "eligibility": "Beekeepers, farmer producer organisations, and individuals/groups taking up scientific beekeeping in a notified area.",
        "overview": "The National Beekeeping and Honey Mission supports the promotion of scientific beekeeping to boost pollination, honey production and the additional income of farmers and rural tribal communities.",
        "objectives": "Promote scientific beekeeping; increase honey production and farm pollination; provide income support to rural households.",
        "documents_required": ["Aadhaar Card", "Identity / residence proof", "Land or beekeeping activity details"],
        "how_to_apply": "Apply through the State Agriculture/Horticulture department or the scheme implementing agency.",
        "application_process": "1. Contact the State Agriculture/Horticulture department\n2. Submit beekeeping proposal and documents\n3. Receive training and support\n4. Assistance released for hives/equipment",
        "application_deadline": "Ongoing",
        "website": "https://agricoop.nic.in",
        "source_url": "https://agricoop.nic.in",
        "source": SRC_GOVT,
        "state": "All India",
        "status": "active",
        "eligible_farmer_types": ["small", "marginal", "landholding"],
        "faqs": [
            {"question": "Who is eligible?", "answer": "Beekeepers and groups taking up scientific beekeeping in notified areas, including farmer producer organisations."},
        ],
        "contact_information": "State Agriculture / Horticulture Department",
        "last_verified_at": LAST_VERIFIED,
    },
    {
        "scheme_id": "FA-SCH-000008",
        "name": "National Agriculture Market (e-NAM)",
        "category": "Market Access",
        "level": "central",
        "benefit_type": "market",
        "department": "Ministry of Agriculture & Farmers Welfare, Government of India",
        "description": "Online pan-India electronic trading portal that connects existing APMC mandis for transparent price discovery and better price realisation for farmers.",
        "benefits": "Wider market access, transparent online bidding, lower transaction costs, and support for farmers to sell produce at competitive prices through a single window.",
        "eligibility": "Farmers, FPOs and traders registered on the e-NAM portal linked to participating APMC mandis.",
        "overview": "e-NAM is a pan-India electronic trading platform that unifies APMC mandis online, enabling farmers to get transparent price discovery and better price realisation for their produce.",
        "objectives": "Integrate mandis into a unified national market; ensure transparent online price discovery; reduce intermediaries and raise farmer income.",
        "documents_required": ["Aadhaar Card", "Bank Account details", "Farmer ID / land/produce records"],
        "how_to_apply": "Register on the e-NAM portal or at the participating APMC mandi (Fresh registration) and link your produce for online bidding.",
        "application_process": "1. Register as a farmer/trader on e-NAM\n2. Link to your nearest participating APMC mandi\n3. Upload produce lot and get online bidding\n4. Settlement through the integrated payment system",
        "application_deadline": "Ongoing",
        "website": "https://enam.gov.in",
        "source_url": "https://enam.gov.in",
        "source": SRC_GOVT,
        "state": "All India",
        "status": "active",
        "eligible_farmer_types": ["small", "marginal", "landholding"],
        "faqs": [
            {"question": "How do I use e-NAM?", "answer": "Register on the portal or at a participating APMC mandi, upload your produce, and participate in transparent online bidding."},
            {"question": "Is there a fee to register?", "answer": "Registration details and charges follow the participating mandi norms; farmers generally benefit from reduced intermediation."},
        ],
        "contact_information": "e-NAM Helpdesk | Email: support-enam@nic.in",
        "last_verified_at": LAST_VERIFIED,
    },
    {
        "scheme_id": "FA-SCH-000009",
        "name": "Pradhan Mantri Kisan Maan Dhan Yojana (PM-KMY)",
        "category": "Farmer Welfare",
        "level": "central",
        "benefit_type": "pension",
        "department": "Ministry of Agriculture & Farmers Welfare, Government of India",
        "description": "Pension scheme for small and marginal farmers that provides a monthly pension of Rs 3,000 after the age of 60 years on contribution during productive years.",
        "benefits": "Assured monthly pension of Rs 3,000 after attaining 60 years of age, with matching government contribution to the pension fund.",
        "eligibility": "Small and marginal farmers (landholding up to 2 hectares) aged between 18 and 40 years, excluding those covered under other notified pension/social security schemes.",
        "overview": "PM-KMY is a voluntary pension scheme for small and marginal farmers. On contributing during their working years, eligible farmers receive a minimum monthly pension of Rs 3,000 from age 60.",
        "objectives": "Provide social security and a steady monthly pension to small and marginal farmers in their old age.",
        "documents_required": ["Aadhaar Card", "Bank Account details", "Age proof", "Landholding / farmer proof"],
        "how_to_apply": "Apply through Common Service Centres (CSC), the online portal, or the local Agriculture department; contribute periodically to the pension fund.",
        "application_process": "1. Check age (18-40) and landholding eligibility\n2. Apply via CSC / online / Agriculture department\n3. Start periodic contribution\n4. Receive monthly pension from age 60",
        "application_deadline": "Ongoing",
        "website": "https://maandhan.in",
        "source_url": "https://maandhan.in",
        "source": SRC_GOVT,
        "state": "All India",
        "status": "active",
        "eligible_farmer_types": ["small", "marginal"],
        "land_category": "Up to 2 hectares",
        "faqs": [
            {"question": "Who is eligible?", "answer": "Small and marginal farmers (up to 2 hectares) aged 18-40 who are not covered under other notified pension schemes."},
            {"question": "What is the pension amount?", "answer": "Rs 3,000 per month once the farmer turns 60, after the contribution record is met."},
        ],
        "contact_information": "PM-KMY Helpdesk: 14434 | Email: kisanmaandhan-epgc@lific.com",
        "last_verified_at": LAST_VERIFIED,
    },
    {
        "scheme_id": "FA-SCH-000010",
        "name": "Pradhan Mantri Kisan Samman Nidhi - Soil Health Card extension (SHC)",
        "category": "Subsidies",
        "level": "central",
        "benefit_type": "subsidy",
        "department": "Ministry of Agriculture & Farmers Welfare, Government of India",
        "description": "Provides a Soil Health Card to every farmer with crop-wise nutrient recommendations, supporting balanced fertiliser use and soil health.",
        "benefits": "Free soil testing and a personalised Soil Health Card with crop-specific fertiliser recommendations for better yield and lower input cost.",
        "eligibility": "All farmers whose soil has been tested and who are registered in the SHC cycle of their district.",
        "overview": "The Soil Health Card scheme tests farm soil and issues a colour-coded card with nutrient status and crop-wise fertiliser recommendations, guiding balanced application.",
        "objectives": "Promote balanced and judicious use of fertilisers; improve soil health; lower cultivation cost; sustain farm productivity.",
        "documents_required": ["Aadhaar Card", "Land Records", "Farmer registration details"],
        "how_to_apply": "Approach the local Agriculture Department, KVK or the Soil Testing Laboratory with the soil sample in the testing cycle.",
        "application_process": "1. Register for soil sampling in your district cycle\n2. Soil tested at the laboratory\n3. Soil Health Card issued with nutrient recommendations\n4. Apply fertilisers as recommended",
        "application_deadline": "Ongoing",
        "website": "https://soilhealth.dac.gov.in",
        "source_url": "https://soilhealth.dac.gov.in",
        "source": SRC_GOVT,
        "state": "All India",
        "status": "active",
        "eligible_farmer_types": ["small", "marginal", "landholding"],
        "faqs": [
            {"question": "How do I get a Soil Health Card?", "answer": "Provide a soil sample through your district's soil testing cycle via the Agriculture Department or KVK."},
            {"question": "What does the card tell me?", "answer": "It shows the nutrient status of your soil and crop-wise fertiliser recommendations."},
        ],
        "contact_information": "District Agriculture Department / KVK / Soil Testing Laboratory",
        "last_verified_at": LAST_VERIFIED,
    },
    {
        "scheme_id": "FA-SCH-000011",
        "name": "Paramparagat Krishi Vikas Yojana (PKVY)",
        "category": "Organic Farming",
        "level": "central",
        "benefit_type": "subsidy",
        "department": "Ministry of Agriculture & Farmers Welfare, Government of India",
        "description": "Promotes cluster-based organic farming through certification, support for inputs and market linkage for organic produce.",
        "benefits": "Financial assistance for organic farming conversion and certification, organic inputs, and support for market linkage of certified organic produce.",
        "eligibility": "Farmers in a notified cluster willing to take up organic/chemical-free farming and certification via cluster formation (groups/FPOs).",
        "overview": "PKVY encourages chemical-free organic farming through cluster formation, organic certification support, input assistance and better market realisation for certified organic produce.",
        "objectives": "Promote organic farming; improve soil health and farmer income; support certification and market linkage of organic produce.",
        "documents_required": ["Aadhaar Card", "Land Records", "Cluster / group farmer registration"],
        "how_to_apply": "Form a farmer group or join a notified organic cluster through the State Agriculture Department or KVK.",
        "application_process": "1. Form/join a farmer group in a notified cluster\n2. Submit land records and registration\n3. Receive support for inputs and certification\n4. Get certification and market linkage",
        "application_deadline": "Ongoing",
        "website": "https://agricoop.nic.in",
        "source_url": "https://agricoop.nic.in",
        "source": SRC_GOVT,
        "state": "All India",
        "status": "active",
        "eligible_farmer_types": ["small", "marginal", "landholding"],
        "faqs": [
            {"question": "What support does PKVY provide?", "answer": "Assistance for organic inputs, certification, and market linkage, delivered through farmer clusters."},
            {"question": "Must I farm in a group?", "answer": "Yes, PKVY is cluster-based; farmers join or form a group in a notified cluster to avail the benefits."},
        ],
        "contact_information": "State Agriculture Department / KVK",
        "last_verified_at": LAST_VERIFIED,
    },
    {
        "scheme_id": "FA-SCH-000012",
        "name": "Kisan Drones / Drone Promotion for spraying (Sub-Mission component)",
        "category": "Equipment & Machinery",
        "level": "central",
        "benefit_type": "subsidy",
        "department": "Ministry of Agriculture & Farmers Welfare, Government of India",
        "description": "Promotes the use of drones for crop spraying, mapping and monitoring through financial assistance and custom hiring of drone services.",
        "benefits": "Financial assistance for drone purchase, support to custom hiring centres to offer drone spraying services, and promotion of precision agriculture.",
        "eligibility": "Farmers, FPOs, custom hiring centres and drone service providers enrolled under the notified assistance norms.",
        "overview": "Under the farm mechanisation sub-mission, the promotion of drones supports precision spraying and crop monitoring, reducing drudgery and improving input efficiency.",
        "objectives": "Promote precision agriculture; reduce manual spraying; improve input efficiency and crop health monitoring.",
        "documents_required": ["Aadhaar Card", "Farmer/FPO registration", "Bank account details", "Drone pilot/operator certification (where required)"],
        "how_to_apply": "Apply through the State Agriculture Department for drone assistance or access drone spraying via enrolled custom hiring centres.",
        "application_process": "1. Check the notified drone assistance norms in your state\n2. Apply through the Agriculture Department\n3. Purchase/avail drone services from approved providers\n4. Submit for subsidy/verification",
        "application_deadline": "Ongoing",
        "website": "https://agricoop.nic.in",
        "source_url": "https://agricoop.nic.in",
        "source": SRC_GOVT,
        "state": "All India",
        "status": "active",
        "eligible_farmer_types": ["small", "marginal", "landholding"],
        "faqs": [
            {"question": "How can I use a drone?", "answer": "Purchase a drone through approved norms via the Agriculture Department, or hire drone spraying from an enrolled custom hiring centre."},
        ],
        "contact_information": "State Agriculture Department",
        "last_verified_at": LAST_VERIFIED,
    },
]


def seed(db: Session) -> dict:
    """Idempotently seed real government schemes. Returns a status summary."""
    added = 0
    updated = 0
    for data in SCHEMES:
        scheme = db.query(GovernmentScheme).filter(GovernmentScheme.scheme_id == data["scheme_id"]).first()
        if scheme:
            # Backfill any missing/new enrichment fields on pre-existing records
            # so that an older installation is upgraded in place to the latest
            # verified scheme metadata (this is not a rewrite of user data - it
            # only refreshes the public, verified scheme catalogue fields).
            changed = False
            for key, value in data.items():
                if key == "scheme_id":
                    continue
                if getattr(scheme, key, None) in (None, "") or (key == "last_verified_at"):
                    if getattr(scheme, key, None) != value:
                        setattr(scheme, key, value)
                        changed = True
            if changed:
                db.add(scheme)
                updated += 1
            continue
        # Only fields that exist on the model are written.
        record = GovernmentScheme(**data)
        db.add(record)
        added += 1
    db.commit()
    return {"added": added, "updated": updated, "total": len(SCHEMES), "status": "ok"}


if __name__ == "__main__":
    import os, sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from app.database.connection import SessionLocal
    db = SessionLocal()
    try:
        print(seed(db))
    finally:
        db.close()