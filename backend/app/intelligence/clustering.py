from math import asin, cos, hypot, radians, sin, sqrt


def haversine_distance_km(lat1, lon1, lat2, lon2):
    """Return great-circle distance in kilometres."""
    phi1, phi2 = radians(float(lat1)), radians(float(lat2))
    dphi = radians(float(lat2) - float(lat1))
    dlambda = radians(float(lon2) - float(lon1))
    a = sin(dphi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(dlambda / 2) ** 2
    return 6371.0088 * 2 * asin(sqrt(max(0.0, min(1.0, a))))


from .deduplication import normalize_title

EVENT_CLUSTER_TIME_WINDOW_HOURS = 48
EVENT_CLUSTER_SIMILARITY_THRESHOLD = 0.70
EVENT_CLUSTER_DISTANCE_KM = 200


def _parse_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_datetime(value):
    if not value:
        return None

    from datetime import datetime

    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def score_event_similarity(left, right):
    score = 0.0

    left_title = normalize_title(left.get("title") or left.get("event_title") or "")
    right_title = normalize_title(right.get("title") or right.get("event_title") or "")
    if left_title and right_title:
        if left_title == right_title:
            score += 0.45
        else:
            left_tokens = set(left_title.split())
            right_tokens = set(right_title.split())
            if left_tokens or right_tokens:
                overlap = len(left_tokens & right_tokens) / max(len(left_tokens | right_tokens), 1)
                score += overlap * 0.40

    left_country = (left.get("country") or "").lower()
    right_country = (right.get("country") or "").lower()
    if left_country and right_country and left_country == right_country:
        score += 0.20

    left_cat = (left.get("category") or "").lower()
    right_cat = (right.get("category") or "").lower()
    if left_cat and right_cat and left_cat == right_cat:
        score += 0.15

    left_lat = _parse_float(left.get("latitude"))
    left_lon = _parse_float(left.get("longitude"))
    right_lat = _parse_float(right.get("latitude"))
    right_lon = _parse_float(right.get("longitude"))
    if left_lat is not None and right_lat is not None and left_lon is not None and right_lon is not None:
        distance = haversine_distance_km(left_lat, left_lon, right_lat, right_lon)
        if distance <= EVENT_CLUSTER_DISTANCE_KM:
            score += 0.15

    left_time = _parse_datetime(left.get("event_time") or left.get("published_at"))
    right_time = _parse_datetime(right.get("event_time") or right.get("published_at"))
    if left_time and right_time:
        delta = abs((left_time - right_time).total_seconds()) / 3600
        if delta <= EVENT_CLUSTER_TIME_WINDOW_HOURS:
            score += 0.15

    return min(1.0, max(0.0, score))


def find_matching_event(article, existing_events):
    best_match = None
    best_score = 0.0

    for event in existing_events:
        sim = score_event_similarity(article, event)
        if sim >= EVENT_CLUSTER_SIMILARITY_THRESHOLD and sim > best_score:
            best_match = event
            best_score = sim

    return best_match
