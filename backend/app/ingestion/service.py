import hashlib
import sqlite3

from .gdelt import fetch_gdelt
from .rss import fetch_rss

from ..database.db import get_connection
from ..processing.analyzer import analyze
from ..ai.ollama import analyze_with_ollama
from ..config import settings


async def ingest():
    """
    Collect news from GDELT and RSS, analyze the articles using
    the deterministic analyzer + Ollama, and store events in SQLite.

    GDELT is treated as an optional source. If GDELT fails
    (for example, HTTP 429 rate limiting), RSS processing
    continues normally.
    """

    # --------------------------------------------------
    # 1. Collect articles
    # --------------------------------------------------

    articles = []

    # --------------------------------------------------
    # 1A. Try GDELT
    # --------------------------------------------------

    try:

        print("[GDELT] Fetching articles...")

        gdelt_articles = await fetch_gdelt(
            settings.gdelt_max_records
        )

        articles.extend(gdelt_articles)

        print(
            f"[GDELT] Fetched {len(gdelt_articles)} articles"
        )

    except Exception as exc:

        print(
            f"[GDELT ERROR] {exc}"
        )

        print(
            "[GDELT] Skipping GDELT and continuing with RSS..."
        )

    # --------------------------------------------------
    # 1B. Get RSS news
    # --------------------------------------------------

    try:

        print("[RSS] Fetching articles...")

        rss_articles = await fetch_rss()

        articles.extend(rss_articles)

        print(
            f"[RSS] Fetched {len(rss_articles)} articles"
        )

    except Exception as exc:

        print(
            f"[RSS ERROR] {exc}"
        )

    # --------------------------------------------------
    # 2. Open database
    # --------------------------------------------------

    conn = get_connection()

    inserted = 0
    events = 0
    ai_analyzed = 0
    ai_failed = 0

    # --------------------------------------------------
    # 3. Process each article
    # --------------------------------------------------

    for article in articles:

        url = article.get("url")

        if not url:
            continue

        title = article.get(
            "title",
            "Untitled"
        )

        description = article.get(
            "description",
            ""
        )

        source = article.get(
            "source",
            "Unknown"
        )

        published_at = article.get(
            "published_at",
            ""
        )

        # --------------------------------------------------
        # 4. Generate article hash
        # --------------------------------------------------

        content_hash = hashlib.sha256(
            f"{title}|{url}".encode()
        ).hexdigest()

        # --------------------------------------------------
        # 5. Insert article
        # --------------------------------------------------

        try:

            cur = conn.execute(
                """
                INSERT INTO articles
                (
                    title,
                    url,
                    source,
                    published_at,
                    description,
                    content_hash
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    title,
                    url,
                    source,
                    published_at,
                    description,
                    content_hash,
                ),
            )

            article_id = cur.lastrowid

            inserted += 1

        except sqlite3.IntegrityError:

            # Article already exists
            continue

        # --------------------------------------------------
        # 6. Deterministic analysis
        # --------------------------------------------------

        result = analyze(
            title,
            description
        )

        # --------------------------------------------------
        # 7. Ollama AI analysis
        # --------------------------------------------------

        try:

            print(
                f"[AI] Analyzing: {title}"
            )

            ai = await analyze_with_ollama(
                title=title,
                description=description,
                source=source,
                url=url,
            )

        except Exception as exc:

            print(
                f"[AI ERROR] {exc}"
            )

            ai = None

            ai_failed += 1

        # --------------------------------------------------
        # 8. Merge AI result
        # --------------------------------------------------

        if ai:

            ai_analyzed += 1

            # ----------------------------------------------
            # Event title
            # ----------------------------------------------

            result["title"] = (
                ai.get("event_title")
                or result.get("title")
                or title
            )

            # ----------------------------------------------
            # Summary
            # ----------------------------------------------

            result["summary"] = (
                ai.get("summary")
                or result.get("summary")
                or description
                or title
            )

            # ----------------------------------------------
            # Category
            # ----------------------------------------------

            result["category"] = (
                ai.get("category")
                or result.get("category")
                or "other"
            )

            # ----------------------------------------------
            # Country
            # ----------------------------------------------

            result["country"] = (
                ai.get("country")
                or result.get("country")
            )

            # ----------------------------------------------
            # Country code
            # ----------------------------------------------

            result["country_code"] = (
                ai.get("country_code")
                or result.get("country_code")
            )

            # ----------------------------------------------
            # Location
            # ----------------------------------------------

            result["location"] = (
                ai.get("location")
                or result.get("location")
            )

            # ----------------------------------------------
            # Latitude
            # ----------------------------------------------

            if ai.get("latitude") is not None:

                result["latitude"] = ai.get(
                    "latitude"
                )

            # ----------------------------------------------
            # Longitude
            # ----------------------------------------------

            if ai.get("longitude") is not None:

                result["longitude"] = ai.get(
                    "longitude"
                )

            # ----------------------------------------------
            # Importance
            # ----------------------------------------------

            try:

                importance = int(
                    ai.get(
                        "importance",
                        result.get(
                            "importance",
                            1
                        ),
                    )
                )

                result["importance"] = max(
                    1,
                    min(
                        10,
                        importance
                    )
                )

            except (
                TypeError,
                ValueError
            ):

                pass

            # ----------------------------------------------
            # Confidence
            # ----------------------------------------------

            try:

                confidence = float(
                    ai.get(
                        "confidence",
                        result.get(
                            "confidence",
                            0
                        ),
                    )
                )

                result["confidence"] = max(
                    0.0,
                    min(
                        1.0,
                        confidence
                    )
                )

            except (
                TypeError,
                ValueError
            ):

                pass

        # --------------------------------------------------
        # 9. Store event
        # --------------------------------------------------

        cur = conn.execute(
            """
            INSERT INTO events
            (
                title,
                summary,
                category,
                country,
                country_code,
                latitude,
                longitude,
                importance,
                confidence,
                event_time
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result.get(
                    "title",
                    title
                ),

                result.get(
                    "summary",
                    description
                ),

                result.get(
                    "category",
                    "other"
                ),

                result.get(
                    "country"
                ),

                result.get(
                    "country_code"
                ),

                result.get(
                    "latitude"
                ),

                result.get(
                    "longitude"
                ),

                result.get(
                    "importance",
                    1
                ),

                result.get(
                    "confidence",
                    0
                ),

                result.get(
                    "event_time"
                ),
            ),
        )

        event_id = cur.lastrowid

        # --------------------------------------------------
        # 10. Connect article → event
        # --------------------------------------------------

        conn.execute(
            """
            INSERT INTO event_articles
            (
                event_id,
                article_id
            )
            VALUES (?, ?)
            """,
            (
                event_id,
                article_id,
            ),
        )

        events += 1

    # --------------------------------------------------
    # 11. Commit changes
    # --------------------------------------------------

    conn.commit()

    conn.close()

    # --------------------------------------------------
    # 12. Return ingestion statistics
    # --------------------------------------------------

    return {
        "articles_seen": len(articles),
        "articles_inserted": inserted,
        "events_created": events,
        "ai_analyzed": ai_analyzed,
        "ai_failed": ai_failed,
    }