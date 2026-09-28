import hashlib
import re
from datetime import datetime
from urllib.parse import urlparse


STOPWORDS = {
    "the",
    "a",
    "an",
    "of",
    "in",
    "on",
    "at",
    "for",
    "to",
    "and",
    "with",
    "after",
    "before",
    "into",
    "from",
    "by",
    "as",
    "over",
    "under",
    "major",
    "breaking",
    "latest",
    "update",
    "news",
}


def normalize_text(value):
    if value is None:
        return ""
    text = str(value).lower()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def normalize_url(value):
    if not value:
        return ""
    parsed = urlparse(str(value))
    host = parsed.netloc.lower().replace("www.", "")
    path = parsed.path.rstrip("/")
    return f"{host}{path}"


def normalize_title(value):
    text = normalize_text(value)
    tokens = [token for token in text.split() if token and token not in STOPWORDS]
    return " ".join(tokens)


def _hash_value(value):
    return hashlib.sha256(normalize_text(value).encode("utf-8")).hexdigest()


def _jaccard_similarity(left, right):
    if not left or not right:
        return 0.0

    left_tokens = set(left.split())
    right_tokens = set(right.split())
    if not left_tokens and not right_tokens:
        return 0.0

    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def _token_overlap(left, right):
    if not left or not right:
        return 0.0

    left_tokens = left.split()
    right_tokens = right.split()
    if not left_tokens or not right_tokens:
        return 0.0

    common = sum(1 for token in left_tokens if token in right_tokens)
    return common / min(len(left_tokens), len(right_tokens))


def _parse_datetime(value):
    if not value:
        return None

    if isinstance(value, datetime):
        return value

    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def is_duplicate(left, right):
    if left is None or right is None:
        return False

    left_url = normalize_url(left.get("url"))
    right_url = normalize_url(right.get("url"))
    if left_url and right_url and left_url == right_url:
        return True

    left_hash = left.get("content_hash") or left.get("hash")
    right_hash = right.get("content_hash") or right.get("hash")
    if left_hash and right_hash and left_hash == right_hash:
        return True

    left_title = normalize_title(left.get("title") or left.get("event_title") or "")
    right_title = normalize_title(right.get("title") or right.get("event_title") or "")
    if left_title and right_title:
        if left_title == right_title:
            return True
        if _jaccard_similarity(left_title, right_title) >= 0.75:
            return True

        shared_tokens = set(left_title.split()) & set(right_title.split())
        if len(shared_tokens) >= 2:
            token_overlap = _token_overlap(left_title, right_title)
            if token_overlap >= 0.5:
                return True

    left_desc = normalize_text(left.get("description") or left.get("summary") or "")
    right_desc = normalize_text(right.get("description") or right.get("summary") or "")
    if left_desc and right_desc:
        overlap = _token_overlap(left_desc, right_desc)
        if overlap >= 0.78:
            return True

    left_time = _parse_datetime(left.get("published_at") or left.get("event_time"))
    right_time = _parse_datetime(right.get("published_at") or right.get("event_time"))
    if left_time and right_time and abs((left_time - right_time).total_seconds()) <= 4 * 3600:
        if left_title and right_title:
            shared_tokens = set(left_title.split()) & set(right_title.split())
            if len(shared_tokens) >= 2 or _jaccard_similarity(left_title, right_title) >= 0.6:
                return True

    return False


def find_duplicate_article(article, existing_articles):
    for candidate in existing_articles:
        if is_duplicate(article, candidate):
            return candidate
    return None


def create_article_hash(title, url):
    value = f"{normalize_url(url)}|{normalize_title(title)}"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
