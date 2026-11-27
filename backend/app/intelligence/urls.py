"""URL canonicalisation and publisher identification.

Article URLs arrive from three providers and are untrusted input.  Two reports
of the same story usually differ only in tracking parameters, mobile/AMP
prefixes or trailing slashes, which is why canonicalisation runs before any
duplicate check.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

# Query parameters that never change which article is served.
TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "utm_id", "utm_name", "utm_cid", "utm_reader", "utm_referrer",
    "gclid", "dclid", "fbclid", "msclkid", "mc_cid", "mc_eid", "igshid",
    "ref", "ref_src", "referrer", "cmpid", "ocid", "ns_mchannel",
    "ns_campaign", "ns_source", "at_medium", "at_campaign", "ito",
    "smid", "share", "spm", "yptr", "guccounter", "soc_src", "soc_trk",
    "output", "site", "rss", "feed",
}

# Domains that republish other publishers' reporting.
KNOWN_AGGREGATORS = {
    "news.google.com", "news.yahoo.com", "yahoo.com", "msn.com",
    "flipboard.com", "smartnews.com", "newsnow.co.uk", "newsbreak.com",
    "ground.news", "apple.news", "buzzfeednews.com", "inkl.com",
    "newspaper.li", "feedspot.com", "prnewswire.com", "businesswire.com",
    "globenewswire.com", "einpresswire.com", "marketwatch.com",
}

# Publisher families: several domains can belong to one newsroom, which for
# independence purposes is *one* source.
PUBLISHER_FAMILIES = {
    "bbc": {"bbc.co.uk", "bbc.com", "bbc.in"},
    "cnn": {"cnn.com", "cnnphilippines.com", "edition.cnn.com"},
    "aljazeera": {"aljazeera.com", "aljazeera.net"},
    "dw": {"dw.com", "dw.de"},
    "france24": {"france24.com", "france24.com"},
    "npr": {"npr.org", "npr.com"},
    "reuters": {"reuters.com", "reutersagency.com", "trust.org"},
    "apnews": {"apnews.com", "ap.org"},
    "afp": {"afp.com", "afpforum.com"},
    "nytimes": {"nytimes.com", "nytimespost.com"},
    "guardian": {"theguardian.com", "guardian.co.uk"},
    "washingtonpost": {"washingtonpost.com"},
    "nhk": {"nhk.or.jp", "www3.nhk.or.jp"},
    "abc": {"abc.net.au", "abcnews.go.com"},
    "cbs": {"cbsnews.com"},
    "nbc": {"nbcnews.com"},
    "fox": {"foxnews.com"},
    "skynews": {"news.sky.com", "skynews.com", "sky.com"},
    "euronews": {"euronews.com"},
    "rt": {"rt.com", "rttv.com"},
    "scmp": {"scmp.com"},
    "thehindu": {"thehindu.com", "thehindubusinessline.com"},
    "toi": {"timesofindia.indiatimes.com", "indiatimes.com"},
    "straitstimes": {"straitstimes.com"},
    "japantimes": {"japantimes.co.jp"},
    "independent": {"independent.co.uk", "independent.co.in"},
    "telegraph": {"telegraph.co.uk"},
    "economist": {"economist.com"},
    "bloomberg": {"bloomberg.com", "bloombergquint.com"},
    "wsj": {"wsj.com"},
    "ft": {"ft.com"},
    "forbes": {"forbes.com"},
    "politico": {"politico.com", "politico.eu"},
    "axios": {"axios.com"},
    "time": {"time.com"},
    "newsweek": {"newsweek.com"},
    "irishTimes": {"irishtimes.com"},
    "cbc": {"cbc.ca"},
    "globalnews": {"globalnews.ca"},
    "cbcradio": {"cbc.ca"},
    "lemonde": {"lemonde.fr"},
    "lesechos": {"lesechos.fr"},
    "spiegel": {"spiegel.de"},
    "zeit": {"zeit.de"},
    "faz": {"faz.net"},
    "welt": {"welt.de"},
    "elpais": {"elpais.com"},
    "clarin": {"clarin.com"},
    "folha": {"folha.uol.com.br"},
    "globo": {"globo.com", "g1.globo.com"},
    "kickerdaily": {"kickerdaily.com"},
    "xinhua": {"xinhuanet.com", "news.cn"},
    "cgtn": {"cgtn.com"},
    "globaltimes": {"globaltimes.cn"},
    "tass": {"tass.com"},
    "sputnik": {"sputniknews.com", "sputnikglobe.com"},
    "kyivpost": {"kyivpost.com"},
    "kyivindependent": {"kyivindependent.com"},
    "haaretz": {"haaretz.com", "haaretz.co.il"},
    "jpost": {"jpost.com"},
    "timesofisrael": {"timesofisrael.com"},
    "almonitor": {"al-monitor.com"},
    "arabnews": {"arabnews.com"},
    "gulfnews": {"gulfnews.com"},
    "khaleejtimes": {"khaleejtimes.com"},
    "thenational": {"thenationalnews.com"},
    "irishexaminer": {"irishexaminer.com"},
    "rte": {"rte.ie"},
    "svt": {"svt.se"},
    "nrk": {"nrk.no"},
    "yle": {"yle.fi"},
    "dr": {"dr.dk"},
    "polsat": {"polsatnews.pl"},
    "interfax": {"interfax.com", "interfax.ru"},
    "kyodonews": {"kyodonews.net"},
    "asahi": {"asahi.com"},
    "yomiuri": {"yomiuri.co.jp"},
    "mainichi": {"mainichi.jp"},
    "scmp2": {"scmp.com"},
    "bangkokpost": {"bangkokpost.com"},
    "jakartapost": {"thejakartapost.com"},
    "rappler": {"rappler.com"},
    "inquirer": {"inquirer.net"},
    "channelnewsasia": {"channelnewsasia.com"},
    "malaymail": {"malaymail.com"},
    "thestar": {"thestar.com.my"},
    "dawn": {"dawn.com"},
    "thedailystar": {"thedailystar.net"},
    "kathmandupost": {"kathmandupost.com"},
    "tamilmirror": {"tamilmirror.lk"},
    "dailymirror": {"dailymirror.lk"},
    "adaderana": {"adaderana.lk"},
    "colombopage": {"colombopage.com"},
}

# Second-level suffixes that must not be treated as the registrable name.
_MULTI_PART_SUFFIXES = {
    "co.uk", "org.uk", "ac.uk", "gov.uk", "com.au", "net.au", "org.au",
    "co.jp", "or.jp", "ne.jp", "co.in", "net.in", "org.in", "com.br",
    "com.cn", "com.sg", "com.my", "co.za", "com.ng", "co.ke", "com.pk",
    "com.tr", "com.ar", "com.mx", "co.nz", "com.hk", "com.tw", "co.id",
}

AMP_SUFFIXES = ("/amp", "/amp/", ".amp", "/amp.html")


def registrable_domain(host: str) -> str:
    """Return the registrable part of a hostname (``news.bbc.co.uk`` -> ``bbc.co.uk``)."""
    host = (host or "").lower().strip().strip(".")
    if not host:
        return ""
    labels = host.split(".")
    if len(labels) <= 2:
        return host
    suffix2 = ".".join(labels[-2:])
    if suffix2 in _MULTI_PART_SUFFIXES and len(labels) >= 3:
        return ".".join(labels[-3:])
    return suffix2


def publisher_domain(url: str | None, fallback: str | None = None) -> str:
    """Best-effort publisher host with ``www.`` and AMP noise removed."""
    host = ""
    try:
        host = (urlparse(str(url or "")).hostname or "").lower()
    except ValueError:
        host = ""
    if not host:
        host = str(fallback or "").lower().strip()
    if host.startswith("www."):
        host = host[4:]
    return host


def publisher_family(domain: str) -> str:
    """Group domains that belong to the same newsroom."""
    domain = (domain or "").lower()
    if not domain:
        return "unknown"
    for family, domains in PUBLISHER_FAMILIES.items():
        if domain in domains:
            return family
    registrable = registrable_domain(domain)
    return registrable or domain


def is_aggregator(domain: str, extra: set[str] | None = None) -> bool:
    domain = (domain or "").lower()
    if not domain:
        return False
    aggregators = KNOWN_AGGREGATORS | (extra or set())
    if domain in aggregators:
        return True
    registrable = registrable_domain(domain)
    return any(
        registrable == registrable_domain(item) for item in aggregators if item
    )


def canonicalize_url(url: str | None) -> str:
    """Canonical form used for exact-duplicate detection.

    * lowercases scheme/host, drops ``www.``, default ports and fragments;
    * strips tracking query parameters, keeps meaningful ones sorted;
    * removes trailing slashes and AMP variants.
    """
    raw = str(url or "").strip()
    if not raw:
        return ""

    try:
        parsed = urlparse(raw)
    except ValueError:
        return raw.lower()

    scheme = (parsed.scheme or "https").lower()
    if scheme not in {"http", "https"}:
        return raw

    host = (parsed.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if parsed.port and parsed.port not in (80, 443):
        host = f"{host}:{parsed.port}"

    path = parsed.path or "/"
    for suffix in AMP_SUFFIXES:
        if path.endswith(suffix):
            path = path[: -len(suffix)] or "/"
    path = re.sub(r"/{2,}", "/", path)
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")

    query_items = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in TRACKING_PARAMS and not key.lower().startswith("utm_")
    ]
    query = urlencode(sorted(query_items))

    return urlunparse((scheme, host, path, "", query, ""))


def url_domain_key(url: str | None) -> str:
    """Stable identity for a URL's publisher (used in duplicate grouping)."""
    return publisher_family(publisher_domain(url))


def extract_google_news_publisher(title: str, url: str) -> tuple[str, str]:
    """Split a Google News headline into (publisher, clean title).

    Google News entries look like ``"Headline text - Publisher Name"`` and the
    link is a ``news.google.com`` redirect. Treating Google as the publisher
    would double-count every article, so the real publisher is recovered from
    the title suffix and used for provenance.
    """
    clean_title = (title or "").strip()
    publisher = ""
    if " - " in clean_title:
        candidate_title, _, candidate_publisher = clean_title.rpartition(" - ")
        if 0 < len(candidate_publisher) <= 60 and len(candidate_title) > 10:
            clean_title = candidate_title.strip()
            publisher = candidate_publisher.strip()
    if not publisher:
        publisher = publisher_domain(url) or "Google News"
    return publisher, clean_title
