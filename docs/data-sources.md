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

## Requested additions not included in this change

UCDP, UNHCR/HDX HAPI, OFAC downloads, State Department advisories, and Polymarket context are **not registered providers** in this implementation. This execution environment only permits outbound requests to GitHub/npm/PyPI hosts, so public endpoint reachability, current response formats, update cadence, redistribution terms, and for some sources registration/key requirements could not be verified. To avoid shipping speculative endpoints or implying verified coverage, these integrations are deferred. Revisit each from its official documentation, write offline fixtures from published schemas, and keep any key-dependent adapter disabled until configured.

Open-source GPS/GNSS interference feeds were likewise not added: no free, stable, attributable public source could be verified from the available network. The system does not infer jamming from unrelated event data.
