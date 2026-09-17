import os
import httpx


X_SEARCH_URL = "https://api.x.com/2/tweets/search/recent"


async def fetch_x(max_records: int = 50):
    bearer_token = os.getenv("X_BEARER_TOKEN")

    if not bearer_token:
        print("[X] X_BEARER_TOKEN not configured. Skipping.")
        return []

    headers = {
        "Authorization": f"Bearer {bearer_token}",
        "User-Agent": "GlobalEventIntelligence/1.0",
    }

    params = {
        "query": (
            "(earthquake OR flood OR wildfire OR "
            "war OR conflict OR disaster OR "
            "government OR election OR economy) "
            "-is:retweet lang:en"
        ),
        "max_results": min(max_records, 100),
        "tweet.fields": "created_at,author_id,lang",
    }

    async with httpx.AsyncClient(
        timeout=20,
        follow_redirects=True,
    ) as client:

        response = await client.get(
            X_SEARCH_URL,
            headers=headers,
            params=params,
        )

        response.raise_for_status()

        data = response.json()

    results = []

    for post in data.get("data", []):
        post_id = post.get("id")

        if not post_id:
            continue

        text = post.get("text", "").strip()

        if not text:
            continue

        results.append({
            "title": text[:200],
            "url": (
                f"https://x.com/i/web/status/"
                f"{post_id}"
            ),
            "source": "X",
            "published_at": post.get(
                "created_at",
                "",
            ),
            "description": text,
        })

    return results