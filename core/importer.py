"""Auto-sync real local ChatGPT/Codex token usage (from Codex rollout logs)."""
from __future__ import annotations

import json
import time
from pathlib import Path

from . import usage


def _sessions_roots() -> list[Path]:
    home = Path.home()
    return [p for p in (home / ".codex" / "sessions", home / ".codex" / "archived_sessions") if p.is_dir()]


def _parse_ts_ms(obj: dict, fallback: float) -> float:
    ts = obj.get("timestamp")
    if isinstance(ts, (int, float)):
        return ts / 1000.0 if ts > 1e12 else float(ts)
    if isinstance(ts, str):
        try:
            from datetime import datetime
            return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
        except Exception:
            pass
    return fallback


def collect_records(max_files: int = 120) -> list[dict]:
    """One record per response_id from token_usage_record.usage (per-call, not cumulative)."""
    by_id: dict[str, dict] = {}
    files: list[Path] = []
    for root in _sessions_roots():
        files.extend(root.rglob("rollout-*.jsonl"))
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    for fp in files[:max_files]:
        try:
            if fp.stat().st_size > 120_000_000:
                continue
            with open(fp, encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if '"token_usage_record"' not in line:
                        continue
                    try:
                        obj = json.loads(line)
                    except Exception:
                        continue
                    payload = obj.get("payload") or {}
                    u = payload.get("usage") or {}
                    rid = payload.get("response_id") or f"{payload.get('turn_id')}:{obj.get('ordinal')}"
                    if rid in by_id:
                        continue
                    inp = int(u.get("input_tokens") or 0)
                    out = int(u.get("output_tokens") or 0)
                    cache = int(u.get("cached_input_tokens") or 0)  # subset of input
                    if not (inp or out):
                        continue
                    by_id[rid] = {
                        "ts": _parse_ts_ms(obj, fp.stat().st_mtime),
                        "input_tokens": inp,
                        "output_tokens": out,
                        "cache_tokens": cache,
                        "response_id": rid,
                    }
        except Exception:
            continue

    recs = list(by_id.values())
    recs.sort(key=lambda r: r["ts"])
    return recs


def sync_usage(clear_first: bool = True) -> dict:
    """Replace local usage DB with correctly computed real token stats."""
    usage.init_db()
    if clear_first:
        usage.clear_all()
    recs = collect_records()
    for r in recs:
        usage.add_record(
            input_tokens=r["input_tokens"],
            output_tokens=r["output_tokens"],
            cache_tokens=r["cache_tokens"],  # cache is subset of input, stored for display
            source="codex",
            note=r.get("response_id", ""),
            ts=r["ts"],
        )
    return {
        "records": len(recs),
        "totals": usage.totals(),
        "days": len(usage.daily_series(3650)),
    }


def ensure_imported(marker_name: str = "usage-imported.flag") -> bool:
    try:
        import sys
        if getattr(sys, "frozen", False):
            marker = Path(sys.executable).parent / marker_name
        else:
            marker = Path(__file__).resolve().parent.parent / marker_name
    except Exception:
        marker = Path.cwd() / marker_name
    if marker.exists():
        return False
    try:
        stats = sync_usage(True)
        marker.write_text(json.dumps({"at": time.time(), **stats}, ensure_ascii=False), encoding="utf-8")
        return True
    except Exception:
        return False


if __name__ == "__main__":
    print(json.dumps(sync_usage(True), ensure_ascii=False, indent=2))
