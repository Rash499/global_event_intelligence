"""Versioned hierarchical event taxonomy.

Categories and subcategories are the vocabulary of the whole platform: the
classification pipeline, clustering, analytics, alerts and the assistant all
refer to these identifiers.  The taxonomy is **versioned** so that later changes
can be introduced without invalidating historical analytics: stored events keep
the ``taxonomy_version`` they were classified under.

Identifiers are lower_snake_case and stable. Display names live alongside so the
frontend never has to hardcode a mapping.
"""

from __future__ import annotations

TAXONOMY_VERSION = "1.0"


def _sub(key: str, label: str, keywords: tuple[str, ...]) -> dict:
    return {"key": key, "label": label, "keywords": keywords}


# Ordered mapping: order is used as a deterministic tie-break and as the
# presentation order in the UI.
TAXONOMY: dict[str, dict] = {
    "armed_conflict": {
        "label": "Armed Conflict and Security",
        "description": "Organised violence between armed actors, military operations and security incidents.",
        "keywords": (
            "war", "airstrike", "air strike", "missile", "shelling", "artillery",
            "offensive", "military operation", "troops", "ceasefire", "militant",
            "insurgent", "armed group", "clashes", "frontline", "battle",
        ),
        "subcategories": {
            "armed_clash": _sub("armed_clash", "Armed clash", ("clash", "fighting", "battle", "exchange of fire")),
            "airstrike": _sub("airstrike", "Airstrike", ("airstrike", "air strike", "air raid", "bombing raid")),
            "missile_attack": _sub("missile_attack", "Missile or drone attack", ("missile", "drone strike", "rocket attack", "uav")),
            "shelling": _sub("shelling", "Shelling or artillery", ("shelling", "artillery", "mortar fire")),
            "military_operation": _sub("military_operation", "Military operation", ("military operation", "offensive", "mobilisation", "mobilization", "deployment")),
            "border_incident": _sub("border_incident", "Border incident", ("border", "cross-border", "incursion", "frontier")),
            "ceasefire_development": _sub("ceasefire_development", "Ceasefire development", ("ceasefire", "truce", "peace deal", "armistice")),
            "security_incident": _sub("security_incident", "Security incident", ("security forces", "checkpoint", "ambush", "police operation")),
        },
    },
    "political_development": {
        "label": "Political Developments",
        "description": "Elections, government change, legislation, diplomacy and political crises.",
        "keywords": (
            "election", "referendum", "parliament", "president", "prime minister",
            "cabinet", "coalition", "legislation", "bill", "sanctions",
            "diplomatic", "embassy", "summit", "treaty", "coup", "impeachment",
        ),
        "subcategories": {
            "election": _sub("election", "Election", ("election", "poll", "ballot", "vote count", "referendum")),
            "government_change": _sub("government_change", "Government change", ("resign", "appointed", "sworn in", "coup", "new government", "caretaker")),
            "legislative_development": _sub("legislative_development", "Legislative development", ("parliament", "bill", "legislation", "law passed", "vote in parliament")),
            "diplomatic_dispute": _sub("diplomatic_dispute", "Diplomatic dispute", ("expel", "ambassador", "diplomatic row", "recall", "summoned")),
            "sanctions": _sub("sanctions", "Sanctions", ("sanction", "embargo", "asset freeze", "blacklist")),
            "political_crisis": _sub("political_crisis", "Political crisis", ("crisis", "impeachment", "no-confidence", "state of emergency", "political turmoil")),
        },
    },
    "protest_unrest": {
        "label": "Protests and Civil Unrest",
        "description": "Demonstrations, strikes, riots and civil disorder.",
        "keywords": (
            "protest", "demonstration", "rally", "riot", "strike", "unrest",
            "demonstrators", "march", "civil disobedience", "curfew", "looting",
        ),
        "subcategories": {
            "demonstration": _sub("demonstration", "Demonstration", ("protest", "demonstration", "rally", "march")),
            "labor_strike": _sub("labor_strike", "Labour strike", ("strike", "walkout", "union", "industrial action")),
            "riot": _sub("riot", "Riot or violent unrest", ("riot", "looting", "clashes with police", "vandalism")),
            "civil_disobedience": _sub("civil_disobedience", "Civil disobedience", ("blockade", "sit-in", "occupation", "shutdown")),
            "crackdown": _sub("crackdown", "Crackdown on unrest", ("crackdown", "dispersed", "tear gas", "arrested protesters", "curfew")),
        },
    },
    "terrorism_extremism": {
        "label": "Terrorism and Extremism",
        "description": "Terror attacks, extremist violence and counter-terrorism operations.",
        "keywords": (
            "terror", "terrorist", "suicide bomb", "car bomb", "extremist",
            "jihadist", "hostage", "kidnapping", "insurgent attack", "gunmen",
        ),
        "subcategories": {
            "terror_attack": _sub("terror_attack", "Terror attack", ("terror attack", "suicide bomb", "car bomb", "gunmen", "explosion claimed")),
            "extremist_violence": _sub("extremist_violence", "Extremist violence", ("extremist", "jihadist", "militant group", "insurgents")),
            "counter_terrorism": _sub("counter_terrorism", "Counter-terrorism operation", ("counter-terrorism", "counterterrorism", "raid", "arrested suspects")),
            "hostage_incident": _sub("hostage_incident", "Hostage or kidnapping incident", ("hostage", "kidnap", "abduct")),
        },
    },
    "natural_disaster": {
        "label": "Natural Disasters",
        "description": "Geophysical, hydrological and meteorological disasters with reported impact.",
        "keywords": (
            "earthquake", "flood", "cyclone", "hurricane", "typhoon", "tsunami",
            "landslide", "wildfire", "volcano", "eruption", "drought",
            "disaster", "evacuation", "magnitude", "evacuated", "tremor",
        ),
        "subcategories": {
            "earthquake": _sub("earthquake", "Earthquake", ("earthquake", "magnitude", "seismic", "tremor", "quake")),
            "flood": _sub("flood", "Flood", ("flood", "flooding", "flash flood", "inundation", "overflow")),
            "tropical_cyclone": _sub("tropical_cyclone", "Tropical cyclone", ("cyclone", "hurricane", "typhoon", "tropical storm")),
            "landslide": _sub("landslide", "Landslide", ("landslide", "mudslide", "rockslide")),
            "wildfire": _sub("wildfire", "Wildfire", ("wildfire", "bushfire", "forest fire", "blaze")),
            "volcanic_activity": _sub("volcanic_activity", "Volcanic activity", ("volcano", "eruption", "lava", "ash cloud")),
            "tsunami": _sub("tsunami", "Tsunami", ("tsunami", "tidal wave")),
            "drought": _sub("drought", "Drought", ("drought", "water shortage", "crop failure")),
        },
    },
    "severe_weather": {
        "label": "Weather and Extreme Climate",
        "description": "Severe weather and climate extremes, including official warnings.",
        "keywords": (
            "heatwave", "heat wave", "cold snap", "blizzard", "snowstorm", "storm",
            "heavy rain", "hail", "gale", "warning", "extremely high temperature",
        ),
        "subcategories": {
            "severe_storm": _sub("severe_storm", "Severe storm", ("severe storm", "thunderstorm", "hail", "gale", "squall")),
            "extreme_heat": _sub("extreme_heat", "Extreme heat", ("heatwave", "heat wave", "record temperature", "extreme heat")),
            "extreme_cold": _sub("extreme_cold", "Extreme cold", ("cold snap", "blizzard", "snowstorm", "freezing")),
            "heavy_rainfall": _sub("heavy_rainfall", "Heavy rainfall", ("heavy rain", "torrential", "monsoon", "downpour")),
            "official_weather_warning": _sub("official_weather_warning", "Official weather warning", ("weather warning", "red alert", "orange alert", "meteorological warning")),
        },
    },
    "public_health": {
        "label": "Public Health",
        "description": "Disease outbreaks, public health emergencies and health-system events.",
        "keywords": (
            "outbreak", "epidemic", "pandemic", "cholera", "ebola", "measles",
            "dengue", "malaria", "polio", "virus", "infection", "cases reported",
            "health emergency", "vaccination",
        ),
        "subcategories": {
            "disease_outbreak": _sub("disease_outbreak", "Disease outbreak", ("outbreak", "epidemic", "cases reported", "infection")),
            "pandemic_alert": _sub("pandemic_alert", "Pandemic alert", ("pandemic", "public health emergency", "global health emergency")),
            "health_system": _sub("health_system", "Health system event", ("hospital", "health workers", "health system", "medical supplies")),
            "vaccination_campaign": _sub("vaccination_campaign", "Vaccination campaign", ("vaccination", "immunisation", "immunization", "vaccine campaign")),
        },
    },
    "humanitarian": {
        "label": "Humanitarian Crises",
        "description": "Displacement, food insecurity, humanitarian access and refugee situations.",
        "keywords": (
            "humanitarian", "refugee", "displaced", "idp", "famine", "food insecurity",
            "aid", "relief", "malnutrition", "shelter", "asylum",
        ),
        "subcategories": {
            "displacement": _sub("displacement", "Displacement", ("displaced", "refugee", "idp", "fled", "evacuated")),
            "food_insecurity": _sub("food_insecurity", "Food insecurity", ("famine", "food insecurity", "malnutrition", "hunger")),
            "humanitarian_access": _sub("humanitarian_access", "Humanitarian access", ("humanitarian", "aid convoy", "relief operation", "access denied")),
            "refugee_crisis": _sub("refugee_crisis", "Refugee crisis", ("refugee crisis", "asylum", "border crossing", "camp")),
        },
    },
    "economic_financial": {
        "label": "Economic and Financial Developments",
        "description": "Macroeconomic, market, trade and financial-system developments.",
        "keywords": (
            "economy", "inflation", "interest rate", "gdp", "recession", "currency",
            "central bank", "stock market", "tariff", "trade deal", "default",
            "imf", "debt",
        ),
        "subcategories": {
            "economic_policy": _sub("economic_policy", "Economic policy", ("interest rate", "central bank", "budget", "fiscal", "monetary")),
            "market_event": _sub("market_event", "Market event", ("stock market", "shares", "bond", "currency", "crash", "rally")),
            "trade_development": _sub("trade_development", "Trade development", ("tariff", "trade deal", "export", "import", "trade war")),
            "financial_crisis": _sub("financial_crisis", "Financial crisis", ("default", "bailout", "debt crisis", "currency collapse")),
        },
    },
    "energy_infrastructure": {
        "label": "Energy and Infrastructure",
        "description": "Power, water, fuel, telecom and transport infrastructure disruptions.",
        "keywords": (
            "power outage", "blackout", "grid", "pipeline", "electricity", "oil",
            "gas supply", "water supply", "dam", "infrastructure", "telecom",
            "fuel", "refinery", "substation",
        ),
        "subcategories": {
            "power_disruption": _sub("power_disruption", "Power disruption", ("power outage", "blackout", "grid failure", "electricity")),
            "water_infrastructure": _sub("water_infrastructure", "Water infrastructure", ("water supply", "dam", "reservoir", "water treatment")),
            "fuel_energy": _sub("fuel_energy", "Fuel and energy supply", ("oil", "gas supply", "pipeline", "refinery", "fuel shortage")),
            "telecom_internet": _sub("telecom_internet", "Telecom and internet", ("internet shutdown", "telecom", "network outage", "mobile network")),
        },
    },
    "transportation": {
        "label": "Transportation and Logistics",
        "description": "Aviation, maritime, rail and road incidents and logistics disruption.",
        "keywords": (
            "plane crash", "derailment", "train crash", "ship", "vessel", "port",
            "airport", "flight", "shipping", "road accident", "ferry", "cargo",
        ),
        "subcategories": {
            "aviation_incident": _sub("aviation_incident", "Aviation incident", ("plane crash", "flight", "aviation", "airport", "airliner")),
            "maritime_incident": _sub("maritime_incident", "Maritime incident", ("ship", "vessel", "ferry", "port", "shipping")),
            "rail_road_incident": _sub("rail_road_incident", "Rail or road incident", ("derail", "train crash", "road accident", "bus crash")),
            "logistics_disruption": _sub("logistics_disruption", "Logistics disruption", ("logistics", "supply chain", "cargo", "container", "freight")),
        },
    },
    "cyber_technology": {
        "label": "Cybersecurity and Technology",
        "description": "Cyber attacks, data breaches, technology incidents and AI developments.",
        "keywords": (
            "cyberattack", "cyber attack", "ransomware", "data breach", "hacking",
            "malware", "vulnerability", "artificial intelligence", "outage",
            "software", "semiconductor",
        ),
        "subcategories": {
            "cyber_attack": _sub("cyber_attack", "Cyber attack", ("cyberattack", "cyber attack", "ransomware", "malware", "ddos")),
            "data_breach": _sub("data_breach", "Data breach", ("data breach", "leaked", "exposed records", "stolen data")),
            "technology_incident": _sub("technology_incident", "Technology incident", ("outage", "system failure", "bug", "service disruption")),
            "technology_development": _sub("technology_development", "Technology development", ("artificial intelligence", "ai model", "semiconductor", "software release")),
        },
    },
    "crime_public_safety": {
        "label": "Crime and Public Safety",
        "description": "Serious crime, accidents and public safety incidents.",
        "keywords": (
            "murder", "shooting", "gunman", "robbery", "trafficking", "arrest",
            "police", "crime", "accident", "stampede", "building fire", "fire broke out", "collapse",
        ),
        "subcategories": {
            "violent_crime": _sub("violent_crime", "Violent crime", ("murder", "shooting", "stabbing", "gunman")),
            "organised_crime": _sub("organised_crime", "Organised crime", ("trafficking", "smuggling", "cartel", "gang")),
            "public_safety_incident": _sub("public_safety_incident", "Public safety incident", ("stampede", "building collapse", "fire broke out", "building fire", "accident")),
        },
    },
    "international_relations": {
        "label": "International Relations",
        "description": "Bilateral and multilateral relations, summits and international institutions.",
        "keywords": (
            "bilateral", "united nations", "nato", "eu ", "g7", "g20", "summit",
            "foreign minister", "state visit", "agreement signed", "talks",
            "negotiations", "peace talks",
        ),
        "subcategories": {
            "diplomatic_engagement": _sub("diplomatic_engagement", "Diplomatic engagement", ("state visit", "bilateral", "talks", "negotiations", "summit")),
            "international_institution": _sub("international_institution", "International institution", ("united nations", "security council", "nato", "european union", "world bank")),
            "treaty_agreement": _sub("treaty_agreement", "Treaty or agreement", ("agreement signed", "treaty", "accord", "memorandum")),
        },
    },
    "environmental": {
        "label": "Environmental Incidents",
        "description": "Pollution, ecological damage and environmental hazards.",
        "keywords": (
            "oil spill", "chemical leak", "pollution", "contamination",
            "deforestation", "emissions", "toxic", "wildlife", "ecosystem",
        ),
        "subcategories": {
            "pollution_incident": _sub("pollution_incident", "Pollution incident", ("oil spill", "chemical leak", "contamination", "toxic")),
            "ecological_damage": _sub("ecological_damage", "Ecological damage", ("deforestation", "ecosystem", "wildlife", "coral")),
            "climate_development": _sub("climate_development", "Climate development", ("emissions", "climate target", "carbon", "cop summit")),
        },
    },
    "other": {
        "label": "Other / Unclassified",
        "description": "Insufficient evidence to assign a category.",
        "keywords": (),
        "subcategories": {
            "unclassified": _sub("unclassified", "Unclassified", ("",)),
        },
    },
}

