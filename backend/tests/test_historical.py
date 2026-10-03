import sqlite3
from datetime import datetime, timedelta, timezone

from app.intelligence.historical import (
    build_timeline,
    detect_changes,
    event_momentum,
    historical_stats,
    source_diversity,
)
from app.rag.query import detect_time_range


def make_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE events (
            id INTEGER PRIMARY KEY, title TEXT, summary TEXT, category TEXT,
            country TEXT, country_code TEXT, latitude REAL, longitude REAL,
            importance INTEGER, confidence REAL, article_count INTEGER,
            corroboration_level TEXT, event_time TEXT, created_at TEXT
        );
        CREATE TABLE articles (
            id INTEGER PRIMARY KEY, title TEXT, url TEXT, source TEXT,
            published_at TEXT, description TEXT
        );
        CREATE TABLE event_articles (event_id INTEGER, article_id INTEGER);
    """)
    return conn


def test_event_timeline_is_chronological_and_uses_articles():
    conn = make_db()
    conn.execute("INSERT INTO events VALUES (1,'Flood','','environment','Sri Lanka','LK',7.8,80.7,7,.8,2,'corroborated','2026-09-01T08:00:00Z','2026-09-01T08:00:00Z')")
    conn.executemany("INSERT INTO articles VALUES (?,?,?,?,?,?)", [
        (1, "Initial flood report", "https://a.example/1", "A", "2026-09-01T08:00:00Z", "Flooding reported."),
        (2, "Updated flood report", "https://b.example/2", "B", "2026-09-01T10:00:00Z", "Flooding expanded."),
    ])
    conn.executemany("INSERT INTO event_articles VALUES (?,?)", [(1,1),(1,2)])
    timeline = build_timeline(conn, 1)
    assert [x["article_id"] for x in timeline] == [1,2]
    assert timeline[0]["event_id"] == 1


def test_source_diversity_counts_domains_not_articles():
    conn = make_db()
    conn.execute("INSERT INTO events VALUES (1,'Event','','security','X','XX',None,None,7,.8,3,'single','2026-09-01T08:00:00Z','2026-09-01T08:00:00Z')")
    conn.executemany("INSERT INTO articles VALUES (?,?,?,?,?,?)", [
        (1,"A","https://same.example/a","Same","2026-09-01T08:00:00Z",""),
        (2,"B","https://same.example/b","Same","2026-09-01T09:00:00Z",""),
        (3,"C","https://other.example/c","Other","2026-09-01T10:00:00Z",""),
    ])
    conn.executemany("INSERT INTO event_articles VALUES (?,?)", [(1,1),(1,2),(1,3)])
    diversity = source_diversity(conn,1)
    assert diversity["total_articles"] == 3
    assert diversity["unique_domains"] == 2


def test_conflicting_claims_are_preserved():
    conn = make_db()
    conn.execute("INSERT INTO events VALUES (1,'Incident','','security','X','XX',None,None,8,.8,2,'single','2026-09-01T08:00:00Z','2026-09-01T08:00:00Z')")
    conn.executemany("INSERT INTO articles VALUES (?,?,?,?,?,?)", [
        (1,"Report: 10 casualties","https://a.example/a","A","2026-09-01T08:00:00Z","10 people were killed."),
        (2,"Report: 24 casualties","https://b.example/b","B","24 people were killed."),
    ])
    conn.executemany("INSERT INTO event_articles VALUES (?,?)", [(1,1),(1,2)])
    changes, claims = detect_changes(conn,1)
    assert any(x["type"] == "conflicting_information" for x in changes)
    assert {x["value"] for x in claims} == {10,24}


def test_momentum_requires_observable_history():
    conn = make_db()
    conn.execute("INSERT INTO events VALUES (1,'Event','','security','X','XX',None,None,7,.8,1,'single','2026-09-01T08:00:00Z','2026-09-01T08:00:00Z')")
    conn.execute("INSERT INTO articles VALUES (?,?,?,?,?,?)",(1,"Only report","https://a.example/a","A","2026-09-01T08:00:00Z",""))
    conn.execute("INSERT INTO event_articles VALUES (?,?)",(1,1))
    assert event_momentum(conn,1)["state"] == "insufficient_data"


def test_temporal_parser_supports_explicit_ranges():
    start, end, label = detect_time_range("events between 2026-09-01 and 2026-09-15")
    assert start.startswith("2026-09-01")
    assert end.startswith("2026-09-16")
    assert "between" in label
