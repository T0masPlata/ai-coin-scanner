"""Local state: one SQLite file. Everything the upload sends is read from here."""
import json
import os
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS scans (
  scan_id TEXT PRIMARY KEY, ts TEXT NOT NULL, params TEXT NOT NULL,
  uploaded_at TEXT, upload_result TEXT);
CREATE TABLE IF NOT EXISTS coins (
  scan_id TEXT NOT NULL, mint TEXT NOT NULL, symbol TEXT, pair TEXT, metrics TEXT NOT NULL,
  PRIMARY KEY (scan_id, mint));
CREATE TABLE IF NOT EXISTS rugchecks (
  scan_id TEXT NOT NULL, mint TEXT NOT NULL, data TEXT NOT NULL, ts TEXT NOT NULL,
  PRIMARY KEY (scan_id, mint));
CREATE TABLE IF NOT EXISTS rugcache (
  mint TEXT PRIMARY KEY, data TEXT NOT NULL, fetched_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS scores (
  scan_id TEXT NOT NULL, mint TEXT NOT NULL, score INTEGER NOT NULL, verdict TEXT NOT NULL,
  reasons TEXT NOT NULL, rubric_version TEXT NOT NULL, model_name TEXT NOT NULL,
  baseline INTEGER NOT NULL, flag TEXT, ts TEXT NOT NULL,
  PRIMARY KEY (scan_id, mint));
"""


def default_path():
    base = os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(base, "vostuk", "scanner.db")


def connect(path=None):
    path = path or os.environ.get("VOSTUK_SCANNER_DB") or default_path()
    if path != ":memory:":
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    conn = sqlite3.connect(path, timeout=15)
    conn.row_factory = sqlite3.Row
    if path != ":memory:":
        conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    return conn


def loads(s):
    return json.loads(s) if s else None
