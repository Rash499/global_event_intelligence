"""Duplicate and syndication detection.

Two different questions are answered here:

1. **Is this article already stored?** (``find_duplicate_article``) — exact
   canonical URL, content fingerprint, or near-identical title+description
   inside a short time window.

2. **Is this article independent reporting?** (``assess_independence``) — five
   sites republishing one wire story are *one* confirmation, not five. The
   duplicate layer therefore also records who syndicated whom so confidence
   scoring can count publishers, not URLs.

Near-duplicate matching is deliberately conservative: a shared country name and
a couple of generic words must not merge unrelated reports.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .urls import (
    canonicalize_url,
    is_aggregator,
    publisher_domain,
    publisher_family,
)

STOPWORDS = {
    "the", "a", "an", "of", "in", "on", "at", "for", "to", "and", "with",
    "after", "before", "into", "from", "by", "as", "over", "under", "major",
    "breaking", "latest", "update", "news", "says", "said", "new", "amid",
    "its", "his", "her", "their", "this", "that", "will", "was", "were",
    "has", "have", "had", "be", "been", "is", "are", "it", "but", "not",
    "more", "than", "about", "against", "during", "could", "would", "may",
}

# Title similarity thresholds. Tuned so that "Flooding in Japan" and "Japan
# flooding forces evacuations" are near duplicates, while "Election results in
# Japan" and "Flooding in Japan" are not.
TITLE_JACCARD_NEAR_DUPLICATE = 0.72
TITLE_CONTAINMENT_NEAR_DUPLICATE = 0.80
DESCRIPTION_OVERLAP_NEAR_DUPLICATE = 0.82
# Near-duplicate matching only applies within this window; the same words a week
# apart are usually a follow-up story, not a duplicate.
NEAR_DUPLICATE_WINDOW_HOURS = 48


def normalize_text(value) -> str:
    if value is None:
        return ""
    text = str(value).lower()
    text = text.replace("’", "'").replace("–", "-").replace("—", "-")
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def normalize_url(value) -> str:
    """Backwards-compatible wrapper; canonicalisation replaced the old logic."""
    return canonicalize_url(value)


def normalize_title(value) -> str:
    text = normalize_text(value)
    tokens = [token for token in text.split() if token and token not in STOPWORDS]
    return " ".join(tokens)


def _hash_value(value) -> str:
    return hashlib.sha256(normalize_text(value).encode("utf-8")).hexdigest()


def _tokens(value: str) -> set[str]:
    return {token for token in value.split() if len(token) > 2 or token.isdigit()}


def _jaccard_similarity(left: str, right: str) -> float:
    left_tokens, right_tokens = _tokens(left), _tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def _token_overlap(left: str, right: str) -> float:
    left_tokens, right_tokens = left.split(), right.split()
    if not left_tokens or not right_tokens:
        return 0.0
    overlap = len(set(left_tokens) & set(right_tokens))
    return overlap / min(len(set(left_tokens)), len(set(right_tokens)))


def _containment(left: str, right: str) -> float:
    """Share of the shorter title that appears in the longer one."""
    left_tokens, right_tokens = _tokens(left), _tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / min(len(left_tokens), len(right_tokens))


def _parse_datetime(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        text = str(value).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _within_window(left, right, hours: int = NEAR_DUPLICATE_WINDOW_HOURS) -> bool:
    left_time = _parse_datetime(
        left.get("published_at") or left.get("event_time") or left.get("first_seen_at")
    )
    right_time = _parse_datetime(
        right.get("published_at") or right.get("event_time") or right.get("first_seen_at")
    )
    if not left_time or not right_time:
        # Without timestamps we cannot rule out a follow-up story, so the
        # time-based near-duplicate path stays closed.
        return False
    return abs((left_time - right_time)) <= timedelta(hours=hours)


@dataclass
class DuplicateVerdict:
    is_duplicate: bool
    kind: str = "none"  # canonical_url | url | hash | title | description | none
    matched: dict | None = None
    similarity: float = 0.0

    def as_dict(self) -> dict:
        return {
            "is_duplicate": self.is_duplicate,
            "kind": self.kind,
            "similarity": round(self.similarity, 4),
            "matched_url": (self.matched or {}).get("url"),
        }


def compare_articles(left: dict, right: dict) -> DuplicateVerdict:
    """Classify one candidate pair. Order-independent."""
    if left is None or right is None:
        return DuplicateVerdict(False)

    left_canonical = canonicalize_url(left.get("url"))
    right_canonical = canonicalize_url(right.get("url"))
    if left_canonical and left_canonical == right_canonical:
        return DuplicateVerdict(True, "canonical_url", right, 1.0)

    left_provider_id = left.get("provider_record_id")
    if (
        left_provider_id
        and left_provider_id == right.get("provider_record_id")
        and left.get("provider") == right.get("provider")
    ):
        return DuplicateVerdict(True, "provider_record", right, 1.0)

    left_hash = left.get("content_hash") or left.get("hash")
    right_hash = right.get("content_hash") or right.get("hash")
    if left_hash and right_hash and left_hash == right_hash:
        return DuplicateVerdict(True, "hash", right, 1.0)

    left_title = normalize_title(left.get("title") or left.get("event_title") or "")
    right_title = normalize_title(right.get("title") or right.get("event_title") or "")

    if not left_title or not right_title:
        return DuplicateVerdict(False)

    if left_title == right_title:
        return DuplicateVerdict(True, "title", right, 1.0)

    if not _within_window(left, right):
        return DuplicateVerdict(False)

    jaccard = _jaccard_similarity(left_title, right_title)
    containment = _containment(left_title, right_title)
    if jaccard >= TITLE_JACCARD_NEAR_DUPLICATE:
        return DuplicateVerdict(True, "title", right, jaccard)
    # Headline rewrites ("Major flooding in Japan" / "Flooding hits Japan causing
    # emergency") share only two of their significant tokens, so token
    # containment is the fairer measure. Short titles are excluded because two
    # shared words carry little meaning when there are only three in total.
    union = _tokens(left_title) | _tokens(right_title)
    same_publisher = (
        publisher_family(publisher_domain(left.get("url"), left.get("publisher_domain")))
        == publisher_family(publisher_domain(right.get("url"), right.get("publisher_domain")))
    )
    # Different newsrooms describing the same incident share facts, not
    # wording, so the bar for them is higher than for a publisher updating its
    # own story.
    if len(union) >= 4 and containment >= (0.55 if same_publisher else 0.80):
        return DuplicateVerdict(True, "title", right, containment)

    # Same newsroom publishing the same headline with extra detail ("Japan quake:
    # magnitude 6.8 hits central Honshu" vs "... tsunami advisory issued") is one
    # story being updated, not independent confirmation.
    if same_publisher and len(union) >= 5 and containment >= 0.45:
        return DuplicateVerdict(True, "title_same_publisher", right, containment)

    left_desc = normalize_text(left.get("description") or left.get("summary") or "")
    right_desc = normalize_text(right.get("description") or right.get("summary") or "")
    if left_desc and right_desc and len(left_desc) > 60:
        overlap = _token_overlap(left_desc, right_desc)
        if overlap >= DESCRIPTION_OVERLAP_NEAR_DUPLICATE and jaccard >= 0.35:
            return DuplicateVerdict(True, "description", right, overlap)

    return DuplicateVerdict(False)


def is_duplicate(left, right) -> bool:
    return compare_articles(left, right).is_duplicate


def find_duplicate_article(article, existing_articles):
    """Return the first stored article that duplicates ``article``."""
    for candidate in existing_articles:
        if compare_articles(article, candidate).is_duplicate:
            return candidate
    return None


def create_article_hash(title, url):
    value = f"{canonicalize_url(url)}|{normalize_title(title)}"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


# ----------------------------------------------------------------------
# Independence / syndication
# ----------------------------------------------------------------------
@dataclass
class IndependenceAssessment:
    independent_publishers: int
    syndicated_publishers: int
    publisher_families: list[str]
    duplicate_pairs: list[dict]
    notes: list[str]

    def as_dict(self) -> dict:
        return {
            "independent_publishers": self.independent_publishers,
            "syndicated_publishers": self.syndicated_publishers,
            "publisher_families": self.publisher_families,
            "duplicate_pairs": self.duplicate_pairs,
            "notes": self.notes,
        }


def assess_independence(articles: list[dict], aggregator_domains: set[str] | None = None) -> IndependenceAssessment:
    """Count *independent* publishers among a set of supporting articles.

    A publisher family (``bbc.com``/``bbc.co.uk``) counts once.  Aggregators
    (Google News, MSN, Yahoo…) are excluded from the independent count because
    they do not add confirmation.  Articles whose text duplicates an earlier one
    are recorded as syndication rather than corroboration.
    """
    aggregators = aggregator_domains or set()
    families: dict[str, dict] = {}
    syndicated: list[str] = []
    pairs: list[dict] = []

    ordered = sorted(
        articles,
        key=lambda a: (
            _parse_datetime(a.get("published_at"))
            or datetime.max.replace(tzinfo=timezone.utc)
        ),
    )

    for article in ordered:
        domain = publisher_domain(article.get("url"), article.get("publisher_domain"))
        if not domain:
            continue
        if is_aggregator(domain, aggregators):
            pairs.append(
                {
                    "url": article.get("url"),
                    "publisher": domain,
                    "type": "aggregator",
                    "note": "Aggregator page, not independent reporting.",
                }
            )
            continue

        family = publisher_family(domain)
        if family in families:
            continue  # same newsroom publishing twice is not a new confirmation

        duplicate_of = None
        for accepted_article in families.values():
            if compare_articles(article, accepted_article).is_duplicate:
                duplicate_of = accepted_article
                break

        if duplicate_of is not None:
            syndicated.append(family)
            pairs.append(
                {
                    "url": article.get("url"),
                    "publisher": domain,
                    "type": "syndicated",
                    "syndication_of": publisher_domain(
                        duplicate_of.get("url"), duplicate_of.get("publisher_domain")
                    ),
                    "note": "Near-identical text already published elsewhere.",
                }
            )
            continue

        families[family] = article

    notes = []
    if syndicated:
        notes.append(
            f"{len(syndicated)} publisher(s) republished near-identical text and were "
            "not counted as independent confirmation."
        )
    if not families:
        notes.append("No independent publisher identified for this event.")

    return IndependenceAssessment(
        independent_publishers=len(families),
        syndicated_publishers=len(syndicated),
        publisher_families=sorted(families),
        duplicate_pairs=pairs,
        notes=notes,
    )
