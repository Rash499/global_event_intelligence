# Delivery report

Scope: improve the existing Global Event Intelligence Platform in place. No
rebuild, no fabricated intelligence, no new infrastructure.

| Area | Before | After |
| --- | --- | --- |
| Backend tests | 0 passing (one file did not compile) | **228 passing** |
| Migrations | `CREATE TABLE IF NOT EXISTS` + ad-hoc `ALTER` | 6 numbered, reversible-by-backup migrations with version check |
| Provider health | errors swallowed | per-provider status, retries, circuit breaker, run history |
| Severity / confidence / priority | one synthetic "importance" | three separate, explainable scores with stored components |
| Location | country centroid presented as a precise point | per-event `location_precision`; country-only events never plotted |
| Frontend tests | 71 | **104** |
| Typecheck / build | clean | clean (0 TS errors, build succeeds) |
| Docs vs config | README said 7-day retention, config said 365 | reconciled, one source of truth |

---

## 1. Audit findings (and what was done)

1. **`intelligence/historical.py` did not compile** — a duplicated block was
   pasted mid-function; every backend test failed at collection. Fixed.
2. **`DATABASE_URL` was ignored** — `db.py` hardcoded a path. Now parsed into
   `settings.db_path`; only `sqlite:///` is accepted, with an explicit error.
3. **No migration mechanism** — replaced with a versioned migration runner,
   timestamped backup before destructive steps, and `verify_migrations()`
   surfaced by `/api/system/status`.
4. **Collectors swallowed every exception** — every provider now records an
   outcome, and one failing provider cannot block the others.
5. **Sequential, untracked collection** — registry + per-provider intervals +
   scheduler with in-flight guards, plus a `collection_runs` history table.
6. **Thin provenance** — articles now carry canonical URL, publisher, domain,
   provider, provider record id, language, first/last seen, extraction status,
   syndication link and independence flag.
7. **Confidence used article count** — replaced by an evidence model that counts
   *independent* publishers and penalises syndicated copies and single sourcing.
8. **Importance was synthetic** (`geographic_impact = 7 if country_code`) —
   replaced by severity from stated impact/magnitude, confidence from evidence,
   and priority from severity × confidence × corroboration × lifecycle.
9. **Country centroid sold as a point** — geolocation now returns precision;
   the map endpoint and UI refuse to pin anything below region precision.
10. **SSRF in image discovery** — `safe_fetch` blocks private, loopback, CGNAT,
    documentation, ULA, link-local and IPv4-mapped ranges, validates redirects
    and content types.
11. **`/api/events/seed` wrote fabricated events with no gate** — now requires
    `DEMO_DATA_ENABLED=true` **and** `{"confirm": true}`, refuses in production,
    and the settings validator rejects `production + demo_data_enabled`.
12. **Docs/config disagreement on retention** — one setting
    (`HISTORICAL_RETENTION_DAYS`, default 365, floor 30) now drives both the
    purge job and the docs.
13. **N+1 analytics queries** — aggregate SQL in one pass for dashboard,
    country and history endpoints.
14. **No CI, stale README** — `.github/workflows/ci.yml` added; README rewritten
    against the actual code.

---

## 2. Schema changes

Migration 002 (`articles`): `canonical_url, publisher, publisher_domain,
provider, provider_record_id, language, author, description_hash,
extraction_status, first_seen_at, last_seen_at, reporting_type, syndication_of,
event_time, event_time_precision, raw_metadata, is_independent,
source_record_at, updated_at`.

Migration 003 (`events`): `subcategory, taxonomy_version,
classification_method, classification_confidence, severity, severity_label,
severity_components, confidence_components, confidence_explanation,
priority_score, priority_label, location_precision, location_text,
geocoding_source, geocoding_confidence, event_state, event_state_updated_at,
occurred_at, occurred_at_precision, observed_at, updated_at,
assessment_updated_at, independent_source_count, syndicated_source_count,
ai_assessment, ai_assessment_at, ai_model, escalation_trend, provider_keys,
data_sources, is_structured_observation`.

Migration 004: `providers`, `collection_runs`.
Migration 005: `event_relationships`, `event_locations`, `event_timeline`,
`entities` (+ aliases, mentions, relationships), `alert_rules`, `alerts`,
`saved_searches`, `watchlists`, `anomalies`, `reports`.
Migration 006: foreign keys rebuilt with `ON DELETE CASCADE`.

Indexes cover the keyset-pagination and filter columns (`occurred_at`,
`severity`, `priority_score`, `confidence`, `country_code`, `category`,
`event_state`, `provider_keys`).

---

## 3. API changes

Preserved: every previous route and response field still resolves. Event list
responses gained a pagination envelope (`items`, `next_cursor`, `has_more`,
`count`, `filters`); the legacy `limit` parameter still works and
`/api/events/history` and `/api/events/latest` keep returning plain arrays, so
existing frontend code kept working during the migration.

Added:

- `GET /api/map/events` — precision-aware layer, per-country shading, coverage counts
- `GET /api/dashboard/overview`
- `GET /api/events` (cursor pagination; sorts `recent|severity|priority|confidence`)
- `GET /api/events/{id}` (sources, timeline, relationships, entities, precision)
- `GET /api/providers`, `GET /api/providers/history`
- `GET /api/countries`, `GET /api/countries/{code}/risk`
- `GET /api/anomalies`, `POST /api/anomalies/{id}/dismiss`
- `GET /api/entities`, `GET /api/entities/{id}`
- `GET /api/alerts`, `POST /api/alerts/{id}/status`, `GET|POST|DELETE /api/alert-rules`
- `GET|POST|DELETE /api/saved-searches`, `GET /api/search`
- `POST /api/reports`, `GET /api/reports`, `GET /api/reports/{id}/export?format=csv|html`
- `GET /api/system/status`, `GET /api/ingestion/status`
- `POST /api/ingestion/run?providers=a,b` (subset collection)

