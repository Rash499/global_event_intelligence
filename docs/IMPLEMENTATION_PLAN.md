# Implementation plan (audit-driven)

## Audit findings
1. `backend/app/intelligence/historical.py` did not compile (a duplicated block was pasted mid-function) — every backend test failed at collection.
2. `DATABASE_URL` is documented/configured but ignored: `db.py` hardcodes `backend/data/events.db`.
3. No migration mechanism (`CREATE TABLE IF NOT EXISTS` + ad-hoc `ALTER TABLE`).
4. Collectors swallow every exception (`except Exception: continue`) so provider failures are invisible.
5. Collectors are called sequentially from one function; no scheduler, no retries, no health, no history.
6. `documents/sources` provenance is thin: no canonical URL, publisher, language, first/last seen.
7. Confidence uses `source_count` (article links) where `unique_source_count` semantics are claimed; syndication is not modelled.
8. Importance is mostly synthetic (`geographic_impact=7 if country_code`, `source_coverage=4`, …).
9. Location = country centroid presented with full precision.
10. `discover_image_url` follows redirects to arbitrary hosts → SSRF.
11. `/api/events/seed` writes fabricated events with no environment gate.
12. Weather/retention docs disagree with configuration (7 days vs 365 vs min 30).
13. Many analytics queries run per row inside Python loops (N+1).
14. No CI, no lint config, README is stale relative to actual features.

## Delivery order
Phase 1 reliability (config, migrations, normalization, dedup/syndication, provider adapters, scheduler, assessment, geolocation, SSRF, logging/health, tests, CI, docs).
Phase 2 intelligence (taxonomy, hybrid classification, clustering, relationships, lifecycle, USGS/ReliefWeb/WHO/FIRMS/CAP, country intel, anomalies, entities).
Phase 3 workspace (navigation, overview, map layers, event investigation, search, alert center, provider health, accessibility).
Phase 4 reports/exports + history.
