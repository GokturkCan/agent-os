"""Run 2 acceptance — capability plane scenarios on the real Wave A registry with
deterministic probe states, dispatch integration, telemetry, Run 1 invariance.
No test depends on which tools are installed on this machine, and none touches the network."""
import copy
import json
from pathlib import Path

import pytest

from agentos import capability_policy as CP
from agentos import capability_probes as P
from agentos import capability_registry as R
from agentos import events, router, telemetry
from agentos.dispatch import dispatch
from agentos.taskstate import TaskStore
from evals.test_timeouts import PYTEST, _fixing_runner

ALL_OK = {"available": "present", "health": "healthy", "auth": "present"}


@pytest.fixture(scope="module")
def reg(cfg):
    return R.load(cfg)


def _plan(reg, required, states=None, **req):
    probes = P.static_probes(reg, states=states, default=ALL_OK)
    return CP.plan(reg, CP.CapabilityRequest(required=tuple(required), **req), probes)


def _variant(cfg, mutate):
    data = copy.deepcopy(R.load_raw())
    mutate(data)
    reg, errs = R.parse(data, cfg)
    assert errs == [], errs
    return reg


# ------------------------------------------------------------ scenarios 1-10
def test_s1_code_references_serena_path_eligible(reg):
    pl = _plan(reg, ["code.references"])
    assert pl.status == "selected" and pl.executor == "claude-code"
    assert pl.tools == {"code.references": "serena"}
    assert pl.by_capability["code.references"].eligible == ["serena"]
    assert "semantic-navigation-required" in pl.reasons


def test_s2_serena_unavailable_is_explainable(reg):
    pl = _plan(reg, ["code.references"], states={"serena": {"available": "absent"}})
    assert (pl.status, pl.exit_state, pl.reasons) == ("blocked", "blocked", ["no-eligible-provider"])
    assert pl.by_capability["code.references"].rejected["serena"].reasons == ["provider-unavailable"]
    assert pl.handoff == ["code.references: serena (provider-unavailable)"]
    assert "rejected serena: provider-unavailable" in "\n".join(pl.explain())


def test_s3_docs_lookup_matches_context7(reg):
    pl = _plan(reg, ["web.docs_lookup"])
    assert pl.tools == {"web.docs_lookup": "context7"} and pl.executor == "claude-code"


def test_s4_context7_auth_required_and_missing_is_filtered(cfg, reg):
    strict = _variant(cfg, lambda d: next(p for p in d["providers"] if p["id"] == "context7").update(
        {"auth": "required"}))
    pl = _plan(strict, ["web.docs_lookup"], states={"context7": {"auth": "missing"}})
    assert pl.status == "blocked"
    assert pl.by_capability["web.docs_lookup"].rejected["context7"].reasons == ["auth-missing"]
    # As actually registered, Context7 auth is optional: missing key only flags it.
    ok = _plan(reg, ["web.docs_lookup"], states={"context7": {"auth": "missing"}})
    assert ok.status == "selected" and "auth-optional-absent" in ok.flags["context7"]


def test_s5_web_interact_prefers_playwright(reg):
    pl = _plan(reg, ["web.interact"])
    assert pl.tools == {"web.interact": "playwright"}
    res = pl.by_capability["web.interact"]
    assert res.eligible == ["playwright"] and "browser-deterministic" in res.reasons
    assert res.rejected["browser-use"].reasons == ["policy-blocked"]   # future fallback, never selected


def test_s6_playwright_unavailable_is_deterministic_no_eligible(reg):
    runs = [_plan(reg, ["web.interact"], states={"playwright": {"available": "absent"}}).to_dict()
            for _ in range(3)]
    assert runs[0] == runs[1] == runs[2]
    pl = runs[0]
    assert pl["status"] == "blocked" and pl["executor"] is None
    rej = pl["by_capability"]["web.interact"]["rejected"]
    assert rej["playwright"]["reasons"] == ["provider-unavailable"]
    assert rej["browser-use"]["reasons"] == ["policy-blocked"]          # the later browser-use fallback is visible


