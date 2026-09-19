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

                image_url = None
                media_items = entry.get("media_content", [])
                if media_items:
                    image_url = media_items[0].get("url")
                if not image_url:
                    thumbnails = entry.get("media_thumbnail", [])
                    if thumbnails:
                        image_url = thumbnails[0].get("url")
                if not image_url:
                    enclosures = entry.get("enclosures", [])
                    image_url = next(
                        (
                            item.get("href")
                            for item in enclosures
                            if item.get("type", "").startswith("image/")
                        ),
                        None,
                    )

                results.append({
                    "title": entry.get("title", "Untitled"),
                    "url": link,
                    "source": source,
                    "published_at": entry.get("published", ""),
                    "description": entry.get("summary", ""),
                    "image_url": image_url,
                })
        except Exception:
            continue
    return results
