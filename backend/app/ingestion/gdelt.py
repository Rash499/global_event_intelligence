import httpx
from datetime import datetime, timezone

async def fetch_gdelt(max_records: int = 50):
    url = "https://api.gdeltproject.org/api/v2/doc/doc"
    params = {
        "query": "sourcelang:english",
        "mode": "artlist",
        "format": "json",
        "maxrecords": min(max_records, 250),
        "sort": "datedesc",
    }
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        r = await client.get(url, params=params)
        r.raise_for_status()
        data = r.json()
    results = []
    for item in data.get("articles", []):
        results.append({
            "title": item.get("title") or "Untitled",
            "url": item.get("url"),
            "source": item.get("domain"),
            "published_at": item.get("seendate"),
            "description": item.get("title") or "",
        })
    return [x for x in results if x["url"]]
