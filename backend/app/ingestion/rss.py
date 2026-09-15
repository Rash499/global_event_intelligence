import feedparser
import httpx

DEFAULT_FEEDS = {
    "BBC": "https://feeds.bbci.co.uk/news/world/rss.xml",
    "NPR": "https://feeds.npr.org/1004/rss.xml",
    "Al Jazeera": "https://www.aljazeera.com/xml/rss/all.xml",
}

async def fetch_rss():
    results = []
    for source, url in DEFAULT_FEEDS.items():
        try:
            async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
                r = await client.get(url, headers={"User-Agent": "GlobalEventIntelligence/1.0"})
                r.raise_for_status()
            feed = feedparser.parse(r.text)
            for entry in feed.entries[:30]:
                link = entry.get("link")
                if not link:
                    continue
                results.append({
                    "title": entry.get("title", "Untitled"),
                    "url": link,
                    "source": source,
                    "published_at": entry.get("published", ""),
                    "description": entry.get("summary", ""),
                })
        except Exception:
            continue
    return results
