"""
Database Seeder for 240 Farm Techniques across 11 Major Categories.

Categories (matching the Farm Techniques page horizontal filter pills):
 1. Soil            20  6. Organic         24  11. Storage         22
 2. Seeds           18  7. Crops           34
 3. Irrigation      22  8. Livestock       18
 4. Fertilizer      20  9. Smart Farming   20
 5. Pest Control    24  10. Harvesting     18

Every technique ships genuine, category-accurate detail content (materials,
steps, tips, benefits, precautions, common mistakes). The seeder is idempotent
and self-healing: if the published technique set does not exactly match this
module's canonical catalog, the table is rebuilt from scratch.
"""

from sqlalchemy.orm import Session
from app.models.technique import Technique

import json


def _enc(val):
    return json.dumps(val) if isinstance(val, list) else val

CATEGORY_META = {
    "Soil":               {"icon": "fa-mountain",  "color": "#8B6F47"},
    "Seeds":              {"icon": "fa-seedling",  "color": "#2D8659"},
    "Irrigation":         {"icon": "fa-droplet",   "color": "#1565C0"},
    "Fertilizer":         {"icon": "fa-flask-vial", "color": "#B7791F"},
    "Pest Control":       {"icon": "fa-bug",       "color": "#C62828"},
    "Organic":            {"icon": "fa-leaf",      "color": "#52B788"},
    "Crops":              {"icon": "fa-wheat-awn", "color": "#40916C"},
    "Livestock":          {"icon": "fa-cow",       "color": "#6A1B9A"},
    "Smart Farming":      {"icon": "fa-microchip", "color": "#7c3aed"},
    "Harvesting":         {"icon": "fa-tractor",   "color": "#4E342E"},
    "Storage":            {"icon": "fa-warehouse", "color": "#0F2E1E"},
}

# Category-accurate detail templates. {crop} is replaced per-technique.
DETAILS = {
    "Soil": {
        "materials": ["Soil testing kit or lab sample bag", "Spade, hoe and garden rake", "Organic compost or farmyard manure", "Lime/gypsum (as per soil test)", "Mulch or cover-crop seeds"],
        "steps": ["Collect a representative soil sample from multiple spots in the field.", "Send the sample for pH, EC and nutrient testing before ploughing.", "Work the soil to a fine tilth while the moisture is right for turning.", "Mix in organic matter or the recommended amendment evenly across the field.", "Level the bed and lay mulch or sow a cover-crop to protect the surface."],
        "tips": "Improve one patch of soil at a time so the learning and the amendment cost stay manageable.",
        "benefits": ["Better root penetration and aeration", "Improved water and nutrient holding capacity", "Healthier microbial life in the soil", "Consistent plant establishment and growth"],
        "precautions": ["Do not plough wet soil as it destroys its structure", "Never guess lime/gysum doses; always follow the soil test value", "Avoid burning crop residue in the field", "Keep livestock and vehicles off freshly tilled beds"],
        "common_mistakes": ["Sampling from only one corner of the field", "Applying amendments without a soil test", "Over-ploughing and pulverising the topsoil", "Ignoring drainage before soil treatment"],
    },
    "Seeds": {
        "materials": ["Good-quality certified seed", "Seed treatment chemicals or bio-agents", "Clean water for soaking", "Shade cloth or clean floor for drying", "Airtight seed storage bags"],
        "steps": ["Buy certified, disease-free seed from a reliable source.", "Do a quick germination test on a sample lot before sowing.", "Soak or treat the seed with the recommended bio-agent or fungicide.", "Dry treated seed in shade, never in direct sun.", "Store seed in an airtight container in a cool, dry place until sowing."],
        "tips": "Treating seed with Trichoderma before sowing gives early protection against soil-borne diseases.",
        "benefits": ["Higher and uniform germination", "Fewer seed-borne diseases", "Stronger seedlings that withstand transplant shock", "Better field establishment and yield"],
        "precautions": ["Do not soak seed for too long or germination will drop", "Keep treated seed away from children and livestock", "Never store moist seed", "Do not reuse hybrid seed for the next crop"],
        "common_mistakes": ["Sowing seed without any treatment", "Using seed past its viability", "Soaking in hot water without checking temperature", "Storing seed next to fertilizers and chemicals"],
    },
    "Irrigation": {
        "materials": ["Irrigation layout plan", "Pipes, laterals, emitters or sprinklers", "Filter and pressure gauge", "Water source with adequate supply", "Maintenance tools and spare parts"],
        "steps": ["Measure the field and plan the layout against the crop rows.", "Lay the mainline from the source to the centre of the field.", "Fix laterals and emitters, keeping spacing matching plant spacing.", "Flush the lines and test pressure at every section.", "Schedule irrigation to the crop stage, not on fixed dates alone."],
        "tips": "Water in the early morning or evening to cut evaporation loss by nearly a third.",
        "benefits": ["Up to 60% water saving over flood irrigation", "Uniform moisture across the field", "Fewer weeds between the rows", "Lower labour cost for watering"],
        "precautions": ["Keep filters clean to avoid clogged emitters", "Use a pressure regulator on sloping fields", "Protect pipes from rodent and UV damage", "Do not irrigate during peak heat"],
        "common_mistakes": ["Wrong emitter or sprinkler spacing", "Ignoring pressure variation in the field", "Skipping filtration and regular flushing", "Overwatering young seedlings"],
    },
    "Fertilizer": {
        "materials": ["Fertilizer of the right grade", "Soil test report", "Measuring cup or weighing scale", "Sprayer or fertigation tank", "Protective gloves and mask"],
        "steps": ["Read the soil test report to decide the nutrient dose.", "Split the nitrogen dose into top dressing rounds.", "Apply the basal dose at sowing or transplanting time.", "Foliar-feed through the sprayer during critical growth stages.", "Irrigate lightly after fertilizer application to move nutrients down."],
        "tips": "Split nitrogen at tillering, flowering and grain-fill stages instead of dumping it all at once.",
        "benefits": ["Balanced nutrition without wastage", "Better flowering and fruiting", "Reduced input cost per acre", "Fewer deficiency symptoms mid-season"],
        "precautions": ["Do not apply fertilizer on wet leaves", "Keep fertilizer bags sealed and dry", "Wear gloves while handling granules", "Do not exceed the recommended dose"],
        "common_mistakes": ["Applying only urea and ignoring other nutrients", "Random doses without a soil test", "Mixing incompatible fertilizers together", "Applying fertilizer just before heavy rain"],
    },
    "Pest Control": {
        "materials": ["Pheromone or sticky traps", "Neem oil or bio-pesticides", "Knapsack sprayer", "Scouting notebook", "Safety kit (gloves, mask, goggles)"],
        "steps": ["Scout the crop twice a week and record the pest and its stage.", "Install traps early to catch the first generation.", "Use bio-pesticides and neem before reaching for chemicals.", "Spray only when the pest crosses the economic threshold.", "Clean the field of debris that shelters pests after each season."],
        "tips": "Cotton farmers get better control of bollworms by synchronising pheromone traps with spraying schedules.",
        "benefits": ["Lower pesticide cost per acre", "Better natural predator survival", "Reduced residue on the produce", "Sustainable control season after season"],
        "precautions": ["Never spray during bloom when bees are active", "Follow the waiting period before harvest", "Do not exceed the dose on the label", "Wash the sprayer thoroughly after use"],
        "common_mistakes": ["Spraying at the wrong time of day", "Overusing one chemical until pest resistance builds", "Scouting only the field edges", "Mixing chemicals without compatibility checks"],
    },
    "Organic": {
        "materials": ["Cow dung and cow urine", "Green leaves and biomass", "Jaggery and pulse flour (for preparations)", "Neem leaves and seeds", "Watering can and shade area"],
        "steps": ["Prepare site-specific organic inputs such as vermicompost or jeevamrut in advance.", "Apply them at the root zone during sowing and at critical growth stages.", "Foliar-spray liquid preparations diluted in the safe ratio.", "Mulch with residues to keep moisture and smother weeds.", "Rotate crops and compost residues to close the nutrient loop."],
        "tips": "Dilute liquid organic sprays to 10% strength; over-diluting wastes them while under-diluting can burn leaves.",
        "benefits": ["Improved soil biology and structure", "Safer, residue-free produce", "Lower dependence on purchased inputs", "Better long-term soil fertility"],
        "precautions": ["Do not apply fresh cow dung directly at the root", "Store liquid preparations away from sunlight", "Keep the dilution ratio correct", "Convert slowly; keep soil nutrition balanced"],
        "common_mistakes": ["Assuming organic products never need pest control", "Using one spray for every problem", "Ignoring crop rotation and fallowing", "Applying undiluted liquids on young plants"],
    },
    "Crops": {
        "materials": ["Certified seed or planting material", "Line marker or roller for spacing", "Seed drill or manual dibbler", "Fertilizer and irrigation arrangement", "Record notebook"],
        "steps": ["Follow the recommended planting geometry for the specific crop.", "Prepare the seedbed to the right tilth before planting.", "Plant at uniform depth and spacing for even competition.", "Gap-fill weak or missing hills within the first week.", "Irrigate and top-dress at the stage the crop needs most."],
        "tips": "For transplanted crops, raising healthy nurseries matters more than the transplanting day itself.",
        "benefits": ["Uniform plant stand and canopy", "Easier spraying and weeding", "Better yields from the same land", "Simpler harvest and grading"],
        "precautions": ["Do not plant deeper than the recommended depth", "Keep sufficient row width for machinery", "Do not crowd the crop for the sake of count", "Remove diseased plants early to protect neighbours"],
        "common_mistakes": ["Wrong spacing that blocks sunlight", "Skipping gap filling for weak hills", "Planting a crop outside its best season", "Ignoring seed treatment before planting"],
    },
    "Livestock": {
        "materials": ["Clean feed and water troughs", "Vaccines and de-wormers", "Disinfectant and lime", "Health record register", "Balanced feed and mineral blocks"],
        "steps": ["House animals in dry, ventilated, well-drained sheds.", "Feed a balanced ration at fixed times every day.", "Follow the de-worming and vaccination calendar without skipping.", "Clean sheds daily and disinfect the flooring weekly.", "Keep a health record of each animal for early detection."],
        "tips": "The first milk (colostrum) within hours of birth builds the calf's entire lifetime immunity.",
        "benefits": ["Better milk yield and weight gain", "Fewer disease breakouts in the herd", "Longer productive life of animals", "Cleaner working environment"],
        "precautions": ["Do not let animals drink stagnant water", "Keep feed stores rodent- and damp-free", "Isolate sick animals immediately", "Handle chemicals away from feed areas"],
        "common_mistakes": ["Irregular de-worming schedules", "Ignoring hoof and shelter hygiene", "Feeding one single feed type", "Missing vaccinations for young stock"],
    },
    "Smart Farming": {
        "materials": ["Sensor or automation devices", "Reliable internet or phone connectivity", "Farm management app or dashboard", "Drone or field-scouting kit", "Power backup (solar or battery)"],
        "steps": ["Start small: automate or digitise one field activity first.", "Install sensors in representative spots of the field.", "Connect the data to a dashboard you check regularly.", "Act on alerts such as soil moisture or pest thresholds quickly.", "Review the season data to plan the next crop better."],
        "tips": "Farmers get the fastest returns from soil-moisture sensors on drip-irrigated plots, not from cameras.",
        "benefits": ["Fewer field visits for routine checks", "Precise irrigation and spraying", "Recorded, repeatable decision-making", "Better input-use efficiency"],
        "precautions": ["Keep devices charged and firmware updated", "Protect electronics from moisture and rodents", "Do not rely on a single data point to decide", "Validate automated advice against the field"],
        "common_mistakes": ["Buying gadgets without a clear use case", "Ignoring data because collection is inconsistent", "Placing sensors at field edges only", "Expecting instant yield jumps from digitisation"],
    },
    "Harvesting": {
        "materials": ["Sharp sickles, knives or shears", "Harvesting bags and crates", "Clean tarpaulin or threshing floor", "Gloves and protective clothing", "Weighing and grading tools"],
        "steps": ["Confirm maturity by moisture or colour index, not the calendar.", "Harvest in the cooler part of the day to reduce field losses.", "Cut, collect and move produce to shade quickly.", "Thresh and clean without letting produce touch bare soil.", "Grade, weigh and record the output immediately."],
        "tips": "For grains, harvesting at the right moisture (18-20%) cuts losses by half compared to over-dry fields.",
        "benefits": ["Lower harvest and post-harvest losses", "Better grade and market price", "Faster field turnaround for the next crop", "Less labour stress with planned teams"],
        "precautions": ["Do not harvest in rain or heavy dew", "Keep produce off the ground while collecting", "Do not pile produce in deep mounds that heat up", "Service blades and machinery before and after use"],
        "common_mistakes": ["Harvesting too early or too late", "Bunching filled sacks in direct sun", "Using dull tools that bruise produce", "Mixing graded lots at the last minute"],
    },
    "Storage": {
        "materials": ["Clean gunny bags or hermetic storage bags", "Dried and cleaned produce", "Moisture meter", "Neem leaves or safe grain protectants", "Elevated racks or pallets"],
        "steps": ["Dry and clean the produce to the safe storage moisture.", "Cool it to near-ambient before bagging.", "Treat the store with a safe fumigant or neem guards.", "Stack bags on pallets off the floor and away from walls.", "Inspect stock every week and quarantine any infested lot."],
        "tips": "Storing paddy after sun-drying to 12% moisture prevents the biggest storage losses: weevils and mould.",
        "benefits": ["Protection from insects and mould", "Higher market value for graded stock", "Year-round sale flexibility instead of distress sales", "Cleaner, sale-ready produce"],
        "precautions": ["Do not stack bags against damp walls", "Keep the store dark, ventilated and insect-proof", "Do not mix new stock with old stock", "Monitor moisture before and during storage"],
        "common_mistakes": ["Storing warm, undried produce", "Stacking bags on the bare floor", "Ignoring early signs of infestation", "Opening fumigated stores too soon"],
    },
}

