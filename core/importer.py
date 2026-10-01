"""Import real ChatGPT/Codex token usage from local Codex rollout logs."""
from __future__ import annotations

import json
import time
from collections import defaultdict
from pathlib import Path
from typing import Optional

from . import usage


def _sessions_roots() -> list[Path]:
    roots = []
    home = Path.home()
    for p in (
        home / ".codex" / "sessions",
        home / ".codex" / "archived_sessions",
    ):
        if p.is_dir():
            roots.append(p)
    return roots


def _parse_ts_ms(obj: dict, fallback: float) -> float:
    ts = obj.get("timestamp")
    if isinstance(ts, (int, float)):
        # ms if large
        return ts / 1000.0 if ts > 1e12 else float(ts)
    if isinstance(ts, str):
        try:
            # 2026-09-11T10:01:50.056Z
            from datetime import datetime, timezone
            s = ts.replace("Z", "+00:00")
            dt = datetime.fromisoformat(s)
            return dt.timestamp()
        except Exception:
            pass
    return fallback


def collect_from_rollouts(max_files: int = 80) -> list[dict]:
    """Return list of {ts, input_tokens, output_tokens, cache_tokens, source}.

    Only scans the newest N rollout files and only token-usage lines.
    """
    records = []
    files: list[Path] = []
    for root in _sessions_roots():
        files.extend(root.rglob("rollout-*.jsonl"))
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    files = files[:max_files]

    for fp in files:
        try:
            # skip huge cold files quickly by size guard
            if fp.stat().st_size > 80_000_000:
                continue
            with open(fp, encoding="utf-8", errors="ignore") as f:
                for line in f:
                    # token_usage_record is one-per-response; avoid token_count (cumulative)
                    if '"token_usage_record"' not in line:
                        continue
                    try:
                        obj = json.loads(line)
                    except Exception:
                        continue
                    payload = obj.get("payload") or {}
                    ts = _parse_ts_ms(obj, fp.stat().st_mtime)
                    usage_obj = payload.get("usage") or {}
                    if not isinstance(usage_obj, dict):
                        continue
                    inp = int(usage_obj.get("input_tokens") or 0)
                    out = int(usage_obj.get("output_tokens") or 0)
                    cache = int(usage_obj.get("cached_input_tokens") or 0) + int(
                        usage_obj.get("cache_write_input_tokens") or 0
                    )
                    if inp or out or cache:
                        records.append({
                            "ts": ts,
                            "input_tokens": inp,
                            "output_tokens": out,
                            "cache_tokens": cache,
                            "source": "codex",
                        })
        except Exception:
            continue

    return records


def _dedupe_by_response(records: list[dict]) -> list[dict]:
    """token_usage_record and token_count may duplicate; keep unique by (day,bucket)."""
    # collapse same-minute identical amounts to one (handles double events)
    seen = {}
    out = []
    for r in records:
        key = (int(r["ts"] // 60), r["input_tokens"], r["output_tokens"], r["cache_tokens"])
        if key in seen:
            continue
        seen[key] = True
        out.append(r)
    return out


def import_local_usage(clear_first: bool = False) -> dict:
    """Import real local token usage into app DB."""
    usage.init_db()
    if clear_first:
        usage.clear_all()

    records = _dedupe_by_response(collect_from_rollouts())
    source = "rollout"
    if not records:
        # only if no fine-grained usage found
        records = _dedupe_by_response(_from_threads_table())
        source = "codex-thread"

    n = 0
    for r in records:
        usage.add_record(
            input_tokens=r["input_tokens"],
            output_tokens=r["output_tokens"],
            cache_tokens=r["cache_tokens"],
            source=r.get("source", source),
            note="local import",
            ts=r["ts"],
        )
        n += 1

    return {
        "imported": n,
        "totals": usage.totals(),
        "series_days": len(usage.daily_series(365)),
    }


def _from_threads_table() -> list[dict]:
    """Fallback: threads.tokens_used as total tokens on created day."""
    import sqlite3

    db = Path.home() / ".codex" / "state_5.sqlite"
    if not db.is_file():
        return []
    out = []
    try:
        c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        rows = c.execute(
            "SELECT created_at, tokens_used FROM threads WHERE tokens_used > 0 AND created_at IS NOT NULL"
        ).fetchall()
        c.close()
    except Exception:
        return []

    # Only use threads table if we didn't already get fine-grained records for that day
    # Caller merges + dedupes loosely
    for created_at, tokens in rows:
        try:
            out.append({
                "ts": float(created_at),
                "input_tokens": int(tokens),  # coarse: all as input
                "output_tokens": 0,
                "cache_tokens": 0,
                "source": "codex-thread",
            })
        except Exception:
            continue
    return out


def ensure_imported(marker_name: str = "usage-imported.flag") -> bool:
    """Import once on first run. Returns True if imported now."""
    try:
        if getattr(__import__("sys"), "frozen", False):
            marker = Path(__import__("sys").executable).parent / marker_name
        else:
            marker = Path(__file__).resolve().parent.parent / marker_name
    except Exception:
        marker = Path.cwd() / marker_name

    if marker.exists():
        return False
    try:
        stats = import_local_usage(clear_first=True)
        marker.write_text(json.dumps({"at": time.time(), **stats}), encoding="utf-8")
        return True
    except Exception:
        return False


if __name__ == "__main__":
    print(json.dumps(import_local_usage(clear_first=True), ensure_ascii=False, indent=2))
