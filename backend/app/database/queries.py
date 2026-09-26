"""Shared SQL helpers for reading events with their media and engagement data."""

EVENT_COLUMNS = """
    e.*,
    (
        SELECT a.image_url
        FROM event_articles ea
        JOIN articles a ON a.id = ea.article_id
        WHERE ea.event_id = e.id
          AND a.image_url IS NOT NULL
          AND TRIM(a.image_url) != ''
        ORDER BY a.id
        LIMIT 1
    ) AS image_url,
    (
        SELECT COUNT(*)
        FROM event_likes l
        WHERE l.event_id = e.id
    ) AS like_count,
    (
        SELECT COUNT(*)
        FROM event_comments c
        WHERE c.event_id = e.id
    ) AS comment_count
"""


def select_events(
    conn,
    where_clause="",
    params=(),
    order_clause="e.event_time DESC",
    limit=None,
    user_id=None,
):
    """Return events with image, like and comment metadata.

    When ``user_id`` is provided every row also reports whether that user
    already liked the event, so the UI can render the correct button state.
    """

    columns = EVENT_COLUMNS

    if user_id:
        columns += """,
    CASE
        WHEN EXISTS (
            SELECT 1
            FROM event_likes l
            WHERE l.event_id = e.id AND l.user_id = ?
        )
        THEN 1
        ELSE 0
    END AS liked
"""

    sql = f"SELECT {columns} FROM events e"

    # The user_id placeholder lives inside the SELECT list, so it must be
    # bound before the WHERE/LIMIT placeholders.
    query_params = ([user_id] if user_id else []) + list(params)

    if where_clause:
        sql += f" WHERE {where_clause}"

    if order_clause:
        sql += f" ORDER BY {order_clause}"

    if limit is not None:
        sql += " LIMIT ?"
        query_params.append(limit)

    rows = conn.execute(sql, query_params).fetchall()

    results = []

    for row in rows:
        event = dict(row)

        if "liked" in event:
            event["liked"] = bool(event["liked"])

        results.append(event)

    return results


def select_event(conn, event_id, user_id=None):
    """Return a single event with media + engagement data, or ``None``."""

    events = select_events(
        conn,
        where_clause="e.id = ?",
        params=(event_id,),
        limit=1,
        user_id=user_id,
    )

    return events[0] if events else None
