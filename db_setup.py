import sqlite3
from pathlib import Path

# Store the database in the same folder as this file.
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "findralgo.db"


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password TEXT NOT NULL,
    reputation INTEGER NOT NULL DEFAULT 50
        CHECK (reputation BETWEEN 0 AND 100),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS items (
    item_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    item_type TEXT NOT NULL
        CHECK (item_type IN ('lost', 'found')),
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL,
    location TEXT NOT NULL,
    reported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status TEXT NOT NULL DEFAULT 'open'
        CHECK (status IN ('open', 'returned')),
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS matches (
    match_id INTEGER PRIMARY KEY AUTOINCREMENT,
    lost_item_id INTEGER NOT NULL,
    found_item_id INTEGER NOT NULL,
    score REAL NOT NULL DEFAULT 0,
    reason TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'approved', 'rejected')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (lost_item_id, found_item_id),
    FOREIGN KEY (lost_item_id) REFERENCES items(item_id),
    FOREIGN KEY (found_item_id) REFERENCES items(item_id)
);

CREATE TABLE IF NOT EXISTS claims (
    claim_id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id INTEGER NOT NULL,
    claimant_id INTEGER NOT NULL,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'approved', 'rejected')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (match_id) REFERENCES matches(match_id),
    FOREIGN KEY (claimant_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS reputation_log (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    "change" INTEGER NOT NULL,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE INDEX IF NOT EXISTS idx_items_type_status
ON items(item_type, status);

CREATE INDEX IF NOT EXISTS idx_items_user
ON items(user_id);

CREATE INDEX IF NOT EXISTS idx_matches_lost
ON matches(lost_item_id);

CREATE INDEX IF NOT EXISTS idx_matches_found
ON matches(found_item_id);

CREATE INDEX IF NOT EXISTS idx_claims_match_status
ON claims(match_id, status);

CREATE INDEX IF NOT EXISTS idx_claims_claimant
ON claims(claimant_id);

CREATE INDEX IF NOT EXISTS idx_reputation_user
ON reputation_log(user_id);
"""


def get_connection():
    """Create and return a SQLite database connection."""
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Create all database tables and indexes."""
    conn = get_connection()
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
    print("FindrAlgo database initialized successfully.")
    print(f"Database location: {DB_PATH}")
