# Scoring and source provenance

## Source catalog and credibility

`backend/app/data/source_catalog.json` is a small, versioned, local catalog. It records a publisher domain, tier, source-level propaganda-risk label, state-affiliation label, and region. Tier definitions are: 1 wire/official; 2 major outlet; 3 specialist, regional, or think-tank; 4 aggregator/blog. An unknown publisher is explicitly `undeclared` and is never silently promoted to tier 4. State-affiliated entries remain labelled in source details; the catalog does not add feeds to provider defaults.

Event credibility is stored separately from impact severity and importance. The v1 score starts from an average tier anchor (88, 74, 60, 42; undeclared 55), subtracts a source-risk penalty (0, 9, 22 for low, medium, high), and adds up to 18 points for independent publisher corroboration (6 per publisher after the first), clamped to 0–100. It is a statement about catalogued provenance and corroboration, **not a judgment about the truth of a report**. Catalog entries are a maintained heuristic, not an external certification.

## Importance ranking

`importance_score` is a separate 0–100 ranking field; legacy `importance` remains the existing 1–10 impact-oriented value. Current weights are centralized in `IMPORTANCE_CONFIG` (`backend/app/intelligence/importance.py`): source corroboration +2.5 per additional distinct publisher, capped at six publishers; entity corroboration +8 for at least two extracted entities; tier contributions +9/+6/+3/0, undeclared +0; +5 per keyword group; a 1.35 flashpoint interaction when flashpoint overlaps violence, military, or unrest; linear recency decay over 16 hours with a 0.5 floor; and a 0.35 multiplier for corporate/financial noise only when entity corroboration and a strong non-keyword classifier signal are both absent.

The calculation is descriptive prioritization over collected reports. It makes no predictive claim.
