"""Small, locally maintained source metadata catalog.

Unknown publishers deliberately remain ``undeclared``; absence from this
curation is not evidence that a publisher belongs to the lowest tier.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

CATALOG_PATH = Path(__file__).resolve().parents[1] / "data" / "source_catalog.json"

@lru_cache(maxsize=1)
def load_source_catalog() -> dict[str, dict]:
    payload = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    return {item["domain"].lower(): item for item in payload.get("sources", [])}

def source_metadata(domain: str | None, publisher: str | None = None) -> dict:
    """Resolve exact or parent-domain metadata; state-affiliated status is explicit."""
    candidate = (domain or "").strip().lower().strip(".")
    if not candidate and publisher:
        candidate = urlparse(publisher if "://" in publisher else f"https://{publisher}").hostname or ""
    catalog = load_source_catalog()
    match = catalog.get(candidate)
    if match is None:
        parts = candidate.split(".")
        for offset in range(1, max(1, len(parts) - 1)):
            match = catalog.get(".".join(parts[offset:]))
            if match:
                break
    if match is None:
        return {"source_tier": "undeclared", "propaganda_risk": "medium", "state_affiliated": False, "source_region": None}
    return {
        "source_tier": match["tier"],
        "propaganda_risk": match["propaganda_risk"],
        "state_affiliated": bool(match["state_affiliated"]),
        "source_region": match.get("region"),
    }

def credibility_score(sources: list[dict]) -> int | None:
    """Score provenance quality and independent corroboration (not truth)."""
    if not sources:
        return None
    tier_base = {1: 88, 2: 74, 3: 60, 4: 42, "undeclared": 55}
    risk_penalty = {"low": 0, "medium": 9, "high": 22}
    values = []
    independent = set()
    for source in sources:
        tier = source.get("source_tier", "undeclared")
        if isinstance(tier, str) and tier.isdigit():
            tier = int(tier)
        values.append(tier_base.get(tier, tier_base["undeclared"]) - risk_penalty.get(source.get("propaganda_risk"), 9))
        if source.get("is_independent", True):
            domain = source.get("publisher_domain") or source.get("publisher") or source.get("source")
            if domain:
                independent.add(str(domain).lower())
    corroboration_bonus = min(18, max(0, len(independent) - 1) * 6)
    return max(0, min(100, round(sum(values) / len(values) + corroboration_bonus)))
