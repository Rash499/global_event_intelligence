"""User engagement endpoints: likes and comments on events."""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..database.db import get_connection

router = APIRouter(prefix="/api")

MAX_COMMENT_LENGTH = 2000
DEFAULT_AUTHOR = "Guest analyst"


class LikeRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=120)


class CommentRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=120)
    body: str = Field(min_length=1, max_length=MAX_COMMENT_LENGTH)
    author: str | None = Field(default=None, max_length=80)


def _require_event(conn, event_id: int) -> None:
    row = conn.execute(
        "SELECT id FROM events WHERE id = ?",
        (event_id,),
    ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Event not found")


def _like_count(conn, event_id: int) -> int:
    return conn.execute(
        "SELECT COUNT(*) AS count FROM event_likes WHERE event_id = ?",
        (event_id,),
    ).fetchone()["count"]


def _comment_count(conn, event_id: int) -> int:
    return conn.execute(
        "SELECT COUNT(*) AS count FROM event_comments WHERE event_id = ?",
        (event_id,),
    ).fetchone()["count"]


def _user_liked(conn, event_id: int, user_id: str | None) -> bool:
    if not user_id:
        return False

    row = conn.execute(
        """
        SELECT 1
        FROM event_likes
        WHERE event_id = ? AND user_id = ?
        """,
        (event_id, user_id),
    ).fetchone()

    return bool(row)


def _serialize_comment(row, user_id: str | None) -> dict:
    comment = dict(row)
    comment["own"] = comment.get("user_id") == user_id
    return comment


def _comments(conn, event_id: int, user_id: str | None = None) -> list[dict]:
    rows = conn.execute(
        """
        SELECT id, event_id, user_id, author, body, created_at
        FROM event_comments
        WHERE event_id = ?
        ORDER BY datetime(created_at) ASC, id ASC
        """,
        (event_id,),
    ).fetchall()

    return [_serialize_comment(row, user_id) for row in rows]



@router.get("/interactions/summary")
def interaction_summary(
    event_ids: str = Query(..., description="Comma separated event ids"),
    user_id: str | None = Query(None, max_length=120),
):
    """Bulk like/comment counts so long event lists render in one request."""

    ids = []

    for value in event_ids.split(","):
        value = value.strip()

        if not value:
            continue

        try:
            ids.append(int(value))
        except ValueError:
            continue

    ids = ids[:500]

    if not ids:
        return {"events": {}}

    conn = get_connection()

    try:
        placeholders = ",".join("?" for _ in ids)

        like_rows = conn.execute(
            f"""
            SELECT event_id, COUNT(*) AS count
            FROM event_likes
            WHERE event_id IN ({placeholders})
            GROUP BY event_id
            """,
            ids,
        ).fetchall()

        comment_rows = conn.execute(
            f"""
            SELECT event_id, COUNT(*) AS count
            FROM event_comments
            WHERE event_id IN ({placeholders})
            GROUP BY event_id
            """,
            ids,
        ).fetchall()

        liked_ids = set()

        if user_id:
            liked_rows = conn.execute(
                f"""
                SELECT event_id
                FROM event_likes
                WHERE user_id = ? AND event_id IN ({placeholders})
                """,
                [user_id, *ids],
            ).fetchall()

            liked_ids = {row["event_id"] for row in liked_rows}

        like_counts = {row["event_id"]: row["count"] for row in like_rows}
        comment_counts = {row["event_id"]: row["count"] for row in comment_rows}

        return {
            "events": {
                str(event_id): {
                    "like_count": like_counts.get(event_id, 0),
                    "comment_count": comment_counts.get(event_id, 0),
                    "liked": event_id in liked_ids,
                }
                for event_id in ids
            }
        }

    finally:
        conn.close()


@router.get("/events/{event_id}/interactions")
def event_interactions(
    event_id: int,
    user_id: str | None = Query(None, max_length=120),
):
    conn = get_connection()

    try:
        _require_event(conn, event_id)

        return {
            "event_id": event_id,
            "like_count": _like_count(conn, event_id),
            "comment_count": _comment_count(conn, event_id),
            "liked": _user_liked(conn, event_id, user_id),
            "comments": _comments(conn, event_id, user_id),
        }

    finally:
        conn.close()


@router.post("/events/{event_id}/like")
def toggle_like(event_id: int, payload: LikeRequest):
    conn = get_connection()

    try:
        _require_event(conn, event_id)

        existing = conn.execute(
            """
            SELECT 1
            FROM event_likes
            WHERE event_id = ? AND user_id = ?
            """,
            (event_id, payload.user_id),
        ).fetchone()

        if existing:
            conn.execute(
                """
                DELETE FROM event_likes
                WHERE event_id = ? AND user_id = ?
                """,
                (event_id, payload.user_id),
            )
            liked = False
        else:
            conn.execute(
                """
                INSERT INTO event_likes(event_id, user_id)
                VALUES (?, ?)
                """,
                (event_id, payload.user_id),
            )
            liked = True

        conn.commit()

        return {
            "event_id": event_id,
            "liked": liked,
            "like_count": _like_count(conn, event_id),
        }

    finally:
        conn.close()


@router.post("/events/{event_id}/comments")
def create_comment(event_id: int, payload: CommentRequest):
    body = payload.body.strip()

    if not body:
        raise HTTPException(status_code=422, detail="Comment cannot be empty")

    author = (payload.author or "").strip() or DEFAULT_AUTHOR

    conn = get_connection()

    try:
        _require_event(conn, event_id)

        cursor = conn.execute(
            """
            INSERT INTO event_comments(event_id, user_id, author, body)
            VALUES (?, ?, ?, ?)
            """,
            (event_id, payload.user_id, author, body),
        )

        conn.commit()

        row = conn.execute(
            """
            SELECT id, event_id, user_id, author, body, created_at
            FROM event_comments
            WHERE id = ?
            """,
            (cursor.lastrowid,),
        ).fetchone()

        return {
            "comment": _serialize_comment(row, payload.user_id),
            "comment_count": _comment_count(conn, event_id),
        }

    finally:
        conn.close()


@router.delete("/events/{event_id}/comments/{comment_id}")
def delete_comment(
    event_id: int,
    comment_id: int,
    user_id: str = Query(..., min_length=1, max_length=120),
):
    conn = get_connection()

    try:
        _require_event(conn, event_id)

        row = conn.execute(
            """
            SELECT user_id
            FROM event_comments
            WHERE id = ? AND event_id = ?
            """,
            (comment_id, event_id),
        ).fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Comment not found")

        if row["user_id"] != user_id:
            raise HTTPException(
                status_code=403,
                detail="You can only delete your own comments",
            )

        conn.execute("DELETE FROM event_comments WHERE id = ?", (comment_id,))
        conn.commit()

        return {
            "deleted": True,
            "comment_id": comment_id,
            "comment_count": _comment_count(conn, event_id),
        }

    finally:
        conn.close()
