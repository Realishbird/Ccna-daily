"""SQLite storage. One file, created on first start."""
import sqlite3
from contextlib import contextmanager

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS card_state (
    card_id       TEXT PRIMARY KEY,
    introduced_on TEXT NOT NULL,
    due           TEXT NOT NULL,
    interval_days REAL NOT NULL DEFAULT 0,
    ease          REAL NOT NULL DEFAULT 2.5,
    reps          INTEGER NOT NULL DEFAULT 0,
    lapses        INTEGER NOT NULL DEFAULT 0,
    last_review   TEXT
);
CREATE TABLE IF NOT EXISTS card_reviews (
    id        INTEGER PRIMARY KEY,
    card_id   TEXT NOT NULL,
    day       TEXT NOT NULL,
    at        TEXT NOT NULL,
    rating    INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS drill_problems (
    id        INTEGER PRIMARY KEY,
    day       TEXT NOT NULL,
    kind      TEXT NOT NULL,
    prompt    TEXT NOT NULL,
    answer    TEXT NOT NULL,
    issued_at TEXT NOT NULL,
    given     TEXT,
    correct   INTEGER,
    seconds   REAL
);
CREATE TABLE IF NOT EXISTS question_attempts (
    id          INTEGER PRIMARY KEY,
    question_id TEXT NOT NULL,
    day         TEXT NOT NULL,
    at          TEXT NOT NULL,
    correct     INTEGER NOT NULL,
    extra       INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS lab_attempts (
    id      INTEGER PRIMARY KEY,
    lab_id  TEXT NOT NULL,
    day     TEXT NOT NULL,
    at      TEXT NOT NULL,
    correct INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS checkins (
    day       TEXT PRIMARY KEY,
    sleep     REAL,
    exercise  INTEGER,
    water     INTEGER
);
CREATE TABLE IF NOT EXISTS completions (
    day TEXT PRIMARY KEY,
    at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reminders_sent (
    day  TEXT NOT NULL,
    slot TEXT NOT NULL,
    PRIMARY KEY (day, slot)
);
"""


def connect() -> sqlite3.Connection:
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init() -> None:
    with get() as conn:
        conn.executescript(SCHEMA)


@contextmanager
def get():
    conn = connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
