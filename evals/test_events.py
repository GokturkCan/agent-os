"""Structured execution events: lifecycle order, timeout/retry/verifier
representation, failure safety, secret hygiene, no behaviour change."""
import json
import sys
from pathlib import Path

import pytest

from agentos import events, telemetry, worktree
from agentos.taskstate import TaskStore
from evals.test_timeouts import PYTEST, _fixing_runner, _go, _hanging_runner

FIELDS = {"ts", "event", *events.FIELDS}


def _names(task_id="tmo-task"):
    return [e["event"] for e in events.read_all(task_id)]


def _noop(launch, **kw):
    return {"returncode": 0, "latency_ms": 1.0}


def _crash(launch, **kw):
    return {"returncode": 2, "latency_ms": 1.0}


def test_success_emits_ordered_lifecycle_and_metrics(cfg, fixture_repo, tmp_path):
    res = _go(cfg, fixture_repo, tmp_path, _fixing_runner)
    assert res["exit_state"] == "success"
    assert _names() == ["task_received", "worker_started", "worker_finished", "verification_started",
                        "verification_finished", "task_completed"]
    evs = events.read_all("tmo-task")
    assert all(set(e) == FIELDS for e in evs)                      # stable schema
    fin = {e["event"]: e for e in evs}
    assert fin["worker_finished"]["status"] == "ok" and fin["worker_finished"]["duration_ms"] >= 0
    assert fin["verification_finished"]["verifier_status"] == "passed"
    assert fin["task_completed"]["exit_state"] == "success" and fin["task_completed"]["worker"] == "claude_code"
    assert fin["worker_started"]["attempt"] == 1
    m = res["metrics"]
    assert m["exit_state"] == "success" and m["retries"] == 0 and res["telemetry_errors"] == []
    assert m["task_wall_ms"] >= m["worker_ms"] >= 0 and m["verify_ms"] >= 0
    assert {"ttft_ms", "ram_mb", "vram_mb", "command_started"} <= set(m["unsupported"])
    assert [e["ts"] for e in evs] == sorted(e["ts"] for e in evs)


def test_verifier_failure_is_represented_and_retried(cfg, fixture_repo, tmp_path):
    res = _go(cfg, fixture_repo, tmp_path, _noop)                  # worker ok, tests still fail
    assert res["status"] == "retryable"
    assert _names() == ["task_received", "worker_started", "worker_finished", "verification_started",
                        "verification_finished", "retry"]
    evs = {e["event"]: e for e in events.read_all("tmo-task")}
    assert evs["worker_finished"]["status"] == "ok"
    assert evs["verification_finished"]["verifier_status"] == "failed"
    assert evs["retry"]["verifier_status"] == "failed" and evs["retry"]["attempt"] == 1


def test_failed_worker_emits_finished_then_failed(cfg, fixture_repo, tmp_path):
    results = [_go(cfg, fixture_repo, tmp_path, _crash) for _ in range(3)]
    assert results[-1]["exit_state"] == "budget_exhausted"
    names = _names()
    assert names[-1] == "task_failed" and names.count("retry") == 2
    assert [e["status"] for e in events.read_all("tmo-task") if e["event"] == "worker_finished"] == ["failed"] * 3
    last = events.read_all("tmo-task")[-1]
    assert (last["exit_state"], last["status"]) == ("budget_exhausted", "stopped")


def test_worker_timeout_event_then_retry(cfg, fixture_repo, tmp_path):
    _go(cfg, fixture_repo, tmp_path, _hanging_runner(), timeout=1)
    assert _names() == ["task_received", "worker_started", "worker_finished", "timeout", "retry"]
    evs = {e["event"]: e for e in events.read_all("tmo-task")}
    assert evs["worker_finished"]["status"] == "timeout"
    assert (evs["timeout"]["timeout_kind"], evs["timeout"]["detail"]) == ("per_call", "worker")
    assert evs["retry"]["detail"] == "timeout" and evs["retry"]["verifier_status"] == "skipped"


def test_verifier_timeout_event(cfg, fixture_repo, tmp_path):
    hang = f"{sys.executable} -c 'import time; time.sleep(60)'"
    _go(cfg, fixture_repo, tmp_path, _fixing_runner, verify=hang, verify_timeout=1)
    evs = events.read_all("tmo-task")
    assert [e["event"] for e in evs][-3:] == ["verification_finished", "timeout", "retry"]
    assert evs[-3]["verifier_status"] == "timeout" and evs[-2]["timeout_kind"] == "verify"


def test_final_timeout_exhaustion_is_task_failed_timeout(cfg, fixture_repo, tmp_path):
    for _ in range(3):
        _go(cfg, fixture_repo, tmp_path, _hanging_runner(), timeout=1)
    last = events.read_all("tmo-task")[-1]
    assert (last["event"], last["exit_state"]) == ("task_failed", "timeout")


def test_resume_after_timeout_counts_attempts(cfg, fixture_repo, tmp_path):
    _go(cfg, fixture_repo, tmp_path, _hanging_runner(), timeout=1)
    res = _go(cfg, fixture_repo, tmp_path, _fixing_runner)
    assert res["exit_state"] == "success"
    started = [e for e in events.read_all("tmo-task") if e["event"] == "worker_started"]
    assert [e["attempt"] for e in started] == [1, 2]
    assert TaskStore(cfg).get("tmo-task").state["exit_state"] == "success"


def test_event_write_failure_does_not_break_execution(cfg, fixture_repo, tmp_path, monkeypatch):
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("x")
    monkeypatch.setenv("AGENTOS_TELEMETRY_DIR", str(blocker))      # every telemetry write now fails
    res = _go(cfg, fixture_repo, tmp_path, _fixing_runner)
    assert (res["status"], res["exit_state"]) == ("done", "success")
    assert res["telemetry_errors"] and res["run_id"] is None       # visible, not fatal
    assert TaskStore(cfg).get("tmo-task").state["exit_state"] == "success"   # state stays canonical
    assert worktree.holder(Path(res["worktree"])) is None


def test_emit_never_raises_and_rejects_unknown_events(tmp_path):
    events.clear_errors()
    assert events.emit("not_an_event") is None
    assert events.errors() and "unknown event" in events.errors()[0]


def test_events_contain_no_secrets_or_blobs(cfg, fixture_repo, tmp_path):
    secret = "sk-ABCDEF1234567890SECRET"
    rec = events.emit("worker_finished", task_id="s1", detail=f"Authorization: Bearer {secret} api_key={secret}",
                      prompt="the full prompt", stdout="x" * 5000)
    raw = json.dumps(rec)
    assert secret not in raw and "full prompt" not in raw and "stdout" not in raw
    assert len(rec["detail"]) <= 200
    _go(cfg, fixture_repo, tmp_path, _fixing_runner)
    for f in (telemetry.telemetry_dir() / "events").glob("*.jsonl"):
        assert "fix add()" not in f.read_text()                    # dispatch prompt never logged


def test_traces_unaffected_by_event_stream(cfg, fixture_repo, tmp_path):
    _go(cfg, fixture_repo, tmp_path, _fixing_runner)
    assert all("event" not in r for r in telemetry.read_all())     # TraceRecords stay separate