def test_s7_github_operation_requires_devops_github(reg):
    caps = CP.resolve_required(reg, task_type="github")
    assert caps == ("devops.github",)
    pl = _plan(reg, caps)
    assert pl.tools == {"devops.github": "github-mcp"} and pl.tool_fallbacks == {"devops.github": ["gh-cli"]}
    down = _plan(reg, caps, states={"github-mcp": {"health": "unhealthy"}})
    assert down.tools == {"devops.github": "gh-cli"}                    # Run 1's read-only CLI fallback


def test_s8_reverse_engineering_selects_rea(cfg, reg):
    caps = CP.resolve_required(reg, ["reverse_engineering.decompile"], task_type="reverse_engineering")
    pl = _plan(reg, caps)
    for cap in caps:                                                   # REA is the selected provider
        res = pl.by_capability[cap]
        assert res.selected == "rea" and "reverse-engineering-required" in res.reasons
    # No executor declares an REA integration yet (rea: unknown) -> honest block, not a guess.
    assert pl.status == "blocked"
    assert pl.rejected_executors["claude-code"].reasons == ["capability-missing", "integration-unknown"]
    # Once an executor integration is declared, the full plan selects it with REA.
    wired = _variant(cfg, lambda d: next(p for p in d["providers"] if p["id"] == "claude-code")[
        "integrations"].update({"rea": "supported"}))
    pl = _plan(wired, caps)
    assert pl.status == "selected" and pl.executor == "claude-code" and set(pl.tools.values()) == {"rea"}
    assert "reverse-engineering-required" in pl.reasons


def test_s9_no_valid_executor_blocks_instead_of_guessing(reg):
    pl = _plan(reg, ["code.edit"], states={e: {"available": "absent"} for e in ("claude-code", "codex", "opencode")})
    assert (pl.status, pl.executor, pl.worker, pl.eligible_workers) == ("blocked", None, None, [])
    assert pl.next_step.startswith("human handoff")
    assert pl.rejected_executors["claude-code"].reasons == ["provider-unavailable"]
    assert pl.rejected_executors["codex"].reasons == ["provider-unavailable"]
    assert pl.rejected_executors["opencode"].reasons == ["policy-blocked", "provider-unavailable"]   # disabled + absent


def test_s10_local_free_beats_cloud_metered(cfg):
    reg = _variant(cfg, lambda d: d["providers"].append(
        {"id": "cloud-packer", "kind": "cli", "adoption": "adopted", "capabilities": ["code.snapshot"],
         "requires": ["devops.shell"], "locality": "cloud", "cost": "metered", "latency": "network",
         "hosts": ["cloud"], "auth": "none"}))
    pl = _plan(reg, ["code.snapshot"])
    res = pl.by_capability["code.snapshot"]
    assert res.eligible == ["repomix", "cloud-packer"] and res.reasons == ["cost-preferred"]
    assert pl.tools == {"code.snapshot": "repomix"} and pl.tool_fallbacks == {"code.snapshot": ["cloud-packer"]}
    assert pl.metadata["repomix"]["locality"] == "local"


def test_real_probe_state_never_crashes_planning(cfg):
    for caps in (["code.references"], ["web.interact"], ["devops.github"], ["reverse_engineering.decompile"],
                 ["code.edit", "code.snapshot"], ["code.telepathy"], []):
        pl = CP.plan_for(cfg, caps)
        assert pl.status in ("selected", "blocked") and pl.explain()


# ------------------------------------------------------------ telemetry (R2.7)
def test_capability_decision_event_shape(reg):
    pl = _plan(reg, ["web.interact"], task_id="cap-evt")
    rec = CP.emit_decision(pl)
    assert rec["event"] == "capability_decision" and rec["task_id"] == "cap-evt"
    c = events.read_all("cap-evt")[0]["capabilities"]
    assert c["required"] == ["web.interact"] and c["executor"] == "claude-code"
    assert c["tools"] == {"web.interact": "playwright"} and c["rejected"]["codex"] == [
        "capability-missing", "integration-unsupported"]
    assert c["rejected_tools"]["web.interact"]["browser-use"] == ["policy-blocked"]
    assert (c["cost"], c["locality"]) == ("existing_subscription", "cloud")


