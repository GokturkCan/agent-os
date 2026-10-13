"""Append-only JSONL execution events (lifecycle visibility for Hermes/operators).

Not a source of truth: task state (state/tasks/*) stays canonical, and
TraceRecords (telemetry.py) stay the per-run measurement record. Events are a
timeline written to <telemetry_dir>/events/YYYY-MM-DD.jsonl (a subdirectory, so
`telemetry.read_all()` is unaffected).

Event record (null/absent when not applicable; only measured values):
  ts, event, task_id, worker, attempt, iteration, status, exit_state,
  duration_ms, timeout_kind, verifier_status, detail, capabilities
Events: task_received worker_started worker_finished verification_started
  verification_finished timeout retry task_completed task_failed
  capability_decision (Run 2: emitted only when a task declares required
  capabilities; `capabilities` carries ids + reason codes, never free text)
Unsupported in V1 (worker is one opaque subprocess): command_started/finished,
  TTFT, RSS/RAM, VRAM — never estimated.

Safety: emit() never raises. Failures are collected in `errors()` and warned on
stderr; only whitelisted fields are written, strings are truncated and
secret-looking values redacted, so prompts/stdout/stderr never land here.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import telemetry

EVENTS = ("task_received", "worker_started", "worker_finished", "verification_started",
          "verification_finished", "timeout", "retry", "task_completed", "task_failed",
          "capability_decision")
FIELDS = ("task_id", "worker", "attempt", "iteration", "status", "exit_state", "duration_ms",
          "timeout_kind", "verifier_status", "detail", "capabilities")
STRUCTURED = ("capabilities",)   # small JSON structures, cleaned recursively
UNSUPPORTED = ("command_started", "command_finished", "ttft_ms", "ram_mb", "vram_mb")
_MAX_STR = 200
_SECRET = re.compile(r"(?i)(bearer\s+\S+|sk-[A-Za-z0-9_-]{8,}|(?:api[_-]?key|token|secret|password|authorization)\s*[=:]\s*\S+)")

_errors: list[str] = []


def events_dir() -> Path:
    return telemetry.telemetry_dir() / "events"


def errors() -> list[str]:
    return list(_errors)


def clear_errors():
    _errors.clear()


def _clean(v):
    if isinstance(v, str):
        return _SECRET.sub("[REDACTED]", v)[:_MAX_STR]
    return v if isinstance(v, (int, float, bool)) or v is None else str(v)[:_MAX_STR]


def _clean_struct(v, depth: int = 0):
    if depth > 4:
        return None
    if isinstance(v, dict):
        return {str(k)[:64]: _clean_struct(x, depth + 1) for k, x in list(v.items())[:64]}
    if isinstance(v, (list, tuple)):
        return [_clean_struct(x, depth + 1) for x in list(v)[:64]]
    return _clean(v)


def emit(event: str, **fields) -> dict | None:
    """Append one event. Never raises; returns the record or None if it was not written."""
    try:
        if event not in EVENTS:
            raise ValueError(f"unknown event {event!r}")
        rec = {"ts": datetime.now(timezone.utc).isoformat(), "event": event}
        rec.update({k: (_clean_struct if k in STRUCTURED else _clean)(fields.get(k)) for k in FIELDS})
        d = events_dir()
        d.mkdir(parents=True, exist_ok=True)
        with open(d / f"{datetime.now(timezone.utc):%Y-%m-%d}.jsonl", "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, sort_keys=True) + "\n")
        return rec
    except Exception as exc:                      # telemetry must never break execution
        msg = f"{event}: {type(exc).__name__}: {exc}"[:300]
        _errors.append(msg)
        print(f"agentos: event write failed ({msg})", file=sys.stderr)
        return None


def read_all(task_id: str | None = None) -> list[dict]:
    out = []
    for p in sorted(events_dir().glob("*.jsonl")):
        with open(p, encoding="utf-8") as fh:
            out.extend(r for r in map(json.loads, filter(str.strip, fh))
                       if task_id is None or r["task_id"] == task_id)
    return out


def safe_record(**fields) -> dict:
    """telemetry.record that cannot break execution; on failure returns {'run_id': None}."""
    try:
        return telemetry.record(**fields)
    except Exception as exc:
        msg = f"trace_record: {type(exc).__name__}: {exc}"[:300]
        _errors.append(msg)
        print(f"agentos: telemetry write failed ({msg})", file=sys.stderr)
        return {"run_id": None}
