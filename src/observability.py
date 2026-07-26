import sqlite3
import os
from datetime import datetime
from contextlib import contextmanager

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "logs", "runs.db")


def _ensure_db_dir():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)


@contextmanager
def get_connection():
    _ensure_db_dir()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    """Creates tables if they don't exist. Safe to call every startup."""
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                query TEXT NOT NULL,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                final_status TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS steps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                step_name TEXT NOT NULL,
                status TEXT NOT NULL,
                latency_ms REAL,
                tokens_used INTEGER,
                cost_usd REAL DEFAULT 0,
                error TEXT,
                timestamp TEXT NOT NULL,
                FOREIGN KEY (run_id) REFERENCES runs (run_id)
            )
        """)


def log_run_start(run_id: str, query: str):
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO runs (run_id, query, started_at) VALUES (?, ?, ?)",
            (run_id, query, datetime.utcnow().isoformat())
        )


def log_step(run_id: str, step_name: str, status: str, latency_ms: float,
             tokens_used: int = 0, cost_usd: float = 0, error: str = None):
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO steps (run_id, step_name, status, latency_ms, tokens_used, cost_usd, error, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (run_id, step_name, status, latency_ms, tokens_used, cost_usd, error, datetime.utcnow().isoformat())
        )


def log_run_finish(run_id: str, final_status: str):
    with get_connection() as conn:
        conn.execute(
            "UPDATE runs SET finished_at = ?, final_status = ? WHERE run_id = ?",
            (datetime.utcnow().isoformat(), final_status, run_id)
        )


if __name__ == "__main__":
    init_db()
    test_run_id = "test-run-001"
    log_run_start(test_run_id, "test query for observability")
    log_step(test_run_id, "search", "success", 234.5, tokens_used=0)
    log_step(test_run_id, "fetch", "success", 891.2, tokens_used=0)
    log_step(test_run_id, "synthesize", "success", 1203.7, tokens_used=174, cost_usd=0.000122)
    log_run_finish(test_run_id, "success")

    with get_connection() as conn:
        run = conn.execute("SELECT * FROM runs WHERE run_id = ?", (test_run_id,)).fetchone()
        steps = conn.execute("SELECT * FROM steps WHERE run_id = ?", (test_run_id,)).fetchall()

    print("Run record:", dict(run))
    print(f"\n{len(steps)} step records:")
    for s in steps:
        print(f"  {s['step_name']}: {s['status']} — {s['latency_ms']}ms, "
              f"{s['tokens_used']} tokens, ${s['cost_usd']}")