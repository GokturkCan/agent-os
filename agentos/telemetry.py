"""Append-only JSONL telemetry (TraceRecord).

Only measured values are recorded. Unmeasured fields stay null — never
estimated or invented. One file per UTC day under state/telemetry/.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .config import EXIT_STATES, REPO_ROOT

FIELDS = {
    "run_id", "ts", "task_id", "task_type", "route", "worker", "model",
    "provider", "resource_profile", "latency_ms", "ttft_ms", "tokens_in",
    "tokens_out", "cache_read_tokens", "tool_calls", "retries", "cost_usd",
    "exit_state", "success", "quality", "ram_mb", "vram_mb",
    "human_corrections", "fallbacks", "failures", "artifacts",
    "lesson_candidate", "notes",
    "capabilities",   # Run 2 capability decision summary (ids + reason codes); null when not used
}


def telemetry_dir() -> Path:
    return Path(os.environ.get("AGENTOS_TELEMETRY_DIR", REPO_ROOT / "state" / "telemetry"))


def new_run_id() -> str:
    return f"run-{datetime.now(timezone.utc):%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:6]}"


def record(**fields) -> dict:
    unknown = set(fields) - FIELDS
    if unknown:
        raise ValueError(f"unknown telemetry fields: {sorted(unknown)}")
    if fields.get("exit_state") is not None and fields["exit_state"] not in EXIT_STATES:
        raise ValueError(f"invalid exit_state {fields['exit_state']!r}")
    rec = {k: None for k in sorted(FIELDS)}
    rec.update(fields)
    rec["run_id"] = rec["run_id"] or new_run_id()
    rec["ts"] = rec["ts"] or datetime.now(timezone.utc).isoformat()
    d = telemetry_dir()
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{datetime.now(timezone.utc):%Y-%m-%d}.jsonl"
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, sort_keys=True) + "\n")
    return rec


def read_all() -> list[dict]:
    out = []
    for p in sorted(telemetry_dir().glob("*.jsonl")):
        with open(p, encoding="utf-8") as fh:
            out.extend(json.loads(line) for line in fh if line.strip())
    return out


class Timer:
    """Measure wall-clock latency of a block: `with Timer() as t: ...; t.ms`."""

    def __enter__(self):
        self._t0 = time.perf_counter()
        return self

    def __exit__(self, *exc):
        self.ms = round((time.perf_counter() - self._t0) * 1000, 1)
        return False
