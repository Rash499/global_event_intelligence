import re
from datetime import datetime, timezone

COUNTRIES = {
    "Sri Lanka": ("LK", 7.8731, 80.7718),
    "India": ("IN", 20.5937, 78.9629),
    "Japan": ("JP", 36.2048, 138.2529),
    "United States": ("US", 37.0902, -95.7129),
    "United Kingdom": ("GB", 55.3781, -3.4360),
    "China": ("CN", 35.8617, 104.1954),
    "Australia": ("AU", -25.2744, 133.7751),
    "Germany": ("DE", 51.1657, 10.4515),
    "France": ("FR", 46.2276, 2.2137),
    "Ukraine": ("UA", 48.3794, 31.1656),
    "Russia": ("RU", 61.5240, 105.3188),
    "Canada": ("CA", 56.1304, -106.3468),
    "Brazil": ("BR", -14.2350, -51.9253),
    "Indonesia": ("ID", -0.7893, 113.9213),
    "Pakistan": ("PK", 30.3753, 69.3451),
}

KEYWORDS = {
    "conflict": ["war", "attack", "missile", "military", "fighting", "conflict", "ceasefire"],
    "natural_disaster": ["earthquake", "flood", "storm", "cyclone", "hurricane", "tsunami", "landslide", "wildfire"],
    "politics": ["election", "president", "parliament", "government", "minister", "vote", "political"],
    "economy": ["economy", "inflation", "interest rate", "market", "investment", "trade", "gdp", "bank"],
    "technology": ["technology", "ai", "artificial intelligence", "cyber", "software", "chip", "startup"],
    "health": ["health", "virus", "disease", "hospital", "outbreak", "vaccine"],
    "environment": ["climate", "environment", "pollution", "emissions", "drought"],
}

def analyze(title: str, description: str = ""):
    text = f"{title} {description}".lower()
    category = "international"
    best_score = 0
    for name, words in KEYWORDS.items():
        score = sum(1 for w in words if w in text)
        if score > best_score:
            category, best_score = name, score

    country = None
    code = None
    lat = lon = None
    for name, data in COUNTRIES.items():
        if name.lower() in text:
            country = name
            code, lat, lon = data
            break

    if category == "natural_disaster":
        importance = 8
    elif category in ("conflict", "politics"):
        importance = 7
    elif category in ("economy", "health", "environment"):
        importance = 6
    else:
        importance = 5

    if any(w in text for w in ["major", "deadly", "massive", "crisis", "breaking"]):
        importance = min(10, importance + 1)

    summary = re.sub(r"\s+", " ", description or title).strip()
    if len(summary) > 360:
        summary = summary[:357] + "..."

    return {
        "title": title.strip(),
        "summary": summary,
        "category": category,
        "country": country,
        "country_code": code,
        "latitude": lat,
        "longitude": lon,
        "importance": importance,
        "confidence": 0.62 if country else 0.45,
        "event_time": datetime.now(timezone.utc).isoformat(),
    }
