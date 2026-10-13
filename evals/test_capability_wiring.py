"""Run 2 completion — automatic task_type requirements and capability-selected MCP wiring.

Playwright least privilege: the coder profile MAY receive Playwright (human-approved
grant), but only when the capability plan selected it for the task; the default
coder launch stays Context7 + Serena."""
import json
from pathlib import Path

from agentos import capability_policy as CP
from agentos import capability_registry as R
from agentos import events, telemetry
from agentos.dispatch import dispatch
from agentos.permissions import WorkerSession
from agentos.taskstate import TaskStore
from agentos.workers import build_launch, mcp_servers_for
from evals.test_timeouts import FIXED, PYTEST

OK = {"available": "present", "health": "healthy", "auth": "present"}
OVERRIDES = {pid: dict(OK) for pid in ("claude-code", "codex", "opencode", "serena", "context7", "playwright")}


def _go(cfg, repo, tmp_path, runner=None, task_id="wire-task", task_type="coding", **kw):
    kw.setdefault("capability_overrides", OVERRIDES)
    return dispatch(cfg, task_id=task_id, task_type=task_type, repo=repo, prompt="fix add()", verify=PYTEST,
                    runner=runner, worktree_root=tmp_path / "wts", **kw)


def _capturing_runner(seen):
    def run(launch, **kw):
        seen.append({"argv": launch["argv"],
                     "mcp": json.loads(Path(launch["files"]["mcp_config"]).read_text())["mcpServers"]})
        (Path(launch["cwd"]) / "calc.py").write_text(FIXED)
        return {"returncode": 0, "latency_ms": 1.0}
    return run


# ------------------------------------------------------------ A / B: automatic requirements
def test_a_coding_without_flag_resolves_code_edit_and_test(cfg, fixture_repo, tmp_path):
    res = _go(cfg, fixture_repo, tmp_path, _capturing_runner([]))
    assert (res["status"], res["exit_state"]) == ("done", "success")
    c = res["capabilities"]
    assert c["required"] == ["code.edit", "code.test"]
    assert c["tools"] == {"code.edit": "claude-code", "code.test": "claude-code"}   # native, no MCP
    assert c["extra_mcp"] == []
    assert telemetry.read_all()[-1]["capabilities"]["required"] == ["code.edit", "code.test"]
    # Auto-resolved plan: lifecycle event stream and task contract keep their Run 1 shape.
    assert "capability_decision" not in [e["event"] for e in events.read_all("wire-task")]
    assert "required_capabilities" not in TaskStore(cfg).get("wire-task").contract


def test_a_resolution_is_the_registry_mapping_not_inference(cfg):
    reg = R.load(cfg)
    assert CP.resolve_required(reg, (), "coding") == ("code.edit", "code.test")
    assert CP.resolve_required(reg, (), "review") == ()


def test_b_unmapped_task_type_preserves_old_behaviour(cfg, fixture_repo, tmp_path):
    res = _go(cfg, fixture_repo, tmp_path, None, task_type="review", dry_run=True)
    assert res["status"] == "dry_run" and res["worker"] == "claude_code"
    assert "capabilities" not in res
    assert res["mcp_servers"] == ["context7", "serena"]


def test_b_unknown_task_type_still_blocked_by_router_not_capabilities(cfg, fixture_repo, tmp_path):
    res = _go(cfg, fixture_repo, tmp_path, None, task_type="no-such-type", dry_run=True)
    assert (res["status"], res["exit_state"]) == ("not_dispatched", "blocked")
    assert "capabilities" not in res and "no task class 'no-such-type'" in " ".join(res["trace"])


# ------------------------------------------------------------ C / D: Playwright is task-specific
def test_c_normal_coder_launch_has_no_playwright(cfg, fixture_repo, tmp_path):
    session = WorkerSession.start(cfg, "claude_code", "coder")
    assert session.check("mcp_playwright")                    # MAY receive it (approved grant) ...
    launch = build_launch(cfg, session, "x", tmp_path)
    assert launch["mcp_servers"] == ["context7", "serena"]    # ... but never by default
    assert cfg.mcp["exposure"]["coder"] == ["context7", "serena"]
    res = _go(cfg, fixture_repo, tmp_path, None, dry_run=True)
    assert res["mcp_servers"] == ["context7", "serena"] and "mcp__playwright" not in " ".join(res["launch_argv"])


