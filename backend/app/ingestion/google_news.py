import feedparser
import httpx
from urllib.parse import quote_plus

GOOGLE_NEWS_QUERIES = {
    "Global": "world news",
    "Conflicts": "war OR conflict OR ceasefire",
    "Disasters": "earthquake OR flood OR wildfire OR hurricane",
    "Economy": "economy OR inflation OR recession",
    "Technology": "technology OR artificial intelligence",
    "Science": "science OR space OR climate",
    "Health": "health OR disease OR pandemic",
}

GOOGLE_NEWS_URL = "https://news.google.com/rss/search"

async def fetch_google_news(max_per_query: int = 20):
    results = []
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        for label, query in GOOGLE_NEWS_QUERIES.items():
            try:
                response = await client.get(
                    GOOGLE_NEWS_URL,
                    params={
                        "q": query,
                        "hl": "en-US",
                        "gl": "US",
                        "ceid": "US:en",
                    },
                    headers={"User-Agent": "GlobalEventIntelligence/1.0"},
                )
                response.raise_for_status()
                feed = feedparser.parse(response.text)

                for entry in feed.entries[:max_per_query]:
                    link = entry.get("link")
                    if not link:
                        continue

                    source_name = entry.get("source", {}).get("title") if isinstance(entry.get("source"), dict) else None
                    results.append(
                        {
                            "title": entry.get("title", "Untitled"),
                            "url": link,
                            "source": f"Google News: {source_name or label}",
                            "published_at": entry.get("published", ""),
                            "description": entry.get("summary", ""),
                            "image_url": None,
                        }
                    )
            except Exception:
                continue
    return results
