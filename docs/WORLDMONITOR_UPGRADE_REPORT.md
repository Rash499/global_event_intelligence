# WorldMonitor-inspired upgrades — delivery report

Date: 2026-11-28. All implementation is original to this repository; no WorldMonitor code or phrasing was copied. `LICENSE` was not changed.

## Branch and commits

Arena fixes this session to the active branch `arena/75d68d5c-global-event-intelligence`; the requested `feature/worldmonitor-inspired-upgrades` branch could not be created without violating the session's branch restriction. Changes and commits are on the active branch.

The work was committed in phase-labelled commits. Phase 1 source-affiliation opt-in received a small follow-up commit after Phase 8 documentation clarified default-feed posture.

## Delivered

- **Phases 1–2:** locally curated publisher metadata catalog; undeclared sources stay distinct from tier 4; source risk and state-affiliation labels; state-affiliated RSS feeds excluded unless opted in; stored source credibility separate from importance; separate 0–100 `importance_score` with centralized weights and deterministic scoring.
- **Phase 3:** 15-minute recency gate, importance/severity floors, source-tier/non-keyword classifier gate, story-phase suppression, 30-minute per-event suppression, 60-second global cooldown with critical-over-high override, and stored per-account sensitivity with Alerts controls.
- **Phase 4:** retained coverage-adequacy suppression; daily regional samples and Welford summaries split by weekday/month; 90-day retention, ten-sample minimum, z-score severity bands and stored sample IDs; title/entity term spike checks. Migration 011 persists the explicit z-score field.
- **Phase 5:** country-instability indicator with the requested 40/60 and component weights, local static baseline table, capped boosts from already registered provider keys, full component/coverage response and UI warning. Future conflict-history/travel-advisory floors remain empty until their providers exist.
- **Phase 6:** separate 1° spatial convergence route and MapView panel, nearest-country anchor labels, score/severity, and system alerts that still pass alert gates. The existing `/api/convergence` remains a country/taxonomy-group temporal comparison (current vs preceding equal window and critical-event detection); spatial convergence instead counts distinct categories per grid cell over 24h.
- **Phase 7:** schedule-aware provider freshness, empty-run streak detection, `/api/intelligence-gaps`, and visibility in Providers/System and country coverage detail.
- **Phase 9:** SQLite digest snapshots with cache age, ingestion invalidation and scheduler prewarming; OpenAPI-to-TypeScript generation; Ruff and Biome; installed pre-push hook; Playwright login/map/alerts smoke and axe checks; separate CI E2E job.
- **Phase 10:** README and architecture updates plus scoring, alert-gate, anomaly, convergence, country-score, data-source and engineering documentation.

Database migrations now run through **011**. Existing backup-before-destructive-migration behavior remains unchanged.

## Deferred / not built

The requested new **UCDP, UNHCR/HDX HAPI, OFAC, State Department travel-advisory and Polymarket providers were not registered**. This sandbox only permits outbound access to GitHub, npm and PyPI hosts, so official endpoint availability/response formats, current cadence, key requirements and redistribution terms could not be checked. Rather than ship speculative adapters or claim verified coverage, the official-source review and fixtures are a documented follow-up in `docs/data-sources.md`. Free public GPS/GNSS jamming data was also skipped because a stable attributable source could not be verified. Existing providers remain available, including the existing key-gated/off-by-default FIRMS and ACLED adapters.

Playwright configuration and tests were added and test discovery succeeds, but browser execution was **not run locally** because Chromium is not installed in this sandbox and browser downloads are outside the allowed host list. CI installs Chromium and runs the E2E job separately. E2E API/browser traffic is local to the test services; provider tests remain mocked/offline.

## Verification

- Baseline reported by the request: 252 backend tests passed, with one DNS-dependent security test expected to be hermeticized. A baseline run in this sandbox after installing dependencies observed 253 passed.
- Final backend: **282 passed** (`python -m pytest -q`); Ruff: **passed**.
- Frontend: **129 passed** across 19 Vitest files; TypeScript build/check passed; production build passed; Biome lint passed.
- OpenAPI type generation completed for 63 paths. Playwright test discovery lists one smoke test; full browser execution deferred to CI as noted above.
- The public-URL security test now mocks `socket.getaddrinfo`; provider adapters in tests use mocked responses and no external provider network calls.

## Follow-ups

1. Verify each Phase 8 source from official documentation and legal terms, then add deterministic parser fixtures before enabling any provider.
2. Run the separate Playwright CI job and address any accessibility violations or environment-specific selectors it reveals.
3. Review the static country baseline values before relying on them outside descriptive exploration; the score is explicitly coverage-limited and makes no predictive claim.