CATEGORY_KEYS = tuple(TAXONOMY.keys())

# Legacy identifiers that the pre-taxonomy code wrote, mapped onto the new
# vocabulary. Kept so historical rows keep their meaning.
LEGACY_CATEGORY_MAP = {
    "conflict": "armed_conflict",
    "security": "armed_conflict",
    "politics": "political_development",
    "protest": "protest_unrest",
    "unrest": "protest_unrest",
    "terrorism": "terrorism_extremism",
    "weather": "severe_weather",
    "health": "public_health",
    "humanitarian": "humanitarian",
    "economy": "economic_financial",
    "energy": "energy_infrastructure",
    "infrastructure": "energy_infrastructure",
    "transportation": "transportation",
    "technology": "cyber_technology",
    "cyber": "cyber_technology",
    "crime": "crime_public_safety",
    "international": "international_relations",
    "environment": "environmental",
    "science": "other",
    "other": "other",
    "unknown": "other",
}


def category_label(category: str | None) -> str:
    entry = TAXONOMY.get(category or "")
    return entry["label"] if entry else "Other / Unclassified"


def subcategory_label(category: str | None, subcategory: str | None) -> str:
    entry = TAXONOMY.get(category or "")
    if not entry or not subcategory:
        return "Unclassified"
    sub = entry["subcategories"].get(subcategory)
    return sub["label"] if sub else "Unclassified"


def taxonomy_payload() -> dict:
    """Serialisable taxonomy for the API/frontend."""
    return {
        "version": TAXONOMY_VERSION,
        "categories": [
            {
                "key": key,
                "label": value["label"],
                "description": value["description"],
                "subcategories": [
                    {"key": sub["key"], "label": sub["label"]}
                    for sub in value["subcategories"].values()
                ],
            }
            for key, value in TAXONOMY.items()
        ],
    }