# Entry tuple:
# (title, description, crop, season, difficulty, duration, cost_level,
#  water_requirement, is_organic, suitable_soil)
ENTRIES = [
    # ============ CATEGORY: Soil ============
    ("Compost Application Method", "Incorporate well-decomposed compost into the topsoil to rebuild organic matter and feed soil life.", "All Crops", "Pre-Sowing", "beginner", "2-3 days", "Low", "Medium", True, "All soil types"),
    ("Soil Testing & Nutrient Balance", "Test soil pH and nutrient levels to plan exact fertilizer doses instead of guessing.", "All Crops", "Pre-Sowing", "beginner", "2-3 days", "Low", "Low", True, "All soil types"),
    ("Green Manuring with Dhaincha", "Grow dhaincha and plough it under to add nitrogen and organic matter naturally.", "Paddy, Vegetables", "Kharif", "beginner", "45-50 days", "Low", "Medium", True, "Sandy loam to clay loam"),
    ("Lime Application for Acidic Soil", "Spread agricultural lime in acidic fields to raise pH and unlock phosphorus.", "All Crops", "Pre-Sowing", "intermediate", "1 day", "Medium", "Low", True, "Acidic soils"),
    ("Gypsum for Alkaline Soil", "Apply gypsum to sodic soils to displace sodium and improve water infiltration.", "All Crops", "Pre-Sowing", "intermediate", "1-2 days", "Medium", "Medium", True, "Alkaline / sodic soils"),
    ("Deep Ploughing Method", "Deep-plough once in two to three years to break hard pans and aerate the subsoil.", "All Crops", "Pre-Sowing", "intermediate", "2-3 days", "Medium", "Low", True, "Hard / compacted soils"),
    ("Raised Bed Preparation", "Shape permanent raised beds to improve drainage, aeration and weeding efficiency.", "Vegetables, Wheat", "Pre-Sowing", "intermediate", "2-3 days", "Medium", "Medium", True, "Heavy & waterlogged soils"),
    ("Zero Tillage Soil Prep", "Sow directly into unploughed soil; only the previous crop residue covers the surface.", "Wheat, Maize", "Rabi", "intermediate", "1 day", "Low", "Low", True, "Well-drained loams"),
    ("Mulching Techniques", "Cover the soil surface with organic mulch to trap moisture and smother weeds.", "Vegetables, Fruits", "All Seasons", "beginner", "1 day", "Low", "Medium", True, "All soil types"),
    ("Cover Cropping for Soil Health", "Sow a quick cover crop between main seasons to protect and feed the soil.", "All Crops", "Between Seasons", "beginner", "30-50 days", "Low", "Medium", True, "All soil types"),
    ("Vermicompost Soil Amendment", "Spread vermicompost before transplanting to give the soil an instant microbial boost.", "All Crops", "Pre-Sowing", "beginner", "1-2 days", "Medium", "Medium", True, "All soil types"),
    ("Shallow Cultivation Technique", "Keep the first working after harvest shallow to avoid lifting weed seeds to the surface.", "All Crops", "Pre-Sowing", "beginner", "1 day", "Low", "Low", True, "All soil types"),
    ("Land Leveling & Grading", "Level the field to park irrigation water evenly and reduce runoff and erosion.", "All Crops", "Pre-Sowing", "advanced", "3-7 days", "High", "Medium", True, "All soil types"),
    ("Subsoil Compaction Relief", "Loosen compacted layers with a chisel plough without inverting the topsoil.", "All Crops", "Pre-Sowing", "advanced", "1-2 days", "Medium", "Low", True, "Compacted subsoils"),
    ("Soil Solarization", "Trap heat under clear plastic sheets in summer to sterilize soil-borne pests and weeds.", "Vegetables", "Summer", "intermediate", "20-30 days", "Medium", "High", True, "Nursery & garden beds"),
    ("Sandy Soil Improvement", "Add compost and clay to sandy soils so moisture and nutrients stop leaking away.", "Vegetables", "Pre-Sowing", "intermediate", "2-3 days", "Medium", "High", True, "Sandy soils"),
    ("Clay Soil Improvement", "Break heavy clay with organic matter and sand to improve drainage and aeration.", "All Crops", "Pre-Sowing", "intermediate", "2-4 days", "Medium", "Low", True, "Clay soils"),
    ("Biochar Soil Amendment", "Mix aged biochar into the root zone to hold water and nutrients for many seasons.", "Vegetables, Fruits", "Pre-Sowing", "intermediate", "2-3 days", "Medium", "Medium", True, "Sandy & degraded soils"),
    ("Red Soil Nutrient Boosting", "Rebuild thin red soils with compost, green manure and balanced micronutrients.", "Groundnut, Chilli", "Kharif", "intermediate", "2-3 days", "Medium", "Medium", True, "Red loamy soils"),
    ("Mycorrhizal Soil Inoculation", "Inoculate the root zone with mycorrhizal fungi to expand the plant's nutrient uptake.", "All Crops", "Pre-Sowing", "intermediate", "1 day", "Medium", "Low", True, "All soil types"),
    # ============ CATEGORY: Seeds ============
    ("Seed Treatment with Trichoderma", "Treat seed with Trichoderma viride to shield seedlings from soil-borne diseases.", "All Crops", "Pre-Sowing", "beginner", "Half day", "Low", "Low", True, "All soil types"),
    ("Hot Water Seed Treatment", "Dip seed in hot water bath to kill seed-borne fungi without a chemical seed dresser.", "Wheat, Cabbage", "Pre-Sowing", "intermediate", "Half a day", "Low", "Low", True, "All soil types"),
    ("Seed Priming for Germination", "Soak seed in water briefly, then dry back, for faster and even germination.", "All Crops", "Pre-Sowing", "beginner", "Few hours", "Low", "Low", True, "All soil types"),
    ("Seed Dormancy Breaking", "Break hard-seed dormancy with scarification or chilling so sowing germinates reliably.", "Groundnut, Lucerne", "Pre-Sowing", "advanced", "Few hours", "Low", "Low", True, "All soil types"),
    ("Seed Germination Testing", "Check a sample lot on a wet cloth for germination before spending the whole sowing.", "All Crops", "Pre-Sowing", "beginner", "7-10 days", "Low", "Low", True, "All soil types"),
    ("Certified Seed Sourcing", "Buy certified, tagged seed from registered dealers to guarantee purity and health.", "All Crops", "Procurement", "beginner", "1 day", "Medium", "Low", True, "All soil types"),
    ("Acid Delinting of Cotton Seed", "Treat fuzzy cotton seed with sulphuric acid to remove lint and speed up germination.", "Cotton", "Pre-Sowing", "advanced", "Half day", "Low", "Low", True, "All soil types"),
    ("Neem-Coated Seed Storage", "Store seed with dry neem leaves to keep weevils away without harsh chemicals.", "All Crops", "Storage", "beginner", "During storage", "Low", "Low", True, "All soil types"),
    ("Rhizobium Seed Inoculation", "Coat legume seed with Rhizobium culture so nodules form and the crop fixes its own nitrogen.", "Soybean, Groundnut", "Pre-Sowing", "intermediate", "Half day", "Low", "Low", True, "All soil types"),
    ("Azotobacter Seed Inoculation", "Inoculate non-legume seed with Azotobacter to bring atmospheric nitrogen to cereals.", "Wheat, Maize", "Pre-Sowing", "intermediate", "Half day", "Low", "Low", True, "All soil types"),
    ("Planter Seed Calibration", "Calibrate the seed drill to drop the exact seed rate at the right depth.", "Wheat, Maize, Soybean", "Pre-Sowing", "advanced", "Few hours", "Low", "Low", True, "All soil types"),
    ("Nursery Seedbed Preparation", "Raise uniform seedlings in a treated nursery bed before transplanting to the field.", "Paddy, Vegetables", "Pre-Sowing", "beginner", "20-30 days", "Low", "High", True, "All soil types"),
    ("Boron Seed Treatment for Groundnut", "Treat groundnut seed with boron before sowing to prevent immature and hollow kernels.", "Groundnut", "Pre-Sowing", "intermediate", "Half day", "Low", "Low", True, "All soil types"),
    ("Gibberellic Acid Seed Soaking", "Soak certain seeds in dilute gibberellic acid to break dormancy and speed sprouting.", "Grapes, Potatoes", "Pre-Sowing", "advanced", "Several hours", "Low", "Low", True, "All soil types"),
    ("Salt Water Seed Separation", "Float off chaffy, insect-damaged seed in salt water to keep only the heavy, healthy seed.", "Paddy", "Pre-Sowing", "beginner", "Few hours", "Low", "Low", True, "All soil types"),
    ("Onion Seed Vernalization", "Expose onion seeds to the right chill period for improved bolting and bulb uniformity.", "Onion", "Pre-Sowing", "advanced", "10-15 days", "Low", "Low", True, "All soil types"),
    ("Sprouted Seed Nursery for Paddy", "Sprout paddy seed in gunny bags and sow as sowpalli for even, quick field establishment.", "Paddy", "Kharif", "beginner", "2-3 days", "Low", "High", True, "All soil types"),
    ("Pelleted Seed Sowing", "Wrap tiny, irregular seeds in a clay pellet for precise machine sowing and easier handling.", "Fodder, Vegetables", "Pre-Sowing", "advanced", "1-2 days", "Medium", "Low", True, "All soil types"),
    # ============ CATEGORY: Irrigation ============
    ("Drip Irrigation Setup", "Install a water-efficient drip system that delivers water directly to the root zone.", "Vegetables, Fruits", "All Seasons", "intermediate", "2-3 days", "Medium", "Low", True, "All soil types; ideal for sandy soils"),
    ("Sprinkler Irrigation System", "Distribute water uniformly like gentle rain across the field to save labour and water.", "Vegetables, Pulses", "All Seasons", "intermediate", "2-4 days", "Medium", "Medium", True, "Sandy & light soils"),
    ("Fertigation through Drip", "Inject dissolved fertilizers into the drip network for precise, root-zone feeding.", "All Crop Types", "Growing Season", "advanced", "1-2 days", "Medium", "Low", True, "All soil types"),
    ("Rain Gun Irrigation", "Use a high-pressure rain gun for quick, wide-area watering of large plots.", "Sugarcane, Vegetables", "Summer", "intermediate", "Half day", "Medium", "Medium", True, "All soil types"),
    ("Flood Basin Irrigation", "Prepare flat basins and flood them gently for crops that tolerate standing water.", "Paddy, Wheat", "Kharif", "beginner", "Half day", "Low", "High", True, "Clay & clay loam soils"),
    ("Furrow Irrigation Method", "Run water down narrow furrows between crop rows for efficient, controlled watering.", "Maize, Cotton", "Growing Season", "beginner", "Half day", "Low", "Medium", True, "Sloping & medium soils"),
    ("Check Basin Method", "Split the field into level check basins to hold water uniformly and reduce wastage.", "Paddy, Orchards", "All Seasons", "intermediate", "1 day", "Low", "High", True, "Level medium soils"),
    ("Mulch-Drip Combination", "Combine drip lines with plastic or organic mulch to save up to an extra 25% water.", "Vegetables", "All Seasons", "intermediate", "2-3 days", "Medium", "Low", True, "All soil types"),
    ("Paddy Flood-Drain Cycle", "Flood and drain paddy beds on a schedule to save water and aerate the roots.", "Paddy", "Kharif", "intermediate", "Whole season", "Low", "High", True, "Clay soils"),
    ("Alternate Wetting and Drying", "Let paddy soil dry cyclically before rewetting to cut water use without losing yield.", "Paddy", "Kharif", "advanced", "Whole season", "Low", "High", True, "Clay & clay loam soils"),
    ("Rainwater Harvesting Farm Pond", "Dig and line a farm pond to trap runoff during the monsoon for dry-season irrigation.", "All Crops", "Monsoon", "advanced", "2-3 weeks", "High", "High", True, "All soil types"),
    ("Solar Pump Irrigation", "Power tube-well and lift irrigation with solar panels to slash running costs.", "All Crops", "Year-Round", "advanced", "1-2 weeks", "High", "Medium", True, "All soil types"),
    ("Micro Sprinkler for Nurseries", "Fit micro-sprinklers in nurseries for uniform misting of tender seedlings.", "Nurseries", "All Seasons", "intermediate", "1-2 days", "Medium", "Low", True, "All soil types"),
    ("Subsurface Drip Irrigation", "Bury drip lines below the soil to water roots with no surface evaporation.", "Fruits, Sugarcane", "Year-Round", "advanced", "3-5 days", "High", "Low", True, "All soil types"),
    ("Drip Line Flushing & Care", "Flush drip lines quarterly and clean filters to keep emitters flowing at full rate.", "All Crops", "Year-Round", "beginner", "Few hours", "Low", "Low", True, "All soil types"),
    ("Emitter Spacing Selection", "Match emitter discharge and spacing to soil texture and plant spacing for uniform wetting.", "All Crops", "Before Installation", "advanced", "Few hours", "Low", "Low", True, "All soil types"),
    ("Canal Water Management", "Schedule canal turns and line field channels to move every drop to the crop.", "All Crops", "Monsoon", "intermediate", "Whole season", "Medium", "High", True, "All soil types"),
    ("Conjunctive Well-Canal Use", "Alternate canal and borewell water to manage salinity and stretch scarce supplies.", "All Crops", "Year-Round", "advanced", "Whole season", "Medium", "Medium", True, "All soil types"),
    ("Saline Water Irrigation Management", "Irrigate with saline water only in measured doses and flush salts below the root zone.", "All Crops", "Year-Round", "advanced", "Whole season", "Medium", "Medium", True, "Sodic & saline soils"),
    ("Deficit Irrigation Scheduling", "Reduce water at non-critical stages while protecting flowering and grain-fill stages.", "Wheat, Maize", "Growing Season", "advanced", "Whole season", "Low", "Low", True, "All soil types"),
    ("Pivot Irrigation for Large Fields", "Use a centre-pivot boom to irrigate large, flat fields with minimal labour.", "Maize, Soybean", "Growing Season", "advanced", "1-2 weeks", "High", "Medium", True, "Large level fields"),
    ("Irrigated Fodder Production", "Grow high-yield fodder under irrigation so livestock feed is assured in every season.", "Fodder Crops", "Year-Round", "intermediate", "30-45 days", "Medium", "High", True, "All soil types"),
    # ============ CATEGORY: Fertilizer ============
    ("Soil Test Based Fertilization", "Plan the full fertilizer schedule from a soil test so every rupee is spent on what is short.", "All Crops", "Pre-Sowing", "intermediate", "Whole season", "Medium", "Low", True, "All soil types"),
    ("Basal Dose Fertilizer Application", "Work the basal dose into the soil at sowing to feed the crop through its early growth.", "All Crops", "Sowing", "beginner", "Half day", "Low", "Medium", True, "All soil types"),
    ("Urea Top Dressing", "Apply urea in moist soil at the right growth stages to avoid nitrogen loss as gas.", "Paddy, Wheat, Maize", "Growing Season", "beginner", "Hour per acre", "Low", "Low", True, "All soil types"),
    ("Split Application of Nitrogen", "Divide the nitrogen dose into three to four splits for continuity of supply and less loss.", "All Crops", "Growing Season", "intermediate", "Whole season", "Low", "Medium", True, "All soil types"),
    ("Compost Tea Foliar Spray", "Brew finished compost in water and spray it on leaves for a mild, natural nutrient boost.", "Vegetables", "Growing Season", "beginner", "1-2 days per brew", "Low", "Low", True, "All soil types"),
    ("NPK 19:19:19 Foliar Feeding", "Spray a balanced water-soluble NPK on stressed or flowering crops for a quick fix.", "Vegetables, Fruits", "Growing Season", "intermediate", "Hour per acre", "Medium", "Low", True, "All soil types"),
    ("Zinc Sulphate Application", "Apply zinc sulphate to correct zinc deficiency visible as whitish bands on leaves.", "Paddy, Maize, Cotton", "Growing Season", "intermediate", "Half day", "Medium", "Low", True, "Zinc-deficient soils"),
    ("Micronutrient Mix Spray", "Spray a prepared micronutrient mix at early growth to head off hidden deficiencies.", "All Crops", "Early Growth", "intermediate", "Hour per acre", "Medium", "Low", True, "All soil types"),
    ("Neem-Coated Urea Application", "Use neem-coated urea so nitrogen releases slowly and resisted pests stay suppressed.", "All Crops", "Growing Season", "intermediate", "Whole season", "Low", "Medium", True, "All soil types"),
    ("DAP Placement Method", "Place DAP in the root zone at sowing so phosphorus is available right next to roots.", "All Crops", "Sowing", "intermediate", "Half day", "Medium", "Low", True, "All soil types"),
    ("Seed-Cum-Fertilizer Drill Sowing", "Drill seed and starter fertilizer together in lines for even placement and early vigour.", "Wheat, Pulses", "Sowing", "advanced", "Half day", "Medium", "Low", True, "All soil types"),
    ("Vermiwash Foliar Spray", "Spray diluted vermiwash on leaves at 15-day intervals for a gentle organic feed.", "All Crops", "Growing Season", "beginner", "Hour per acre", "Low", "Low", True, "All soil types"),
    ("Band Placement of Fertilizer", "Place concentrated fertilizer in a band beside the seed row to boost early uptake.", "Maize, Cotton, Potato", "Sowing", "intermediate", "Half day", "Low", "Low", True, "All soil types"),
    ("Slow-Release Fertilizer Use", "Switch to slow-release and coated fertilizers to feed crops steadily and cut losses.", "All Crops", "Sowing", "intermediate", "Whole season", "High", "Low", True, "All soil types"),
    ("Fertigation Fertilizer Schedule", "Run a weekly fertigation program matched to crop growth for precise nutrition.", "Drip-irrigated Crops", "Growing Season", "advanced", "Whole season", "Medium", "Low", True, "All soil types"),
    ("Liquid Biofertilizer Application", "Apply liquid biofertilizers at sowing and flowering to keep the root zone biologically active.", "All Crops", "Sowing & Flowering", "intermediate", "Half day", "Low", "Low", True, "All soil types"),
    ("Starter Solution for Transplants", "Dip seedlings in a weak nutrient starter solution before transplanting to cut shock.", "Vegetables", "Transplanting", "intermediate", "Few hours", "Low", "Medium", True, "All soil types"),
    ("Phosphorus Fixation Management", "Bypass high phosphorus-fixing soils with banding and fertilizing alongside organic matter.", "All Crops", "Sowing", "advanced", "Whole season", "Medium", "Medium", True, "Acid & red soils"),
    ("Potash Application Timing", "Apply potash before flowering and fruit set, when the crop's potassium demand peaks.", "Fruits, Potato, Banana", "Growing Season", "intermediate", "Half day", "Medium", "Low", True, "All soil types"),
    ("Foliar Boron for Flowering Crops", "Spray boron at flowering to improve fruit set and prevent flower and fruit drop.", "Groundnut, Mango, Apple", "Flowering", "intermediate", "Hour per acre", "Low", "Low", True, "Boron-poor soils"),
    # ============ CATEGORY: Pest Control ============
    ("Integrated Pest Management", "Combine monitoring, cultural, biological and chemical tools so pests never build up.", "All Crops", "Whole Season", "intermediate", "Whole season", "Medium", "Medium", True, "All soil types"),
    ("Neem Oil Spray Preparation", "Prepare a 1-2% neem oil spray to knock down sucking pests and soft-bodied larvae.", "All Crops", "Growing Season", "beginner", "Hour per acre", "Low", "Low", True, "All soil types"),
    ("Pheromone Trap Installation", "Install species-specific pheromone traps at the crop edge to detect pests early.", "Cotton, Maize, Brinjal", "Early Season", "beginner", "Few hours", "Low", "Low", True, "All soil types"),
    ("Yellow Sticky Trap Monitoring", "Hang yellow sticky traps above the canopy to catch and count flying pests.", "Vegetables, Fruits", "Growing Season", "beginner", "Few hours", "Low", "Low", True, "All soil types"),
    ("Trichogramma Card Release", "Staple Trichogramma parasitoid cards at weekly intervals to destroy pest eggs.", "Maize, Sugarcane, Cotton", "Egg-laying Season", "intermediate", "Weekly", "Medium", "Low", True, "All soil types"),
    ("NPV Biopesticide Spray", "Spray Nuclear Polyhedrosis Virus at dusk when caterpillar larvae are feeding.", "Vegetables, Legumes", "Growing Season", "intermediate", "Hour per acre", "Low", "Low", True, "All soil types"),
    ("Bacillus thuringiensis Spray", "Apply Bacillus thuringiensis spray to target leaf-eating caterpillars safely.", "All Crops", "Growing Season", "intermediate", "Hour per acre", "Medium", "Low", True, "All soil types"),
    ("Light Trap Pest Catching", "Operate a light trap in the crop to pull and destroy night-flying adult moths.", "All Crops", "Pest Season", "beginner", "Nightly", "Low", "Low", True, "All soil types"),
    ("Border Crop Pest Barrier", "Sow a border crop around the main field to confine or bait pests before entry.", "Cotton, Pulses", "Sowing", "beginner", "At sowing", "Low", "Medium", True, "All soil types"),
    ("Marigold Trap Cropping", "Plant marigold rows in vegetable fields to attract pests away from the main crop.", "Tomato, Chilli", "Sowing", "beginner", "At sowing", "Low", "Medium", True, "All soil types"),
    ("Clean Cultivation for Pests", "Destroy crop debris and volunteer plants that shelter pests between seasons.", "All Crops", "Post-Harvest", "beginner", "Half day", "Low", "Low", True, "All soil types"),
    ("Fermented Biomass Trap", "Brew a jaggery-yeast solution in pots to attract and drown fruit-feeding moths.", "Fruit & vegetable crops", "Fruiting Season", "intermediate", "Weekly", "Low", "Low", True, "All soil types"),
    ("Tobacco Decoction Spray", "Boil tobacco leaves into a decoction and spray dilute to control soft-bodied pests.", "Vegetables", "Growing Season", "intermediate", "Hour per acre", "Low", "Medium", True, "All soil types"),
    ("Spray Nozzle & Timing Selection", "Match spray nozzle, droplet size and timing to get complete coverage with less pesticide.", "All Crops", "Growing Season", "intermediate", "At each spray", "Low", "Low", True, "All soil types"),
    ("Sucking Pest Control Strategy", "Time systemic insecticide sprays early, when sucking pest counts first cross thresholds.", "Cotton, Chillies", "Growing Season", "intermediate", "Hour per acre", "Medium", "Low", True, "All soil types"),
    ("Whitefly Control Program", "Trap, remove alternate hosts and rotate chemistry to stop whitefly build-up early.", "Cotton, Tomato", "Growing Season", "advanced", "Whole season", "Medium", "Medium", True, "All soil types"),
    ("Aphid Management Technique", "Wash off early aphid colonies and spray only when populations keep increasing.", "Mustard, Pulses", "Growing Season", "beginner", "Hour per acre", "Low", "Low", True, "All soil types"),
    ("Fall Armyworm Management", "Scout for egg masses, hand-pick larvae and time sprays before the cob stage.", "Maize", "Vegetative Stage", "advanced", "Whole season", "Medium", "Medium", True, "All soil types"),
    ("Pink Bollworm PB Rope", "Install PB Rope dispensers to confuse pink bollworm males so mating drops.", "Cotton", "Fruiting Stage", "advanced", "Season-long", "High", "Low", True, "All soil types"),
    ("Rodent Bait Station Placement", "Lay bait stations along bunds and stores to drive down field and storage rodents.", "All Crops, Stores", "Whole Season", "intermediate", "Monthly", "Low", "Low", True, "All soil types"),
    ("Weed-Host Removal for Pests", "Clear alternate weed hosts that carry viruses and pests into the main crop.", "All Crops", "Throughout Season", "beginner", "Weekly round", "Low", "Medium", True, "All soil types"),
    ("Natural Predator Conservation", "Protect ladybirds and wasps by avoiding broad-spectrum sprays during peak activity.", "All Crops", "Growing Season", "beginner", "Whole season", "Low", "Low", True, "All soil types"),
    ("Pesticide Drift Reduction", "Spray on calm mornings with drift-reducing nozzles so neighbouring crops stay safe.", "All Crops", "Spray Season", "intermediate", "At each spray", "Low", "Low", True, "All soil types"),
    ("Spot Systemic Insecticide Application", "Inject or drench systemic insecticide only into infested plants to protect their neighbours.", "Orchards, Vegetables", "Infestation", "advanced", "Hour per acre", "Medium", "Low", True, "All soil types"),
    # ============ CATEGORY: Organic ============
    ("Vermicompost Production", "Let earthworms convert farm waste into rich, slow-release compost for the soil.", "All Crops", "Year-Round", "beginner", "45-60 days", "Low", "Low", True, "All soil types"),
    ("NADEP Compost Method", "Layer crop waste and cattle dung in a pit to make large volumes of quality compost.", "All Crops", "Post-Harvest", "intermediate", "90 days", "Low", "Low", True, "All soil types"),
    ("Panchagavya Preparation", "Ferment cow dung, urine, milk and ghee into a potent foliar growth booster.", "All Crops", "Growing Season", "intermediate", "30-day ferment", "Low", "Low", True, "All soil types"),
    ("Jeevamrut Preparation", "Brew cow dung, urine and pulse flour into a living liquid fertilizer and soil tonic.", "All Crops", "Growing Season", "beginner", "Brew before sunrise", "Low", "Low", True, "All soil types"),
    ("Beejamrut Seed Treatment", "Coat seeds with fermented beejamrut before sowing for a natural disease shield.", "All Crops", "Pre-Sowing", "beginner", "Few hours", "Low", "Low", True, "All soil types"),
    ("Green Manure with Sunhemp", "Grow sunhemp and plough it in to add nitrogen and bulk organic matter cheaply.", "Paddy, Vegetables", "Pre-Sowing", "beginner", "40-45 days", "Low", "Medium", True, "All soil types"),
    ("Cow Urine Foliar Spray", "Dilute aged cow urine and spray to deter pests and strengthen plant immunity.", "All Crops", "Growing Season", "beginner", "Hour per acre", "Low", "Low", True, "All soil types"),
    ("Trichoderma-Enriched Compost", "Fork Trichoderma culture into compost heaps to build protective, disease-suppressing biology.", "All Crops", "Composting", "intermediate", "During composting", "Low", "Low", True, "All soil types"),
    ("Pseudomonas Biofertilizer", "Apply Pseudomonas fluorescens to suppress root rot and promote healthy rooting.", "All Crops", "Sowing & Drench", "intermediate", "Half day", "Low", "Low", True, "All soil types"),
    ("Organic Residue Mulching", "Mulch crops thickly with straw, leaves or groundnut shells to feed the soil as it rots.", "All Crops", "Growing Season", "beginner", "Half day", "Low", "Low", True, "All soil types"),
    ("Azolla Cultivation for Paddy", "Grow azolla on paddy water and turn it in for a natural nitrogen and mulch source.", "Paddy", "Kharif", "intermediate", "Seasonal", "Low", "High", True, "Paddy fields"),
    ("Compost Tea Brewing", "Brew aerated compost tea and drench beds for a quick injection of soil biology.", "Vegetables, Fruits", "Growing Season", "intermediate", "24-48 hours brew", "Low", "Low", True, "All soil types"),
    ("Fermented Plant Juice", "Ferment fast-growing weeds with jaggery into a potassium- and enzyme-rich tonic.", "All Crops", "Growing Season", "intermediate", "7-day ferment", "Low", "Low", True, "All soil types"),
    ("Effective Microorganisms Application", "Apply effective microorganisms with compost and soil to out-compete harmful microbes.", "All Crops", "Whole Season", "intermediate", "Monthly", "Medium", "Low", True, "All soil types"),
    ("Eggshell Calcium Fertilizer", "Grind dried eggshells into powder and work in to supply slow calcium to the soil.", "Vegetables, Fruits", "Growing Season", "beginner", "Half day", "Low", "Low", True, "All soil types"),
    ("Banana Peel Potassium Tea", "Soak banana peels in water and use the tea as a gentle potassium feed for crops.", "Flowers, Vegetables", "Growing Season", "beginner", "2-3 days soak", "Low", "Low", True, "All soil types"),
    ("Onion Peel Antioxidant Spray", "Brew onion peels into a mild spray that strengthens plants against fungal attacks.", "Vegetables", "Growing Season", "beginner", "1-2 days brew", "Low", "Low", True, "All soil types"),
    ("Dashaparni Herbal Pesticide", "Ferment ten forest leaves together into an all-round herbal pest repellent.", "All Crops", "Growing Season", "intermediate", "3-4 day ferment", "Low", "Low", True, "All soil types"),
    ("Agniastra Bio-Pesticide", "Blend tobacco, neem, garlic and chilli into a strong but botanical pest-kill spray.", "All Crops", "Pest Attack", "advanced", "1-2 days brew", "Low", "Low", True, "All soil types"),
    ("Brahmastra Bio-Pesticide", "Combine custard apple, neem and papaya leaves into a broad-spectrum herbal spray.", "All Crops", "Pest Attack", "advanced", "1-2 days brew", "Low", "Low", True, "All soil types"),
    ("Neem Seed Kernel Extract", "Soak crushed neem kernels overnight and spray the strained water as a safe insecticide.", "All Crops", "Growing Season", "intermediate", "Overnight soak", "Low", "Low", True, "All soil types"),
    ("Vermiwash Root Drench", "Drench selected plants with diluted vermiwash at transplanting and flowering stages.", "All Crops", "Transplant & Flowering", "beginner", "Hour per acre", "Low", "Low", True, "All soil types"),
    ("Jaggery Fermentation Attractant", "Set out fermented jaggery solutions to lure pests into traps away from the crop.", "Fruit Crops", "Fruiting Season", "beginner", "Weekly", "Low", "Low", True, "All soil types"),
    ("Bee Conservation for Orchards", "Grow bee forage around orchards and avoid sprays in bloom to lift pollination.", "Fruits", "Flowering", "beginner", "Whole season", "Low", "Low", True, "Orchard areas"),
    # ============ CATEGORY: Crops ============
    ("System of Rice Intensification", "Transplant single young paddy seedlings widely spaced to build a stronger root system.", "Paddy", "Kharif", "advanced", "Whole season", "Low", "Low", True, "Clay loam soils"),
    ("Transplanting Paddy Seedlings", "Transplant healthy 25-day paddy seedlings at even spacing for an even stand.", "Paddy", "Kharif", "beginner", "2-3 days", "Low", "High", True, "Clay & loam soils"),
    ("Side-Dressing Nitrogen in Rice", "Sidedress nitrogen into paddy rows at tillering and panicle initiation for greedy uptake.", "Paddy", "Kharif", "intermediate", "Whole season", "Low", "Medium", True, "Clay soils"),
    ("Wet Ploughing for Paddy", "Plough paddy fields under standing water to soften soil and suppress weeds.", "Paddy", "Kharif", "beginner", "1-2 days", "Low", "High", True, "Clay soils"),
    ("Wheat Line Sowing", "Sow wheat in straight lines with a seed drill for uniform crops and easier spraying.", "Wheat", "Rabi", "beginner", "1-2 days", "Low", "Medium", True, "Loam & alluvial soils"),
    ("Wheat Zero-Tillage Drill Sowing", "Plant wheat directly into standing rice stubble to save time, water and diesel.", "Wheat", "Rabi", "advanced", "1-2 days", "Low", "Low", True, "Well-drained loams"),
    ("Maize Plant Spacing Management", "Set maize rows and hills at the recommended spacing for cobs that fill completely.", "Maize", "Kharif", "beginner", "At sowing", "Low", "Medium", True, "Loam soils"),
    ("Groundnut Kernel Mulching", "Cover freshly sown groundnut rows with loose kernels' husk to hold moisture and stop weeds.", "Groundnut", "Kharif", "intermediate", "1 day", "Low", "Medium", True, "Red & sandy loams"),
    ("Chilli Staking & Trellising", "Stake or trellis chilli plants to keep fruit off the ground and reduce rot.", "Chilli", "Rabi", "intermediate", "1-2 days", "Medium", "Medium", True, "All soil types"),
    ("Tomato Pruning Technique", "Prune tomato suckers and lower leaves to open the canopy for bigger, cleaner fruit.", "Tomato", "Rabi", "intermediate", "Weekly", "Low", "Medium", True, "All soil types"),
    ("Onion Bulb Size Management", "Match onion spacing and top-dressing to plant population for max bulb size.", "Onion", "Rabi", "intermediate", "Whole season", "Medium", "Medium", True, "Sandy loam soils"),
    ("Cotton High-Density Planting", "Raise cotton plant density with close rows and controlled growth for earlier harvest.", "Cotton", "Kharif", "advanced", "Whole season", "Medium", "Medium", True, "Black & deep loam soils"),
    ("Sugarcane Setts Treatment", "Dip sugarcane setts in a hot-water-cum-fungicide bath for clean bud sprouting.", "Sugarcane", "Spring", "intermediate", "Half day", "Low", "Medium", True, "Black & loam soils"),
    ("Sugarcane Earthing-Up", "Earth up soil around sugarcane a few months in for strong tillers and lodging-resistance.", "Sugarcane", "Growing Season", "intermediate", "1-2 days", "Low", "High", True, "All soil types"),
    ("Soybean Seed-Cum-Fertilizer Sowing", "Drill soybean with starter fertilizer in lines for early vigour and clean harvest.", "Soybean", "Kharif", "advanced", "1-2 days", "Medium", "Medium", True, "Black soils"),
    ("Mustard Line Sowing", "Sow mustard in straight, wide rows for air movement and fewer aphid outbreaks.", "Mustard", "Rabi", "beginner", "1 day", "Low", "Medium", True, "Loam soils"),
    ("Potato Tuber Planting", "Plant well-sprouted, chalk-cut potato tubers at the right depth for even emergence.", "Potato", "Rabi", "intermediate", "1-2 days", "Medium", "High", True, "Sandy loam soils"),
    ("Chickpea Rhizobium Management", "Inoculate chickpea seed and soil with Rhizobium to fix nitrogen without extra urea.", "Chickpea", "Rabi", "intermediate", "At sowing", "Low", "Low", True, "Black & loam soils"),
    ("Sunflower Hybrid Sowing", "Sow sunflower hybrids at even geometry so every head fills against the pollination window.", "Sunflower", "Rabi", "beginner", "1 day", "Low", "Medium", True, "All soil types"),
    ("Banana Sucker Selection & Planting", "Pick healthy sword suckers and plant them deep with manure in the pit for a strong mat.", "Banana", "All Seasons", "intermediate", "2-3 days", "Medium", "High", True, "Rich loam soils"),
    ("Mango Grafting Technique", "Graft improved scion varieties onto vigorous rootstocks for uniform mango orchards.", "Mango", "Monsoon", "advanced", "Half day", "Low", "Low", True, "All soil types"),
    ("Grape Canopy Management", "Prune and train grape canes to sunlight and air for clean, well-coloured bunches.", "Grapes", "Winter", "advanced", "Seasonal pruning", "Medium", "Medium", True, "Deep loam soils"),
    ("Coconut Basin Irrigation", "Water coconut palms through circular basins to recharge the deep root zone.", "Coconut", "Summer", "beginner", "Weekly", "Low", "High", True, "Coastal & red soils"),
    ("Cashew Grafting", "Whip-graft high-yield scions onto cashew rootstocks for early, uniform production.", "Cashew", "Monsoon", "advanced", "Half day", "Low", "Low", True, "Laterite & red soils"),
    ("Pepper Trail Training", "Train pepper vines up live standards for easier harvest and better berry set.", "Black Pepper", "Monsoon", "intermediate", "1-2 days", "Low", "Medium", True, "Shaded, well-drained soils"),
    ("Rose Nursery Budding", "Bud improved rose varieties onto hardy stocks to produce uniform planting material.", "Roses", "Winter", "advanced", "Few hours", "Low", "Low", True, "Nursery beds"),
    ("Turmeric Rhizome Planting", "Plant disease-free turmeric rhizomes in ridges with a heavy seed rate for clean fingers.", "Turmeric", "Summer", "intermediate", "2-3 days", "Medium", "Medium", True, "Loam & alluvial soils"),
    ("Ginger Bed Cultivation", "Grow ginger on raised beds with good drainage and heavy mulching for plump rhizomes.", "Ginger", "Summer", "intermediate", "2-3 days", "Medium", "High", True, "Loam & sandy loam soils"),
    ("Sweet Corn Intercropping", "Intercrop short-duration sweet corn with pulses to earn extra income per acre.", "Maize (Sweet Corn)", "Kharif", "intermediate", "Whole season", "Low", "Medium", True, "All soil types"),
    ("Bajra Planting Geometry", "Sow pearl millet at the right spacing so tillers spread and ears fill before the heat.", "Pearl Millet", "Kharif", "beginner", "1 day", "Low", "Low", True, "Sandy loam soils"),
    ("Sorghum Fodder Cultivation", "Grow forage sorghum in close rows with quick nitrogen for high-quality green fodder.", "Sorghum", "Kharif", "beginner", "35-45 days", "Low", "High", True, "All soil types"),
    ("Cardamom Sucker Planting", "Plant select cardamom suckers in pits with shade and mulch for healthy clumps.", "Cardamom", "South-West Monsoon", "advanced", "2-3 days", "Medium", "High", True, "Forest loam soils"),
    ("Arecanut Management", "Regular de-trashing and leaf-area management keep arecanut palms healthy and bearing.", "Arecanut", "Whole Season", "intermediate", "Monthly rounds", "Medium", "High", True, "Deep red loam soils"),
    ("Chilli Harvest Maturity Index", "Harvest chilli at full red or green maturity based on the market and variety.", "Chilli", "Rabi", "beginner", "Weekly rounds", "Low", "Medium", True, "All soil types"),
    # ============ CATEGORY: Livestock ============
    ("Stall Feeding of Cattle", "Keep dairy cattle in clean stalls with a mixed green-and-concentrate ration.", "Cattle", "Year-Round", "beginner", "Daily routine", "Medium", "Medium", True, "Farmstead"),
    ("Cattle Shed Disinfection", "Clean, scrape and lime-wash cattle sheds weekly to break disease cycles.", "Cattle, Buffalo", "Year-Round", "beginner", "Weekly", "Low", "Low", True, "Farmstead"),
    ("De-worming Schedule for Cattle", "De-worm cattle at the recommended interval for weight gain and milk response.", "Cattle", "Every 4-6 Months", "beginner", "Half day", "Low", "Low", True, "Farmstead"),
    ("Poultry Vaccination Calendar", "Follow the broiler and layer vaccination schedule from day one for flock survival.", "Poultry", "Rearing Cycle", "intermediate", "At set ages", "Low", "Low", True, "Poultry house"),
    ("Mastitis Prevention in Dairy", "Keep milking hygiene high and dry-off feet clean to prevent udder infections.", "Dairy Cattle", "Lactation", "intermediate", "Daily", "Medium", "Low", True, "Dairy shed"),
    ("Urea-Molasses Mineral Block", "Offer a homemade urea-molasses block to improve roughage digestion and growth.", "Cattle, Buffalo", "Year-Round", "advanced", "Monthly prep", "Low", "Low", True, "Farmstead"),
    ("Silage Making for Fodder", "Chop, wilt and pack green fodder airtight to preserve quality feed for lean months.", "Cattle", "Harvest Season", "intermediate", "2-3 days", "Medium", "Low", True, "Fodder plots"),
    ("Hay Making for Animal Feed", "Dry surplus green grass and legumes to hay for the dry-season feeding buffer.", "Cattle, Sheep", "Harvest Season", "beginner", "3-5 days", "Low", "Low", True, "Fodder plots"),
    ("Composting Farmyard Manure", "Pit-compost fresh dung and litter to keep farmyard manure rich and weed-seed-free.", "Cattle", "Year-Round", "beginner", "60-90 days", "Low", "Low", True, "Farmstead"),
    ("Goat House Management", "Keep goats on raised, dry, ventilated platforms to control worms and foot rot.", "Goats", "Year-Round", "beginner", "Weekly", "Low", "Low", True, "Goat shed"),
    ("Sheep Shearing Program", "Shear sheep at the right season to protect them from heat and get sellable wool.", "Sheep", "Before Summer", "intermediate", "Half day", "Low", "Low", True, "Farmstead"),
    ("Chick Brooding Management", "Provide brooding heat and light as chicks need it for a strong first 14 days.", "Poultry", "Brooding Period", "intermediate", "First 2 weeks", "Medium", "Low", True, "Brooder house"),
    ("Layer Lighting Program", "Manage the light program step-wise to guide layers to steady egg production.", "Layer Poultry", "Laying Cycle", "advanced", "Daily", "Medium", "Low", True, "Poultry house"),
    ("Calf Colostrum Feeding", "Feed every calf colostrum within the first hours for lifetime immunity.", "Cattle", "Calving", "beginner", "At birth", "Low", "Low", True, "Dairy shed"),
    ("Artificial Insemination Timing", "Time AI against observed heat signs to lift conception rates in dairy animals.", "Cattle, Buffalo", "Heat Cycle", "intermediate", "At heat", "Low", "Low", True, "Farmstead"),
    ("Milking Hygiene Practices", "Follow clean-milking routines and teat dipping to keep milk safe and the udder healthy.", "Dairy Animals", "Lactation", "beginner", "Twice daily", "Low", "Low", True, "Dairy shed"),
    ("Buffalo Wallowing & Cooling", "Give buffaloes regular wallowing or wetting in summer to protect milk yield.", "Buffalo", "Summer", "beginner", "Daily", "Low", "High", True, "Farmstead"),
    ("Deep Litter Poultry System", "Manage bedding as a composting deep-litter layer for drier, healthier birds.", "Poultry", "Whole Cycle", "intermediate", "Season-long", "Low", "Low", True, "Poultry house"),
    # ============ CATEGORY: Smart Farming ============
    ("Drone Spraying of Pesticide", "Deploy a drone to spray uniform, targeted doses even in tall or lodged crops.", "Paddy, Cotton", "Growing Season", "advanced", "Hour per few acres", "High", "Low", True, "All soil types"),
    ("Drone Seeding of Paddy", "Broadcast pregerminated seed by drone for quick, low-labour sowing over wet fields.", "Paddy", "Kharif", "advanced", "Hour per few acres", "High", "High", True, "Puddle fields"),
    ("IoT Soil Moisture Sensors", "Bury in-field soil-moisture sensors to decide irrigation dates from data.", "All Crops", "Year-Round", "advanced", "1-2 days setup", "Medium", "Low", True, "All soil types"),
    ("Drip Automation with Timers", "Set irrigation timers and valves to water at the right time without being present.", "Drip-irrigated Crops", "Year-Round", "intermediate", "Half day setup", "Medium", "Low", True, "All soil types"),
    ("Weather-Based Irrigation Scheduling", "Start irrigation decisions from local rainfall and evapotranspiration forecasts.", "All Crops", "Whole Season", "intermediate", "Weekly", "Low", "Low", True, "All soil types"),
    ("Satellite NDVI Crop Monitoring", "Track crop health from satellite imagery and act only where the map shows stress.", "Large Plots", "Whole Season", "advanced", "Weekly check", "Medium", "Low", True, "Large holdings"),
    ("GPS Land Survey & Mapping", "Survey and map the farm boundary and field layout with GPS for planning.", "All Crops", "Setup", "intermediate", "Half day", "Medium", "Low", True, "All soil types"),
    ("Farm Record-Keeping App", "Log sowings, sprays and sales in a farm app to price and plan every season better.", "All Crops", "Year-Round", "beginner", "Daily", "Low", "Low", True, "All soil types"),
    ("Automated Weather Station", "Install a compact on-farm weather station for crop-stage-specific decisions.", "All Crops", "Year-Round", "advanced", "Half day setup", "Medium", "Low", True, "All soil types"),
    ("Hydroponic Fodder System", "Grow green fodder in trays with controlled water and light, independent of seasons.", "Cattle Feed", "Year-Round", "advanced", "Weekly cycle", "High", "Medium", True, "Indoor system"),
    ("Polyhouse Climate Control", "Manage micro-climate in a polyhouse for quality off-season vegetable crops.", "Vegetables, Flowers", "Off-Season", "advanced", "Whole cycle", "High", "Medium", True, "Protected structure"),
    ("Shade Net Cultivation", "Grow vegetables under shade nets to cut heat stress and improve produce quality.", "Vegetables", "Summer", "intermediate", "Whole cycle", "High", "Medium", True, "Protected structure"),
    ("Fertigation Controller Automation", "Program the fertigation controller to dose water-soluble fertilizer in set ratios.", "Drip Crops", "Growing Season", "advanced", "Half day setup", "Medium", "Low", True, "All soil types"),
    ("Solar Fencing for Farms", "Power field fencing with solar to protect produce and livestock with zero electric cost.", "All Crops, Orchards", "Year-Round", "advanced", "1-2 weeks", "High", "Low", True, "All land types"),
    ("AI Pest Detection Cameras", "Mount AI cameras in the field to flag pest activity days before it spreads.", "Large Plots", "Whole Season", "advanced", "1-2 days setup", "High", "Low", True, "Bigger holdings"),
    ("Tractor GPS Auto-Steering", "Use GPS guidance on the tractor for straight, overlap-free passes and less dead work.", "Large Plots", "Sowing & Spraying", "advanced", "Half day setup", "High", "Low", True, "Large fields"),
    ("Variable Rate Technology", "Apply inputs at variable rates across the field based on soil and yield maps.", "Large Plots", "Whole Season", "advanced", "Season setup", "High", "Low", True, "Large holdings"),
    ("Smart Grain Silo Monitoring", "Fit temperature and moisture probes in silos to catch grain heating early.", "Grain Stores", "Storage", "advanced", "Half day setup", "Medium", "Low", True, "Silos & godowns"),
    ("Blockchain Farm Records", "Record produce lots on an immutable ledger for certified traceability to buyers.", "All Crops", "Year-Round", "advanced", "Setup once", "Medium", "Low", True, "All holdings"),
    ("E-Agriculture Advisory Platforms", "Use phone and digital extension alerts for sowing, pest and market advisories.", "All Crops", "Year-Round", "beginner", "Daily check", "Low", "Low", True, "All soil types"),
    # ============ CATEGORY: Harvesting ============
    ("Harvest Timing by Moisture", "Confirm crop maturity by grain moisture percentage instead of the calendar.", "Wheat, Paddy, Maize", "Harvest Stage", "intermediate", "Few hours", "Low", "Low", True, "All soil types"),
    ("Combine Harvester Operation", "Run a combine to cut, thresh and clean in one pass for high-acreage crops.", "Wheat, Paddy, Soybean", "Harvest Stage", "advanced", "Hours per acre", "High", "Low", True, "Large level fields"),
    ("Paddy Mechanical Harvesting", "Use a reaper or combine matching field moisture to stop shattering losses.", "Paddy", "Harvest Stage", "advanced", "Hours per acre", "High", "High", True, "Level fields"),
    ("Wheat Threshing Method", "Thresh wheat with proper drum speed and crop feeding so grain stays whole.", "Wheat", "Harvest Stage", "intermediate", "Hours per ton", "Medium", "Low", True, "Threshing floor"),
    ("Groundnut Digger Harvesting", "Loosen soil with a digger before pulling plants so pods don't snap off underground.", "Groundnut", "Harvest Stage", "intermediate", "1-2 days", "Medium", "Low", True, "Sandy loam soils"),
    ("Sugarcane Cane Harvesting", "Cut sugarcane close to the ground and load quickly to preserve cane weight.", "Sugarcane", "Harvest Stage", "intermediate", "High labour days", "Medium", "High", True, "All soil types"),
    ("Cotton Picking Schedule", "Pick cotton in repeated rounds as bolls open, keeping lint grade high.", "Cotton", "Harvest Stage", "beginner", "Weekly rounds", "Low", "Low", True, "All soil types"),
    ("Chilli Harvest & Grading", "Harvest chilli at the right redness and grade pods before drying for better price.", "Chilli", "Harvest Stage", "beginner", "Every 4-5 days", "Low", "Low", True, "All soil types"),
    ("Onion Curing After Harvest", "Cure lifted onions in the field or shade for skins that store well.", "Onion", "Post-Harvest", "beginner", "7-14 days", "Low", "Low", True, "All soil types"),
    ("Garlic Twisting & Curing", "Twist garlic tops into strings and cure slowly for bulbs that store and price well.", "Garlic", "Post-Harvest", "beginner", "2-3 weeks", "Low", "Low", True, "All soil types"),
    ("Mango Maturity Harvest Index", "Pick mango at the light-green maturity stage for ideal ripening in transit.", "Mango", "Harvest Stage", "intermediate", "Daily rounds", "Medium", "Low", True, "All soil types"),
    ("Banana Bunch Harvesting", "Harvest banana bunches with clean cuts and padded transport for tamper-free peels.", "Banana", "Harvest Stage", "intermediate", "Per bunch", "Medium", "High", True, "All soil types"),
    ("Maize Cob Harvest Timing", "Harvest maize cobs just as husks dry for higher grain weight and clean cobs.", "Maize", "Harvest Stage", "beginner", "Daily rounds", "Low", "Low", True, "All soil types"),
    ("Early-Morning Vegetable Harvest", "Harvest leafy and fruit vegetables at dawn while they are fresh and water-full.", "Vegetables", "Harvest Stage", "beginner", "Morning rounds", "Low", "Low", True, "All soil types"),
    ("Potato Digger Harvest", "Dig potatoes with a mechanical digger and leave to skin-harden before pickup.", "Potato", "Harvest Stage", "intermediate", "1-2 days", "Medium", "Low", True, "Sandy loam soils"),
    ("Turmeric Boiling & Curing", "Boil turmeric rhizomes and cure them for brilliant colour and long shelf life.", "Turmeric", "Post-Harvest", "advanced", "2-3 days", "Medium", "Low", True, "All soil types"),
    ("Soybean Pod Harvest Drying", "Harvest soybean at low moisture and dry to 10% for safe oilseed storage.", "Soybean", "Harvest Stage", "beginner", "1-2 days", "Low", "Low", True, "All soil types"),
    ("Sorghum Grain Harvest", "Cut sorghum panicles at the right stage and thresh promptly to avoid grain mould.", "Sorghum", "Harvest Stage", "beginner", "1-2 days", "Low", "Low", True, "All soil types"),
    # ============ CATEGORY: Storage ============
    ("Paddy Sun Drying", "Spread clean paddy in thin layers on a clean floor and dry to 12% moisture.", "Paddy", "Post-Harvest", "beginner", "2-3 days", "Low", "Low", True, "Clean drying floor"),
    ("Paddy Gunny Bag Storage", "Stack well-dried paddy in clean gunny bags on pallets for village-scale storage.", "Paddy", "Storage", "beginner", "Whole season", "Low", "Low", True, "Storage room"),
    ("Hermetic Grain Storage", "Store grains in hermetic bags that cut oxygen and stop insects without chemicals.", "Paddy, Wheat, Pulses", "Storage", "intermediate", "Whole season", "Medium", "Low", True, "Any clean store"),
    ("Metal Bin Grain Storage", "Keep cleaned grain in metal bins that rodents cannot gnaw through.", "Grains", "Storage", "intermediate", "Whole season", "Medium", "Low", True, "Storage room"),
    ("Neem Leaf Grain Protection", "Mix dried neem leaves into stored grain to repel weevils safely and cheaply.", "Grains, Pulses", "Storage", "beginner", "Whole season", "Low", "Low", True, "Grain stores"),
    ("Godown Fumigation", "Fumigate empty and stocked godowns on a fixed calendar to hold insect pressure down.", "All Grains", "Storage", "advanced", "Seasonal", "Medium", "Low", True, "Godowns"),
    ("Rat-Proof Storage Platforms", "Raise grain stacks on pallets and platforms that rats and damp can't reach.", "All Grains", "Storage", "beginner", "During stacking", "Low", "Low", True, "Storage room"),
    ("Moisture Testing Before Storage", "Test grain moisture before bagging and refuse stock above the safe limit.", "Grains, Oilseeds", "Storage", "beginner", "Few minutes", "Low", "Low", True, "Before storage"),
    ("Stored Grain Pest Monitoring", "Probe stored grain monthly and act at the first live-insect finding.", "All Grains", "Storage", "beginner", "Monthly", "Low", "Low", True, "Grain stores"),
    ("Onion Mesh Bag Storage", "Bag cured onions in mesh and keep them in a dry, ventilated, elevated room.", "Onion", "Storage", "beginner", "Whole season", "Low", "Low", True, "Ventilated room"),
    ("Potato Cold Storage", "Store seed potatoes in a cold chamber to prevent sprouting and shrivelling.", "Potato", "Storage", "advanced", "Whole season", "High", "High", True, "Cold store"),
    ("Garlic Hanging Storage", "Hang cured garlic strings in a cool, dry, ventilated space for months of supply.", "Garlic", "Storage", "beginner", "Whole season", "Low", "Low", True, "Ventilated shed"),
    ("Mango Ripening Chamber", "Ripen mangoes in a ventilated chamber with controlled ethylene for uniform color.", "Mango", "Post-Harvest", "advanced", "3-5 days", "High", "Low", True, "Ripening unit"),
    ("Banana Ripening Chamber", "Use a controlled ethylene chamber for banana ripening that reaches market on time.", "Banana", "Post-Harvest", "advanced", "3-4 days", "High", "Low", True, "Ripening unit"),
    ("Seed Storage in Plastic Bins", "Store clean, dry seed in air-tight plastic bins away from light and rat reach.", "Seed Stocks", "Storage", "beginner", "Whole season", "Low", "Low", True, "Storage room"),
    ("Silo Aeration System", "Move air through silo grain to pull out heat and keep moisture uniform.", "Grains", "Storage", "advanced", "Seasonal", "High", "Low", True, "Silos"),
    ("Warehouse Receipt Financing Prep", "Prepare graded, threatened grain in a certified warehouse to borrow against it.", "Grains", "Storage", "intermediate", "Seasonal", "Medium", "Low", True, "Warehouse"),
    ("Wheat Stack Curing", "Stack just-threshed wheat stems in small stacks so grain finishes drying uniformly.", "Wheat", "Post-Harvest", "beginner", "1-2 weeks", "Low", "Low", True, "Threshing yard"),
    ("Turmeric & Ginger Dry Storage", "Store dried and cured turmeric and ginger in clean, dry, rodent-proof rooms.", "Turmeric, Ginger", "Storage", "beginner", "Whole season", "Low", "Low", True, "Clean store"),
    ("Chilli Pod Storage Rooms", "Keep dried chilli pods in low-light, ventilated rooms to protect colour and shine.", "Chilli", "Storage", "beginner", "Whole season", "Low", "Low", True, "Ventilated store"),
    ("Humidification for Fresh Vegetables", "Add controlled humidity in fresh-vegetable cold rooms to keep produce crisp.", "Vegetables", "Post-Harvest", "advanced", "Whole season", "High", "High", True, "Cold store"),
    ("Cold-Chain Pre-Cooling", "Pre-cool high-value produce promptly after harvest to extend every selling day.", "Fruits, Vegetables", "Post-Harvest", "advanced", "Whole season", "High", "Low", True, "Cold chain"),
]

