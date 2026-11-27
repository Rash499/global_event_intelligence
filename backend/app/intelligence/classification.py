"""Hybrid event classification.

Stage 1 is deliberately deterministic and cheap: keyword/rule scoring against the
versioned taxonomy.  Stage 2 uses the model **only** when it is enabled and the
deterministic pass is not confident enough, so a normal ingestion cycle never
depends on an LLM.

All entry points return the same dictionary shape:

.. code-block:: python

    {
      "category": "natural_disaster",
      "subcategory": "earthquake",
      "confidence": 0.82,
      "method": "deterministic",           # or "ai_assisted"
      "matched_terms": ["earthquake"],
      "taxonomy_version": "1.0",
      "needs_review": False,
    }
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from functools import lru_cache

from .taxonomy import (
    CATEGORY_KEYS,
    LEGACY_CATEGORY_MAP,
    TAXONOMY,
    TAXONOMY_VERSION,
    category_label,
    subcategory_label,
)

logger = logging.getLogger(__name__)

# Confidence assigned when nothing matched. Deliberately below the AI threshold
# but above "we know nothing": an unclassified event still carries provenance.
UNCLASSIFIED_CONFIDENCE = 0.30
# Deterministic scores are capped here; only a human/verified source should
# push classification certainty higher.
DETERMINISTIC_CEILING = 0.93


def _normalise_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", str(value or "").lower()).strip()


def _term_weight(term: str) -> float:
    """Multi-word phrases are stronger evidence than single tokens."""
    words = term.split()
    if len(words) >= 3:
        return 1.6
    if len(words) == 2:
        return 1.25
    return 1.0


@lru_cache(maxsize=2048)
def _term_pattern(term: str) -> re.Pattern[str]:
    """Word-boundary pattern for a taxonomy term.

    Plain substring matching is unusable here: ``"port"`` would match inside
    ``"reported"`` and turn a battle report into a maritime incident. Every
    term is matched as a whole phrase, with whitespace/hyphen tolerance.
    """
    words = [part.strip() for part in term.split() if part.strip()]
    if not words:
        return re.compile(r"(?!x)x")
    # Match inflections in both directions: the taxonomy may store "clashes"
    # while a headline says "clash", or store "protest" while the headline says
    # "protests". The final word is reduced to a stem and given a suffix class.
    last = words[-1]
    if len(last) > 4 and last.endswith("ies"):
        last = last[:-3] + "y"
    elif len(last) > 3 and last.endswith("es"):
        last = last[:-2]
    elif len(last) > 3 and last.endswith("s") and not last.endswith("ss"):
        last = last[:-1]
    parts = [re.escape(part) for part in words[:-1]] + [
        re.escape(last) + r"(?:s|es|ed|ing)?"
    ]
    body = r"[\s\-]+".join(parts)
    return re.compile(rf"(?<![a-z0-9]){body}(?![a-z0-9])")


def _matches(term: str, text: str) -> bool:
    if not term:
        return False
    return _term_pattern(term).search(text) is not None


@dataclass
class _Score:
    category: str
    subcategory: str
    score: float
    terms: list[str]


def _score_text(text: str) -> list[_Score]:
    results: list[_Score] = []

    for category, entry in TAXONOMY.items():
        if category == "other":
            continue
        matched: list[str] = []
        score = 0.0
        for term in entry["keywords"]:
            if _matches(term, text):
                matched.append(term)
                score += _term_weight(term)

        best_sub, best_sub_score, best_sub_terms = "unclassified", 0.0, []
        for sub_key, sub in entry["subcategories"].items():
            sub_hits = [t for t in sub["keywords"] if _matches(t, text)]
            sub_score = sum(_term_weight(t) for t in sub_hits)
            if sub_score > best_sub_score:
                best_sub, best_sub_score = sub_key, sub_score
                best_sub_terms = sub_hits

        if score > 0 or best_sub_score > 0:
            # Category keywords and subcategory phrases reinforce each other.
            combined = score + (best_sub_score * 0.5)
            results.append(
                _Score(
                    category=category,
                    subcategory=best_sub if best_sub_score > 0 else "unclassified",
                    score=combined,
                    terms=sorted(set(matched) | set(best_sub_terms)),
                )
            )

    results.sort(key=lambda r: (-r.score, CATEGORY_KEYS.index(r.category)))
    return results


def _confidence_from_score(best: float, second: float) -> float:
    """Map the winning score onto a confidence in [0, 1].

    A decisive winner (large gap to the runner-up) is trusted more than a tie,
    which keeps ambiguous headlines from being classified confidently.
    """
    strength = min(1.0, best / 4.0)  # saturating evidence strength
    margin = 0.0 if second <= 0 else max(0.0, min(1.0, (best - second) / max(best, 1e-6)))
    confidence = 0.42 + (0.38 * strength) + (0.20 * margin)
    return round(min(DETERMINISTIC_CEILING, confidence), 3)


def normalize_category(value: str | None) -> str:
    """Map any historical/AI supplied label onto a taxonomy category key."""
    if value is None:
        return "other"

    raw = str(value).strip().lower().replace("-", "_")
    raw = re.sub(r"\s+", "_", raw)
    if not raw:
        return "other"

    if raw in TAXONOMY:
        return raw
    if raw in LEGACY_CATEGORY_MAP:
        return LEGACY_CATEGORY_MAP[raw]

    # Fuzzy: look for a category key or a legacy alias inside the raw label.
    for key in TAXONOMY:
        if key != "other" and key in raw:
            return key
    for alias, target in LEGACY_CATEGORY_MAP.items():
        if alias in raw:
            return target

    # Finally, classify the free-text label itself.
    result = classify_article({"title": raw.replace("_", " ")})
    return result["category"]


def normalize_subcategory(category: str, value: str | None) -> str:
    entry = TAXONOMY.get(category)
    if not entry:
        return "unclassified"
    if not value:
        return "unclassified"
    raw = re.sub(r"[\s-]+", "_", str(value).strip().lower())
    if raw in entry["subcategories"]:
        return raw
    for key, sub in entry["subcategories"].items():
        if raw in sub["label"].lower().replace(" ", "_") or key in raw:
            return key
    return "unclassified"


def classify_article(article: dict) -> dict:
    """Deterministic classification of a normalised article."""
    title = str(article.get("title") or "")
    description = str(article.get("description") or article.get("summary") or "")
    text = _normalise_text(f"{title} {title} {description}")  # title weighted 2x

    scores = _score_text(text)
    if not scores or scores[0].score <= 0:
        return {
            "category": "other",
            "subcategory": "unclassified",
            "confidence": UNCLASSIFIED_CONFIDENCE,
            "method": "deterministic",
            "matched_terms": [],
            "taxonomy_version": TAXONOMY_VERSION,
            "needs_review": True,
            "category_label": category_label("other"),
            "subcategory_label": subcategory_label("other", "unclassified"),
        }

    best = scores[0]
    second = scores[1].score if len(scores) > 1 else 0.0
    confidence = _confidence_from_score(best.score, second)

    return {
        "category": best.category,
        "subcategory": best.subcategory,
        "confidence": confidence,
        "method": "deterministic",
        "matched_terms": best.terms[:8],
        "taxonomy_version": TAXONOMY_VERSION,
        "needs_review": confidence < 0.55,
        "category_label": category_label(best.category),
        "subcategory_label": subcategory_label(best.category, best.subcategory),
    }


def merge_ai_classification(deterministic: dict, ai_category: str | None, ai_confidence: float | None = None, ai_subcategory: str | None = None) -> dict:
    """Combine the AI suggestion with the rule-based result.

    The AI is only allowed to *refine* a result. It can raise confidence but not
    above the deterministic ceiling unless the model itself is very confident,
    and categories are always mapped back onto the versioned taxonomy.
    """
    category = normalize_category(ai_category) if ai_category else deterministic["category"]
    if category == "other" and deterministic["category"] != "other":
        category = deterministic["category"]

    subcategory = normalize_subcategory(category, ai_subcategory) if ai_subcategory else deterministic["subcategory"]
    if category != deterministic["category"]:
        subcategory = normalize_subcategory(category, ai_subcategory)

    ai_conf = max(0.0, min(1.0, float(ai_confidence))) if ai_confidence is not None else 0.6
    confidence = round(max(deterministic["confidence"], min(0.95, ai_conf)), 3)
    if category == deterministic["category"]:
        confidence = round(max(deterministic["confidence"], min(0.95, (ai_conf + deterministic["confidence"]) / 2 + 0.05)), 3)

    return {
        **deterministic,
        "category": category,
        "subcategory": subcategory,
        "confidence": confidence,
        "method": "ai_assisted",
        "needs_review": confidence < 0.55,
        "category_label": category_label(category),
        "subcategory_label": subcategory_label(category, subcategory),
    }

# ----------------------------------------------------------------------
# Backwards-compatible vocabulary exports
# ----------------------------------------------------------------------
# ``rag/query.py`` builds its natural-language category matcher from these two
# mappings. They are now *derived* from the versioned taxonomy so there is a
# single vocabulary, and legacy labels still resolve correctly.
KEYWORD_MAP: dict[str, list[str]] = {
    category: list(entry["keywords"]) + [
        term for sub in entry["subcategories"].values() for term in sub["keywords"]
    ]
    for category, entry in TAXONOMY.items()
    if category != "other"
}

CATEGORY_ALIASES: dict[str, str] = {
    **LEGACY_CATEGORY_MAP,
    **{category: category for category in TAXONOMY},
    **{
        entry["label"].lower(): category
        for category, entry in TAXONOMY.items()
    },
}
