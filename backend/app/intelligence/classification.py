import re

CATEGORY_ALIASES = {
    "natural disaster": "natural_disaster",
    "natural_disaster": "natural_disaster",
    "flood": "natural_disaster",
    "flooding": "natural_disaster",
    "earthquake": "natural_disaster",
    "storm": "natural_disaster",
    "weather": "weather",
    "climate": "weather",
    "conflict": "conflict",
    "war": "conflict",
    "attack": "conflict",
    "security": "security",
    "politics": "politics",
    "election": "politics",
    "government": "politics",
    "economy": "economy",
    "business": "economy",
    "market": "economy",
    "health": "health",
    "medical": "health",
    "technology": "technology",
    "ai": "technology",
    "environment": "environment",
    "infrastructure": "infrastructure",
    "transportation": "transportation",
    "energy": "energy",
    "science": "science",
    "other": "other",
    "international": "other",
}

KEYWORD_MAP = {
    "natural_disaster": [
        "flood", "flooding", "earthquake", "storm", "hurricane", "cyclone",
        "tsunami", "wildfire", "landslide", "evacuation", "disaster",
    ],
    "conflict": [
        "war", "attack", "missile", "battle", "military", "ceasefire",
        "explosion", "raid", "strike",
    ],
    "politics": [
        "election", "president", "government", "parliament", "minister",
        "vote", "policy", "diplomatic",
    ],
    "economy": [
        "economy", "inflation", "market", "trade", "industry", "bank",
        "currency", "investment", "tariff",
    ],
    "technology": [
        "ai", "artificial intelligence", "cyber", "software", "chip",
        "startup", "technology",
    ],
    "health": ["virus", "disease", "health", "hospital", "outbreak", "vaccine"],
    "environment": ["climate", "environment", "pollution", "drought", "emissions"],
    "infrastructure": ["bridge", "power grid", "infrastructure", "airport", "rail", "pipeline"],
    "transportation": ["flight", "train", "shipping", "transport", "airline", "crash"],
    "energy": ["energy", "oil", "gas", "power", "electricity", "grid"],
    "science": ["research", "scientists", "study", "space", "lab", "discovery"],
    "security": ["security", "police", "incident", "alert", "threat", "surveillance"],
    "weather": ["weather", "rain", "snow", "heatwave", "cold snap", "blizzard"],
}


def normalize_category(value):
    if value is None:
        return "other"

    raw = str(value).strip().lower().replace("_", " ")
    raw = re.sub(r"\s+", " ", raw)
    if not raw:
        return "other"

    if raw in CATEGORY_ALIASES:
        return CATEGORY_ALIASES[raw]

    for alias, category in CATEGORY_ALIASES.items():
        if raw == alias:
            return category

    for category, keywords in KEYWORD_MAP.items():
        if any(keyword in raw for keyword in keywords):
            return category

    return "other"


def classify_article(article):
    title = str(article.get("title") or "").strip()
    description = str(article.get("description") or "").strip()
    text = f"{title} {description}".lower()

    best_category = "other"
    best_score = 0

    for category, keywords in KEYWORD_MAP.items():
        score = sum(1 for keyword in keywords if keyword in text)
        if score > best_score:
            best_category = category
            best_score = score

    if best_score == 0:
        best_category = "other"

    confidence = 0.60
    if best_score > 0:
        confidence = min(0.98, 0.55 + (best_score * 0.10))

    return {
        "category": normalize_category(best_category),
        "subcategory": best_category,
        "confidence": round(confidence, 2),
    }
