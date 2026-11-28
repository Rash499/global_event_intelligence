# Country instability indicator

`GET /api/countries/{code}/risk` returns the composite alongside the legacy per-dimension event tables and explicit coverage. Formula:

- `eventScore = 0.25 × unrest + 0.30 × conflict + 0.20 × security + 0.25 × information`
- `combined = clamp(0.40 × baseline + 0.60 × eventScore + capped provider boosts + applicable floors, 0, 100)`

Each component is derived from stored events/article pressure and shown in the response. The baseline is a curated static table in `backend/app/data/country_baselines.json`; countries without an explicit entry use the file's labelled static default. Capped additive context boosts are tied to stored provider keys: USGS earthquakes +8, FIRMS wildfires +8, GDACS/EONET disasters +8, ReliefWeb humanitarian +6, WHO outbreaks +6. The API returns boost scores and observation counts. Conflict-history and travel-advisory floors are empty until those providers are registered.

Levels: Critical 81–100, High 66–80, Elevated 51–65, Normal 31–50, Low 0–30. Values are clamped to 0–100. Coverage reports article/publisher counts and missing inputs; sparse or absent collection is never represented as evidence of calm. This is an indicator over ingested data, not a forecast or a complete safety assessment.
