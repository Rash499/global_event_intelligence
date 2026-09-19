import os
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "events.db"

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS articles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        url TEXT UNIQUE NOT NULL,
        source TEXT,
        published_at TEXT,
        description TEXT,
        image_url TEXT,
        content_hash TEXT
    );

    CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        summary TEXT,
        category TEXT NOT NULL,
        country TEXT,
        country_code TEXT,
        latitude REAL,
        longitude REAL,
        importance INTEGER DEFAULT 5,
        confidence REAL DEFAULT 0.5,
        event_time TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS event_articles (
        event_id INTEGER NOT NULL,
        article_id INTEGER NOT NULL,
        PRIMARY KEY(event_id, article_id)
    );
    """)

    article_columns = {
        row[1]
        for row in conn.execute("PRAGMA table_info(articles)").fetchall()
    }
    if "image_url" not in article_columns:
        conn.execute("ALTER TABLE articles ADD COLUMN image_url TEXT")

    conn.commit()
    conn.close()
