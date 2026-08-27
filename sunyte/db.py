import os
import sqlite3

PROJECT_ROOT = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
DB_PATH = os.path.join(PROJECT_ROOT, "sunyte.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    started_at TEXT,
    ended_at TEXT,
    cwd TEXT,
    status TEXT DEFAULT 'running',
    total_cost_usd REAL DEFAULT 0.0,
    total_input_tokens INTEGER DEFAULT 0,
    total_output_tokens INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    timestamp TEXT,
    hook_event TEXT,
    tool_name TEXT,
    tool_input TEXT,
    tool_output TEXT,
    decision TEXT DEFAULT 'allow',
    cost_usd REAL DEFAULT 0,
    prev_hash TEXT DEFAULT '',
    row_hash TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS flags (
    flag_id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    event_id INTEGER,
    rule_name TEXT,
    severity TEXT,
    message TEXT,
    timestamp TEXT
);
"""


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")  # allows concurrent hook calls to not lock each other out
    conn.executescript(SCHEMA)
    # migration-safe: add columns to pre-existing databases that predate cost tracking
    try:
        conn.execute("ALTER TABLE events ADD COLUMN cost_usd REAL DEFAULT 0")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # column already exists
    for col, coltype in [("total_cost_usd", "REAL DEFAULT 0.0"),
                          ("total_input_tokens", "INTEGER DEFAULT 0"),
                          ("total_output_tokens", "INTEGER DEFAULT 0")]:
        try:
            conn.execute(f"ALTER TABLE sessions ADD COLUMN {col} {coltype}")
            conn.commit()
        except sqlite3.OperationalError:
            pass  # column already exists
    for col, coltype in [("prev_hash", "TEXT DEFAULT ''"), ("row_hash", "TEXT DEFAULT ''")]:
        try:
            conn.execute(f"ALTER TABLE events ADD COLUMN {col} {coltype}")
            conn.commit()
        except sqlite3.OperationalError:
            pass  # column already exists
    return conn


def get_last_event_hash(conn) -> str:
    row = conn.execute("SELECT row_hash FROM events ORDER BY event_id DESC LIMIT 1").fetchone()
    return row[0] if row and row[0] else ""