def test_d_plan_selecting_playwright_reaches_strict_mcp_config(cfg, fixture_repo, tmp_path):
    seen = []
    res = _go(cfg, fixture_repo, tmp_path, _capturing_runner(seen), required_capabilities=("web.interact",))
    assert res["exit_state"] == "success"
    assert res["capabilities"]["tools"]["web.interact"] == "playwright"
    assert res["capabilities"]["extra_mcp"] == ["playwright"]
    assert sorted(seen[0]["mcp"]) == ["context7", "playwright", "serena"]       # generated strict config
    assert seen[0]["mcp"]["playwright"] == {"command": "npx", "args": ["@playwright/mcp@latest"]}
    allowed = seen[0]["argv"][seen[0]["argv"].index("--allowedTools") + 1]
    assert "mcp__playwright" in allowed and "--strict-mcp-config" in seen[0]["argv"]


def test_d_playwright_exposure_does_not_leak_into_later_tasks(cfg, fixture_repo, tmp_path):
    browser = _go(cfg, fixture_repo, tmp_path, None, task_id="wire-b", dry_run=True,
                  required_capabilities=("web.browser_test",))
    plain = _go(cfg, fixture_repo, tmp_path, None, task_id="wire-p", dry_run=True)
    assert "playwright" in browser["mcp_servers"] and "playwright" not in plain["mcp_servers"]


# ------------------------------------------------------------ E / F: nothing unrelated, grants enforced
def test_e_only_selected_mcps_are_exposed(cfg, fixture_repo, tmp_path):
    res = _go(cfg, fixture_repo, tmp_path, None, dry_run=True, required_capabilities=("web.interact",))
    assert set(res["mcp_servers"]) == {"context7", "serena", "playwright"}
    for unrelated in ("github_mcp", "sequential_thinking", "notion", "postman", "claude_ai_connectors"):
        assert unrelated not in res["mcp_servers"]


def test_e_cli_native_and_launchless_providers_are_never_mcp(cfg, fixture_repo, tmp_path):
    snap = _go(cfg, fixture_repo, tmp_path, None, task_id="wire-s", dry_run=True,
               required_capabilities=("code.snapshot",))
    assert snap["capabilities"]["tools"]["code.snapshot"] == "repomix"      # a CLI provider ...
    assert snap["capabilities"]["extra_mcp"] == []                          # ... is not an MCP
    gh = _go(cfg, fixture_repo, tmp_path, None, task_id="wire-g", dry_run=True,
             required_capabilities=("devops.github",),
             capability_overrides={**OVERRIDES, "github-mcp": dict(OK)})
    assert gh["capabilities"]["tools"]["devops.github"] == "github-mcp"     # selected MCP, but no launch
    assert gh["capabilities"]["extra_mcp"] == [] and "github_mcp" not in gh["mcp_servers"]


def test_e_selected_mcp_maps_only_the_routed_workers_tools(cfg):
    reg = R.load(cfg)
    plan = CP.plan_for(cfg, ("web.interact",), overrides=OVERRIDES, registry=reg)
    assert CP.selected_mcp(cfg, reg, plan, "claude_code") == ("playwright",)
    assert CP.selected_mcp(cfg, reg, plan, "codex") == ()                   # not eligible -> nothing
    native = CP.plan_for(cfg, ("code.edit",), overrides=OVERRIDES, registry=reg)
    assert CP.selected_mcp(cfg, reg, native, "claude_code") == ()


def test_f_tool_without_profile_grant_stays_excluded(cfg, fixture_repo, tmp_path):
    res = _go(cfg, fixture_repo, tmp_path, None, dry_run=True, profile="readonly",
              required_capabilities=("web.interact",))
    assert res["capabilities"]["extra_mcp"] == ["playwright"]               # selected by the plan ...
    assert "playwright" not in res["mcp_servers"]                           # ... denied by the profile
    reviewer = WorkerSession.start(cfg, "claude_code", "reviewer")
    assert "playwright" not in mcp_servers_for(cfg, reviewer, ("playwright",))


def test_policy_change_is_exactly_the_approved_grant(cfg):
    caps = cfg.capabilities
    assert set(caps["profiles"]["coder"]["grants"]) == {
        "fs_read", "fs_write_worktree", "shell", "shell_readonly", "git_commit_local", "mcp_context7",
        "mcp_serena", "web_fetch", "mcp_playwright"}
    for prof in ("readonly", "reviewer", "knowledge_compiler", "knowledge_reviewer", "untrusted"):
        assert "mcp_playwright" not in caps["profiles"][prof]["grants"]
    assert "mcp_github_read" not in caps["profiles"]["coder"]["grants"]