def test_blocked_decision_records_failure_reasons(reg):
    pl = _plan(reg, ["devops.github"], task_id="cap-blk",
               states={"github-mcp": {"auth": "missing"}, "gh-cli": {"health": "unhealthy"}})
    CP.emit_decision(pl)
    c = events.read_all("cap-blk")[0]["capabilities"]
    assert c["status"] == "blocked" and c["exit_state"] == "blocked"
    assert c["rejected_tools"]["devops.github"] == {"github-mcp": ["auth-missing"], "gh-cli": ["provider-unhealthy"]}


def test_telemetry_failure_does_not_break_selection(reg, tmp_path, monkeypatch):
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("x")
    monkeypatch.setenv("AGENTOS_TELEMETRY_DIR", str(blocker))
    events.clear_errors()
    pl = _plan(reg, ["code.references"], task_id="cap-tf")
    assert CP.emit_decision(pl) is None and events.errors()
    assert pl.status == "selected" and pl.executor == "claude-code"


def test_capability_telemetry_never_leaks_secrets(reg):
    secret = "sk-ABCDEF1234567890SECRET"
    pl = _plan(reg, [f"token={secret}"], task_id="cap-sec")
    CP.emit_decision(pl)
    raw = json.dumps(events.read_all("cap-sec"))
    assert secret not in raw and "[REDACTED]" in raw


# ------------------------------------------------------------ dispatch integration
OK_EXECUTORS = {pid: dict(ALL_OK) for pid in ("claude-code", "codex", "opencode", "serena")}


def _go(cfg, repo, tmp_path, runner, task_id="cap-task", **kw):
    return dispatch(cfg, task_id=task_id, task_type="coding", repo=repo, prompt="fix add()",
                    verify=PYTEST, runner=runner, worktree_root=tmp_path / "wts", **kw)


def _never(launch, **kw):
    raise AssertionError("worker must not run")


def test_run1_dispatch_unmapped_task_type_is_unchanged(cfg, fixture_repo, tmp_path):
    # `review` has no task_types mapping and nothing is declared -> exact Run 1 path.
    res = dispatch(cfg, task_id="cap-task", task_type="review", repo=fixture_repo, prompt="fix add()",
                   verify=PYTEST, runner=_fixing_runner, worktree_root=tmp_path / "wts")
    assert (res["status"], res["exit_state"], res["worker"]) == ("done", "success", "claude_code")
    assert "capabilities" not in res
    assert "capability_decision" not in [e["event"] for e in events.read_all("cap-task")]
    assert telemetry.read_all()[-1]["capabilities"] is None
    assert "required_capabilities" not in TaskStore(cfg).get("cap-task").contract


def test_run1_route_identical_without_eligible_workers(cfg):
    for ev in ({"type": "coding"}, {"type": "review"}, {"type": "summarization"}):
        assert router.route(cfg, dict(ev)).to_dict() == router.route(cfg, {**ev, "eligible_workers": None}).to_dict()


def test_dispatch_with_capabilities_selects_and_records(cfg, fixture_repo, tmp_path):
    res = _go(cfg, fixture_repo, tmp_path, _fixing_runner, required_capabilities=("code.references",),
              capability_overrides=OK_EXECUTORS)
    assert (res["status"], res["exit_state"], res["worker"]) == ("done", "success", "claude_code")
    c = res["capabilities"]
    assert c["executor"] == "claude-code" and c["routed_worker"] == "claude_code"
    assert c["required"] == ["code.edit", "code.references", "code.test"]   # + coding task_type mapping
    names = [e["event"] for e in events.read_all("cap-task")]
    assert names[:3] == ["task_received", "capability_decision", "worker_started"]
    assert telemetry.read_all()[-1]["capabilities"]["executor"] == "claude-code"
    assert TaskStore(cfg).get("cap-task").contract["required_capabilities"] == ["code.references"]


