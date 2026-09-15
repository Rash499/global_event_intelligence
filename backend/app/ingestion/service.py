import hashlib
import sqlite3
from datetime import datetime, timezone
from .gdelt import fetch_gdelt
from .rss import fetch_rss
from ..database.db import get_connection
from ..processing.analyzer import analyze
from ..ai.ollama import analyze_with_ollama
from ..config import settings

async def ingest():
    articles = await fetch_gdelt(settings.gdelt_max_records)
    articles += await fetch_rss()

    conn = get_connection()
    inserted = 0
    events = 0

    for article in articles:
        url = article.get("url")
        if not url:
            continue
        content_hash = hashlib.sha256(
            f"{article.get('title','')}|{url}".encode()
        ).hexdigest()

        try:
            cur = conn.execute(
                """INSERT INTO articles(title,url,source,published_at,description,content_hash)
                   VALUES(?,?,?,?,?,?)""",
                (
                    article.get("title", "Untitled"),
                    url,
                    article.get("source", "Unknown"),
                    article.get("published_at", ""),
                    article.get("description", ""),
                    content_hash,
                ),
            )
            article_id = cur.lastrowid
            inserted += 1
        except sqlite3.IntegrityError:
            continue

        result = analyze(article.get("title", ""), article.get("description", ""))
        ai = await analyze_with_ollama(article.get("title", ""), article.get("description", ""))
        if ai:
            result["category"] = ai.get("category", result["category"])
            result["country"] = ai.get("country") or result["country"]
            result["importance"] = max(1, min(10, int(ai.get("importance", result["importance"]))))
            result["summary"] = ai.get("summary") or result["summary"]
            result["confidence"] = 0.75

        cur = conn.execute(
            """INSERT INTO events(title,summary,category,country,country_code,latitude,longitude,
               importance,confidence,event_time)
               VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (
                result["title"], result["summary"], result["category"],
                result["country"], result["country_code"], result["latitude"], result["longitude"],
                result["importance"], result["confidence"], result["event_time"],
            ),
        )
        event_id = cur.lastrowid
        conn.execute(
            "INSERT INTO event_articles(event_id,article_id) VALUES(?,?)",
            (event_id, article_id),
        )
        events += 1

    conn.commit()
    conn.close()
    return {"articles_seen": len(articles), "articles_inserted": inserted, "events_created": events}