---

## 4. Data sources and access requirements

| Provider key | Credential | Status |
| --- | --- | --- |
| `rss` | none | implemented + tested |
| `gdelt` | none | implemented + tested (parsing, paging) |
| `google_news` | none | implemented + tested |
| `usgs` | none | implemented + tested (structured observation path) |
| `reliefweb` | none | implemented + tested |
| `who` | none | implemented + tested |
| `firms` | `FIRMS_MAP_KEY` | implemented; reports `not_configured` until a key exists |
| `cap` | feed URL list | implemented; needs external feed configuration |
| `acled` | licensed account | implemented; blocked on licensing, disabled by default |
| Ollama | local model | optional; lazy import, platform fully functional without it |

Health states: `healthy` (≥1 success, no current error), `idle` (configured,
never run), `degraded` (recovered after retries, partial failure, or stale),
`unavailable` (current error), `not_configured`, `disabled`.

---

## 5. UI/UX changes

- Navigation regrouped into Monitor / Analyse / Deliver / Operate, with a
  collapsible mobile menu and an unread-alert counter.
- `Ctrl/Cmd-K` command palette over `/api/search` plus section jumps.
- Overview driven entirely by stored counts, with explicit empty states.
- Map with precision modes and a side panel that states what is *not* plotted.
- Event investigation page: three separate scores, each expandable into its
  component breakdown; occurrence / observation / publication / ingestion times
  labelled with precision; sources split independent vs syndicated.
- Country indicators keep the API's coverage caveat instead of presenting a
  composite risk score.
- Provider health page with real statuses, errors and run history, plus a
  per-provider "Collect now".
- Reports with server-rendered CSV/HTML export; system page with schema,
  integrity, scheduler and security posture.
- Accessibility: semantic landmarks, labelled controls, `aria-current`,
  `aria-pressed`, focus-visible rings, `aria-live` status regions, axe checks in
  tests, and `prefers-reduced-motion` handling.
- Responsive at 1400 / 1180 / 860 / 560 px; no horizontal scrolling of the page.
- Performance: every new view is lazily loaded (5–10 kB per view), `three` and
  `globe.gl` are split into their own chunks, and lists are cursor-paginated
  rather than downloaded whole.

---

## 6. Security changes

- SSRF-safe outbound fetching (blocked networks, redirect re-validation,
  content-type allowlist, size caps).
- Demo seed route gated behind config + explicit confirmation, refused in
  production, and rejected at settings-validation time when combined with
  `ENVIRONMENT=production`.
- Fixed-window rate limiting on `/api` with stricter write buckets
  (`ingestion/run` 6/min, `events/seed` 2/min), `Retry-After` and
  `X-RateLimit-Remaining` headers, and `/api/health` exempt.
- Error responses normalised: no tracebacks, file paths or exception text
  reaching the client.
- CORS restricted to configured origins; wildcard rejected in production.
- Security headers on every response (`nosniff`, `DENY`, `no-referrer`).
- No secrets in logs; API keys read from `.env` only and never returned.

---

## 7. Quality gates

```
backend:   python -m pytest -q            → 228 passed
frontend:  npx tsc -b                     → clean
frontend:  npx vitest run                 → 104 passed (11 files)
frontend:  npm run build                  → success
migrations: verified via /api/system/status (schema current, integrity ok)
endpoints:  all 13 checked routes return 200 against a live server
```

CI (`.github/workflows/ci.yml`) runs the backend suite and the frontend
typecheck + tests + production build on every push and pull request.

---

## 8. Known limitations

- **Screenshots are not included in this delivery.** The sandbox has no browser
  binary and the Playwright Chromium download is blocked, so no genuine UI
  screenshot could be captured. Capturing them from the running app locally is
  the only honest way to satisfy that item; the instructions are:
  `npm run dev` in `frontend/`, `uvicorn app.main:app --port 8000` in `backend/`,
  then screenshot Overview, Map, Events, Investigation, Providers and System.
- PDF export is not implemented (HTML export prints to PDF from the browser).
  The UI says this rather than offering a button that does something else.
- Alert delivery is in-app only; no email or webhook transport yet.
- Country indicators are descriptive statistics over collected reporting, not a
  forecast, and are not comparable across countries with different coverage.
- Entity extraction is deterministic and limited to its gazetteer.
- Rate limiting is per-process; a multi-worker deployment would need a shared
  store. The stated deployment target is single-node SQLite.
- Anomaly detection needs ≥3 observed and ≥3 baseline events per dimension, so
  a sparse database cannot produce anomalies — a coverage limit, stated in the
  UI, not a claim of normality.
- ACLED remains blocked on licensing and is never enabled by default.
- Live collection against the real upstream services was not exercised in this
  environment (no outbound access to those hosts); provider parsing and
  lifecycle are covered by fixture-based tests.

---

## 9. Next steps

1. Capture the UI screenshots locally with the app running.
2. Add a PDF renderer (headless Chromium or WeasyPrint) to `/api/reports/{id}/export`.
3. Add webhook/email alert delivery with a signed payload and retry policy.
4. Expand the entity gazetteer and add co-occurrence weighting.
5. Backtest the anomaly baseline against a longer history once enough data exists.