def test_dispatch_blocked_by_capabilities_never_runs_a_worker(cfg, fixture_repo, tmp_path):
    res = _go(cfg, fixture_repo, tmp_path, _never, required_capabilities=("reverse_engineering.decompile",),
              capability_overrides={**OK_EXECUTORS, "rea": {"available": "absent"}})
    assert (res["status"], res["exit_state"]) == ("not_dispatched", "blocked")
    assert res["capabilities"]["status"] == "blocked" and res["next_step"].startswith("human handoff")
    assert any("rejected rea: provider-unavailable" in line for line in res["trace"])
    assert not (tmp_path / "wts").exists() and TaskStore(cfg).list() == []
    assert [e["event"] for e in events.read_all("cap-task")] == ["task_received", "capability_decision",
                                                                  "task_failed"]
    assert telemetry.read_all()[-1]["capabilities"]["status"] == "blocked"


def test_capability_eligibility_narrows_router_fallback(cfg, fixture_repo, tmp_path):
    # Run 1 would fall back to codex when Claude is down; codex has no Serena path, so it is not eligible.
    res = _go(cfg, fixture_repo, tmp_path, _never, required_capabilities=("code.references",),
              capability_overrides=OK_EXECUTORS, health={"providers": {"claude_subscription": False}})
    assert (res["status"], res["exit_state"]) == ("not_dispatched", "blocked")
    assert "C4: skip worker codex: not capability-eligible" in res["trace"]
    plain = _go(cfg, fixture_repo, tmp_path, None, task_id="cap-plain", dry_run=True,
                health={"providers": {"claude_subscription": False}})
    assert plain["worker"] == "codex"                                    # Run 1 behaviour without capabilities


def test_resume_reuses_contract_capabilities(cfg, fixture_repo, tmp_path):
    noop = lambda launch, **kw: {"returncode": 0, "latency_ms": 1.0}
    first = _go(cfg, fixture_repo, tmp_path, noop, required_capabilities=("code.references",),
                capability_overrides=OK_EXECUTORS)
    assert first["status"] == "retryable"
    second = _go(cfg, fixture_repo, tmp_path, _fixing_runner, capability_overrides=OK_EXECUTORS)
    assert second["status"] == "done" and second["capabilities"]["required"][1] == "code.references"
    assert [e["event"] for e in events.read_all("cap-task")].count("capability_decision") == 2


def test_dispatch_dry_run_reports_plan_without_events(cfg, fixture_repo, tmp_path):
    res = _go(cfg, fixture_repo, tmp_path, None, dry_run=True, required_capabilities=("web.docs_lookup",),
              capability_overrides=OK_EXECUTORS)
    assert res["status"] == "dry_run" and res["capabilities"]["tools"]["web.docs_lookup"] == "context7"
    assert events.read_all("cap-task") == []


def test_dispatch_with_capabilities_survives_telemetry_failure(cfg, fixture_repo, tmp_path, monkeypatch):
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("x")
    monkeypatch.setenv("AGENTOS_TELEMETRY_DIR", str(blocker))
    res = _go(cfg, fixture_repo, tmp_path, _fixing_runner, required_capabilities=("code.references",),
              capability_overrides=OK_EXECUTORS)
    assert (res["status"], res["exit_state"]) == ("done", "success")
    assert res["telemetry_errors"] and res["capabilities"]["executor"] == "claude-code"


def test_invalid_registry_fails_closed_only_when_capabilities_declared(cfg, fixture_repo, tmp_path, monkeypatch):
    def broken(cfg_):
        raise R.RegistryError(["registry: broken for test"])
    monkeypatch.setattr(R, "load", broken)
    res = _go(cfg, fixture_repo, tmp_path, _never, required_capabilities=("code.edit",))
    assert (res["status"], res["exit_state"]) == ("not_dispatched", "blocked")
    assert "capability plane error" in res["trace"][0]
    # Nothing declared: an unreadable registry only skips the task_type mapping (Run 1 path).
    ok = _go(cfg, fixture_repo, tmp_path, _fixing_runner, task_id="cap-norun2")
    assert ok["exit_state"] == "success" and "capabilities" not in ok
