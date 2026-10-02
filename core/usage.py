"""Local ChatGPT usage / token stats (SQLite)."""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Optional

DB_NAME = "gpt-ip-guard-usage.db"


def db_path() -> Path:
    try:
        import sys
        if getattr(sys, "frozen", False):
            return Path(sys.executable).parent / DB_NAME
    except Exception:
        pass
    return Path(__file__).resolve().parent.parent / DB_NAME


def _conn() -> sqlite3.Connection:
    p = db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(p), check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


def init_db() -> None:
    with _conn() as c:
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL NOT NULL,
                input_tokens INTEGER DEFAULT 0,
                output_tokens INTEGER DEFAULT 0,
                cache_tokens INTEGER DEFAULT 0,
                source TEXT DEFAULT 'manual',
                note TEXT DEFAULT ''
            )
            """
        )
        c.execute("CREATE INDEX IF NOT EXISTS idx_usage_ts ON usage(ts)")
        c.commit()


def add_record(
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_tokens: int = 0,
    source: str = "manual",
    note: str = "",
    ts: Optional[float] = None,
) -> int:
    init_db()
    ts = ts if ts is not None else time.time()
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO usage(ts, input_tokens, output_tokens, cache_tokens, source, note) VALUES (?,?,?,?,?,?)",
            (ts, int(input_tokens), int(output_tokens), int(cache_tokens), source, note),
        )
        c.commit()
        return int(cur.lastrowid)


def _where_days(days: Optional[int]) -> tuple[str, tuple]:
    if days is None:
        return "", ()
    cutoff = time.time() - days * 86400
    return "WHERE ts >= ?", (cutoff,)


def totals(days: Optional[int] = None) -> dict:
    init_db()
    w, p = _where_days(days)
    with _conn() as c:
        row = c.execute(
            f"""
            SELECT
                COALESCE(SUM(input_tokens),0) AS inp,
                COALESCE(SUM(output_tokens),0) AS outp,
                COALESCE(SUM(cache_tokens),0) AS cache,
                COUNT(*) AS n
            FROM usage {w}
            """,
            p,
        ).fetchone()
        return {
            "input_tokens": row["inp"],
            "output_tokens": row["outp"],
            "cache_tokens": row["cache"],
            "count": row["n"],
            # cache is a subset of input; true spend = input + output
            "total_tokens": row["inp"] + row["outp"],
        }


def daily_series(days: int = 7) -> list[dict]:
    """Per-day sums, oldest first. days=0 → all."""
    init_db()
    cutoff = 0.0
    if days > 0:
        cutoff = time.time() - days * 86400
    with _conn() as c:
        rows = c.execute(
            """
            SELECT date(ts, 'unixepoch', 'localtime') AS d,
                   SUM(input_tokens) AS inp,
                   SUM(output_tokens) AS outp,
                   SUM(cache_tokens) AS cache
            FROM usage
            WHERE ts >= ?
            GROUP BY d
            ORDER BY d ASC
            """,
            (cutoff,),
        ).fetchall()
        return [
            {
                "date": r["d"],
                "input_tokens": r["inp"] or 0,
                "output_tokens": r["outp"] or 0,
                "cache_tokens": r["cache"] or 0,
            }
            for r in rows
        ]


def recent(limit: int = 20, days: Optional[int] = None) -> list[dict]:
    init_db()
    w, p = _where_days(days)
    with _conn() as c:
        rows = c.execute(
            f"SELECT * FROM usage {w} ORDER BY ts DESC LIMIT ?",
            p + (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def clear_all() -> int:
    init_db()
    with _conn() as c:
        n = c.execute("SELECT COUNT(*) FROM usage").fetchone()[0]
        c.execute("DELETE FROM usage")
        c.commit()
        return int(n)
