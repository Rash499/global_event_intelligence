import os
import base64
import httpx


REDDIT_TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
REDDIT_API_URL = "https://oauth.reddit.com"


async def get_reddit_access_token():
    client_id = os.getenv("REDDIT_CLIENT_ID")
    client_secret = os.getenv("REDDIT_CLIENT_SECRET")

    if not client_id or not client_secret:
        return None

    auth = base64.b64encode(
        f"{client_id}:{client_secret}".encode()
    ).decode()

    headers = {
        "Authorization": f"Basic {auth}",
        "User-Agent": "GlobalEventIntelligence/1.0",
    }

    data = {
        "grant_type": "client_credentials",
    }

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            REDDIT_TOKEN_URL,
            headers=headers,
            data=data,
        )

        response.raise_for_status()

        return response.json().get("access_token")


async def fetch_reddit(max_records: int = 50):
    token = await get_reddit_access_token()

    if not token:
        print("[REDDIT] Credentials not configured. Skipping.")
        return []

    subreddits = [
        "worldnews",
        "geopolitics",
        "technology",
        "science",
        "environment",
        "disasters",
    ]

    headers = {
        "Authorization": f"Bearer {token}",
        "User-Agent": "GlobalEventIntelligence/1.0",
    }

    results = []

    per_subreddit = max(1, max_records // len(subreddits))

    async with httpx.AsyncClient(
        timeout=20,
        follow_redirects=True,
    ) as client:

        for subreddit in subreddits:
            try:
                response = await client.get(
                    f"{REDDIT_API_URL}/r/{subreddit}/new",
                    headers=headers,
                    params={
                        "limit": min(per_subreddit, 100),
                    },
                )

                response.raise_for_status()

                data = response.json()

                children = (
                    data.get("data", {})
                    .get("children", [])
                )

                for child in children:
                    post = child.get("data", {})

                    post_id = post.get("id")

                    if not post_id:
                        continue

                    permalink = post.get("permalink")

                    if not permalink:
                        continue

                    url = (
                        "https://www.reddit.com"
                        + permalink
                    )

                    results.append({
                        "title": post.get(
                            "title",
                            "Untitled",
                        ),
                        "url": url,
                        "source": f"Reddit:r/{subreddit}",
                        "published_at": post.get(
                            "created_utc",
                            "",
                        ),
                        "description": post.get(
                            "selftext",
                            "",
                        )[:5000],
                    })

            except Exception as exc:
                print(
                    f"[REDDIT ERROR] r/{subreddit}: {exc}"
                )
                continue

    return results[:max_records]