# Data sources, access cost, and license posture

All current default-path sources are free to access and require no paid API or service. Public access does **not** mean content may be republished without conditions: source-specific terms still apply. The app stores source links and limited metadata/headlines, identifies providers, and does not claim a blanket redistribution license for publisher content.

| Source | Free / key posture | Current status | License/terms posture |
| --- | --- | --- | --- |
| RSS catalog (BBC, NPR, Guardian, UN News, ReliefWeb) | Free feed access; no app key | Default feeds | Publisher terms apply; retain attribution and source URL; no full-text redistribution claim. |
| State-affiliated RSS (Al Jazeera, DW, France 24, NHK World) | Free feed access; no app key | Opt-in only: set `RSS_INCLUDE_STATE_AFFILIATED=true` | State affiliation is labelled per source; publisher terms apply. |
| GDELT | Free; no key | Existing provider | Public project data; verify GDELT terms for downstream republication. |
| Google News RSS | Free feed access; no key | Existing provider | Publisher/source terms apply; headlines are linked, not licensed as app-owned content. |
| USGS earthquakes | Free; no key | Existing structured provider | USGS public data; retain attribution and observation context. |
| NASA EONET | Free; no key | Existing structured provider | NASA open data terms; source identifiers/links are retained. |
| GDACS | Free public API; no app key | Existing structured provider | Follow the provider's API terms and attribution guidance. |
| WHO Disease Outbreak News | Free public feed; no key | Existing structured provider | WHO publication terms apply; retain the original source reference. |
| ReliefWeb | Free API access, requires a configured app name | Existing provider; not ready until configured | ReliefWeb API terms and attribution apply. |
| NASA FIRMS | Free account key required | Optional and off unless configured | NASA FIRMS terms apply; detections are observations, not confirmed fires. |
| CAP feeds | Free, but an operator must configure one or more feed URLs | Existing provider; no default list | Individual feed publishers' terms apply. |
| ACLED | Account/license credentials; not a free default feed | Existing provider, disabled by default | Licensed terms; never enabled by default. |

## Phase-8 additions (registered providers)

The integrations below were deferred by the earlier execution because
endpoint reachability could not be verified from a network-restricted
sandbox. They have since been implemented along exactly the revisit
path named there — published schemas, offline fixtures, `unverified`
until a real collection succeeds. Live reachability is still not
claimed from development environments; the Providers page shows the
honest status.

| Source | Free / key posture | Current status | License/terms posture |
| --- | --- | --- | --- |
| UCDP GED conflict events | Data free; API requires a **free access token** (registration) | Registered, **off by default**, `not_configured` until `UCDP_ACCESS_TOKEN` is set | UCDP terms apply; research dataset, cite Uppsala Conflict Data Program. Feeds conflict history and the country-risk conflict-history floor |
| UNHCR population statistics | Free; no key | Registered, enabled, `unverified` live | UNHCR data terms; annual statistics stored as country-level displacement context, not incidents |
| HDX HAPI | Free with a self-declared app identifier | **Not integrated** — UNHCR's keyless API covers the displacement need with fewer moving parts; HAPI remains a documented alternative | HDX terms would apply |
| OFAC Consolidated List | Free public download; no key | Registered, enabled, `unverified` live | US Treasury public list; only per-country entry **counts** are stored — the list is not republished |
| US State Dept travel advisories | Free public RSS; no key | Registered, enabled, `unverified` live | US government assessment, labelled as such wherever shown; Level 3/4 advisories floor the country instability index |
| Polymarket (Gamma API) | Free; no key; read-only | Registered, **off by default** (opt-in context signal) | Market prices are participants' prices, stored with `is_our_prediction: false`; never presented as this platform's prediction |

Open-source GPS/GNSS interference feeds were likewise not added: no
free, stable, attributable public source could be verified. The system
does not infer jamming from unrelated event data.