TOTAL_TARGET = len(ENTRIES)
TARGET_TITLES = {e[0] for e in ENTRIES}
assert len(TARGET_TITLES) == TOTAL_TARGET, "Technique titles must be unique"


def build_technique(entry, index, category):
    title, desc, crop, season, difficulty, duration, cost, water, organic, soil = entry
    d = DETAILS[category]
    return {
        "technique_id": f"FA-TEC-{str(index).zfill(6)}",
        "title": title,
        "description": desc,
        "category": category,
        "crop": crop,
        "season": season,
        "difficulty": difficulty,
        "duration": duration,
        "cost_level": cost,
        "water_requirement": water,
        "is_organic": organic,
        "suitable_soil": soil,
        "materials": _enc(d["materials"]),
        "steps": _enc([s.replace("{crop}", crop) for s in d["steps"]]),
        "tips": d["tips"].replace("{crop}", crop),
        "benefits": _enc(d["benefits"]),
        "precautions": _enc(d["precautions"]),
        "common_mistakes": _enc(d["common_mistakes"]),
        "icon": CATEGORY_META[category]["icon"],
        "color": CATEGORY_META[category]["color"],
        "is_published": True,
    }


# (category, count) in the same order the ENTRIES list is grouped.
CATEGORY_COUNTS = [
    ("Soil", 20), ("Seeds", 18), ("Irrigation", 22), ("Fertilizer", 20),
    ("Pest Control", 24), ("Organic", 24), ("Crops", 34), ("Livestock", 18),
    ("Smart Farming", 20), ("Harvesting", 18), ("Storage", 22),
]
assert sum(c for _, c in CATEGORY_COUNTS) == TOTAL_TARGET, "Counts must sum to the catalog size"


def build_target_catalog():
    target = []
    idx = 0
    for category, count in CATEGORY_COUNTS:
        for n in range(count):
            target.append(build_technique(ENTRIES[idx + n], idx + n + 1, category))
        idx += count
    return target


def seed_techniques(db: Session):
    target = build_target_catalog()
    expected_ids = {t["technique_id"] for t in target}
    expected_titles = {t["title"] for t in target}
    current = db.query(Technique).all()
    if len(current) == len(target):
        if {t.technique_id for t in current} == expected_ids and {t.title for t in current} == expected_titles:
            return

    db.query(Technique).delete()
    db.flush()
    for t in target:
        db.add(Technique(**t))
    db.commit()
    print(f"Techniques seeded: {len(target)} techniques across {len(CATEGORY_META)} categories.")