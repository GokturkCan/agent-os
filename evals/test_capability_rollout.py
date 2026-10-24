"""Pre-Run 4 capability rollout (2026-10-24): pins, Codex parity, GitHub credential isolation for
dispatched workers, Orchestra progressive exposure, vendored Ponytail integrity, runtime locks.
Non-destructive: no network, no real GitHub call, no credential read."""
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from agentos import capability_policy as CP
from agentos import capability_probes as P
from agentos import capability_registry as R
from agentos.config import REPO_ROOT
from agentos.permissions import WorkerSession
from agentos.workers import build_launch

ALL_OK = {"available": "present", "health": "healthy", "auth": "present"}


@pytest.fixture
def reg(cfg):
    return R.load(cfg)


def _plan(reg, caps, **req):
    probes = P.static_probes(reg, default=ALL_OK)
    return CP.plan(reg, CP.CapabilityRequest(required=tuple(caps), **req), probes)


# ------------------------------------------------------------ pins
@pytest.mark.parametrize("tool,needle", [("serena", "@v2.1.0"), ("context7", "@4.4.4"), ("playwright", "@0.0.83")])
def test_worker_launched_mcp_servers_are_pinned(cfg, tool, needle):
    args = " ".join(cfg.mcp["tools"][tool]["launch"]["args"])
    assert needle in args and "@latest" not in args
    if tool == "serena":
        assert re.search(r"git\+https://github\.com/oraios/serena@v\d+\.\d+\.\d+", args)


def test_no_launch_arg_floats(cfg):
    for name, spec in cfg.mcp["tools"].items():
        for a in (spec.get("launch") or {}).get("args", []):
            assert "@latest" not in str(a), name
            if "git+https://" in str(a):
                assert "@" in str(a).split("git+https://", 1)[1], f"{name}: unpinned git source"


# ------------------------------------------------------------ registry honesty
def test_adopted_providers_are_not_declared_only_except_the_documented_exception(reg):
    """registration != adoption: an adopted provider must be probe-able; `rea` is the one documented exception."""
    declared_only = {p.id for p in reg.providers.values() if p.adoption == "adopted" and p.probe
                     and all(s.get("type") == "declared" for s in p.probe)}
    assert declared_only <= {"rea"}


def test_dormant_installs_are_recorded_disabled_with_reasons(reg):
    for pid in ("superclaude", "omniroute", "clawdbot"):
        p = reg.get(pid)
        assert p.adoption == "disabled" and p.reason and pid not in {x.id for x in reg.providers_for("engineering.spec")}
    assert reg.get("openspec").adoption == "benchmark"
    assert "openspec" not in CP.plan(reg, CP.CapabilityRequest(required=("engineering.spec",)),
                                     P.static_probes(reg, default=ALL_OK)).tools.values()


def test_context7_optional_auth_is_not_reported_missing(cfg, reg):
    p = reg.get("context7")
    assert p.auth == "optional" and not any(s.get("type") == "env_auth" for s in p.probe)
    st = P.probe_provider(p, P.ProbeContext(cfg=cfg, which=lambda n: "/x/" + n, env={}, deep=False))
    assert st.auth != "missing"


def test_repomix_probe_checks_the_real_wrapper_not_npx(reg):
    spec = reg.get("repomix").probe[0]
    assert spec["type"] == "executable" and spec["target"].endswith("agent-stack/bin/repomix")
    assert not any(s.get("target") == "npx" for s in reg.get("repomix").probe)   # npx existing must not imply Repomix


# ------------------------------------------------------------ Codex parity (intentional no-MCP asymmetry)
MCP_DEPENDENT = ["code.semantic_navigation", "code.symbol_lookup", "code.references", "web.docs_lookup",
                 "web.browser_test", "web.interact"]


@pytest.mark.parametrize("cap", MCP_DEPENDENT)
def test_mcp_dependent_capabilities_never_select_codex(cfg, reg, cap):
    pl = _plan(reg, [cap])
    assert "codex" not in pl.eligible_executors and pl.executor == "claude-code"
    assert CP.selected_mcp(cfg, reg, pl, "codex") == ()


@pytest.mark.parametrize("cap", MCP_DEPENDENT)
def test_when_claude_is_down_mcp_tasks_hand_off_instead_of_falling_to_codex(reg, cap):
    probes = P.static_probes(reg, states={"claude-code": {"health": "unhealthy"}}, default=ALL_OK)
    pl = CP.plan(reg, CP.CapabilityRequest(required=(cap,)), probes)
    assert pl.eligible_executors == [] and pl.executor is None


def test_codex_still_serves_plain_coding(reg):
    probes = P.static_probes(reg, states={"claude-code": {"health": "unhealthy"}}, default=ALL_OK)
    pl = CP.plan(reg, CP.CapabilityRequest(required=("code.edit", "code.test")), probes)
    assert pl.executor == "codex"


# ------------------------------------------------------------ GitHub credential isolation for dispatched workers
@pytest.mark.parametrize("profile", ["readonly", "coder", "reviewer"])
def test_claude_workers_are_denied_gh(cfg, tmp_path, profile):
    argv = build_launch(cfg, WorkerSession.start(cfg, "claude_code", profile), "p", tmp_path)["argv"]
    denied = argv[argv.index("--disallowedTools") + 1].split(",")
    for pat in ("Bash(gh:*)", "Bash(env gh:*)", "Bash(/opt/homebrew/bin/gh:*)", "Bash(*gh auth*)", "Bash(*gh api*)"):
        assert pat in denied
    allowed = argv[argv.index("--allowedTools") + 1].split(",")
    assert not any(a.startswith("Bash(gh") for a in allowed)


@pytest.mark.parametrize("worker", ["claude_code", "codex"])
def test_worker_launch_env_has_no_github_identity(cfg, tmp_path, worker):
    env = build_launch(cfg, WorkerSession.start(cfg, worker, "coder"), "p", tmp_path)["env"]
    iso = Path(env["GH_CONFIG_DIR"])
    assert iso.is_dir() and not any(iso.iterdir()) and iso != Path("~/.config/gh").expanduser()
    assert oct(iso.stat().st_mode & 0o777) == "0o700"
    for var in ("GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN", "GITHUB_ENTERPRISE_TOKEN",
                "GITHUB_PERSONAL_ACCESS_TOKEN"):
        assert env[var] == ""
    assert env["GIT_CONFIG_KEY_0"] == "core.hooksPath"            # the push guard is unchanged


def test_launch_env_overrides_an_ambient_github_token(cfg, tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_PERSONAL_ACCESS_TOKEN", "ambient-not-a-real-token")
    monkeypatch.setenv("GH_TOKEN", "ambient-not-a-real-token")
    env = build_launch(cfg, WorkerSession.start(cfg, "claude_code", "coder"), "p", tmp_path)["env"]
    merged = {**os.environ, **env}                                 # exactly what workers.run() builds
    assert merged["GITHUB_PERSONAL_ACCESS_TOKEN"] == "" and merged["GH_TOKEN"] == ""


@pytest.mark.skipif(shutil.which("gh") is None, reason="gh not installed")
def test_gh_under_worker_env_has_no_logged_in_account_and_cannot_call_the_api(cfg, tmp_path):
    """Read-only behaviour check: `gh auth status` / `gh api` (GET) under the isolated env. No write is attempted."""
    env = {**os.environ, **build_launch(cfg, WorkerSession.start(cfg, "claude_code", "coder"), "p", tmp_path)["env"]}
    st = subprocess.run(["gh", "auth", "status"], env=env, capture_output=True, text=True, timeout=30)
    assert "Logged in" not in (st.stdout + st.stderr)
    api = subprocess.run(["gh", "api", "rate_limit"], env=env, capture_output=True, text=True, timeout=30)
    assert api.returncode != 0


def test_interactive_gh_login_is_untouched_by_launch_building(cfg, tmp_path, monkeypatch):
    monkeypatch.delenv("GH_CONFIG_DIR", raising=False)
    build_launch(cfg, WorkerSession.start(cfg, "claude_code", "coder"), "p", tmp_path)
    assert "GH_CONFIG_DIR" not in os.environ                       # isolation lives only in the launch env


# ------------------------------------------------------------ GitHub MCP record
def test_github_mcp_is_read_only_interactive_and_never_launched_into_workers(cfg):
    g = cfg.mcp["tools"]["github_mcp"]
    assert g["health"] == "ok" and g["write_capable"] is False and "launch" not in g
    assert "github_mcp" not in {n for names in cfg.mcp["exposure"].values() for n in names}
    assert "github-mcp-pat" in json.dumps(g)                       # Keychain item NAME only
    assert not re.search(r"(ghp_|github_pat_|gho_)[A-Za-z0-9_]{10,}", json.dumps(g))


# ------------------------------------------------------------ Orchestra progressive exposure
def _gen():
    spec = importlib.util.spec_from_file_location("gen_orchestra_index", REPO_ROOT / "scripts" / "gen_orchestra_index.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@pytest.mark.skipif(not Path("~/.orchestra/skills").expanduser().is_dir(), reason="Orchestra tree not present")
def test_orchestra_index_is_complete_and_current():
    g = _gen()
    text, n = g.build()
    assert (REPO_ROOT / "skills" / "orchestra-index" / "SKILL.md").read_text() == text
    assert n >= 80 and text.count("\n- **") == n                   # every skill indexed exactly once


def test_orchestra_index_is_a_single_small_standing_description():
    head = (REPO_ROOT / "skills" / "orchestra-index" / "SKILL.md").read_text().split("---")[1]
    desc = re.search(r'description:\s*"(.+)"', head).group(1)
    assert len(desc) < 120                                         # one short line instead of ~91 descriptions


# ------------------------------------------------------------ vendored Ponytail + locks
def test_ponytail_vendored_skills_match_the_lock_and_carry_no_hooks():
    lock = json.loads((REPO_ROOT / "scripts" / "runtime" / "skills.lock.json").read_text())["ponytail"]
    assert lock["commit"] == "16352ac229eb08a9598dcae48fe9f2b342567d86" and lock["tag"] == "v5.3.2"
    for rel, want in lock["sha256"].items():
        assert hashlib.sha256((REPO_ROOT / rel).read_bytes()).hexdigest() == want
    for name in ("ponytail", "ponytail-review"):
        d = REPO_ROOT / "skills" / name
        assert sorted(x.name for x in d.iterdir()) == ["SKILL.md"]
    assert not (REPO_ROOT / "skills" / "ponytail" / "hooks").exists()


def test_markitdown_lock_is_hash_pinned():
    lock = (REPO_ROOT / "scripts" / "runtime" / "markitdown.lock").read_text()
    pins = re.findall(r"^([A-Za-z0-9_.-]+)==", lock, re.M)
    assert "markitdown" in pins and re.search(r"^markitdown==0\.1\.9\b", lock, re.M)
    assert lock.count("--hash=sha256:") >= len(pins)


def test_repomix_runtime_is_exactly_pinned_without_install_scripts():
    d = REPO_ROOT / "scripts" / "runtime" / "repomix"
    assert json.loads((d / "package.json").read_text())["dependencies"] == {"repomix": "1.18.1"}
    pkgs = json.loads((d / "package-lock.json").read_text())["packages"]
    assert pkgs["node_modules/repomix"]["version"] == "1.18.1"
    assert not [k for k, v in pkgs.items() if v.get("hasInstallScript")]


def test_runtime_wrappers_are_executable_and_refuse_root_by_construction():
    for n in ("markitdown", "repomix"):
        w = REPO_ROOT / "bin" / n
        assert os.access(w, os.X_OK) and "refusing to run as root" in w.read_text()


# ------------------------------------------------------------ GitHub fails closed for dispatched workers
ALL = ["claude-code", "codex", "serena", "context7", "playwright", "github-mcp", "gh-cli", "repomix", "markitdown"]


def _plan_for(cfg, reg, caps, **ov):
    over = {pid: dict(ALL_OK) for pid in ALL}
    over.update(ov)
    return CP.plan_for(cfg, caps, overrides=over, registry=reg)


def test_github_tasks_fail_closed_for_dispatched_workers_with_everything_healthy(cfg, reg):
    pl = _plan_for(cfg, reg, ["devops.github"])
    assert pl.status == "blocked" and pl.eligible_executors == [] and pl.executor is None
    assert "integration-undeliverable" in pl.rejected_executors["claude-code"].reasons


def test_github_mcp_stays_healthy_adopted_and_registry_facts_are_unchanged(cfg, reg):
    """Fail-closed is a deliverability rule, not a global 'broken' mark: pure registry planning still selects it."""
    assert reg.get("github-mcp").adoption == "adopted"
    assert dict(reg.get("claude-code").integrations)["github-mcp"] == "supported"
    raw = _plan(reg, ["devops.github"])
    assert raw.tools == {"devops.github": "github-mcp"} and raw.tool_fallbacks == {"devops.github": ["gh-cli"]}


def test_gh_cli_is_never_a_worker_fallback(cfg, reg):
    pl = _plan_for(cfg, reg, ["devops.github"], **{"github-mcp": {"health": "unhealthy"}})
    assert pl.eligible_executors == [] and pl.tools == {}


def test_worker_deliverable_predicate_follows_launch_and_deny_config(cfg, reg):
    d = CP.worker_deliverable(cfg)
    cc = reg.get("claude-code")
    assert d(cc, reg.get("serena")) and d(cc, reg.get("context7")) and d(cc, reg.get("playwright"))
    assert not d(cc, reg.get("github-mcp"))                       # no launch in mcp.yaml
    assert not d(cc, reg.get("gh-cli")) and not d(reg.get("codex"), reg.get("gh-cli"))   # withheld from every worker
    assert cfg.workers["withheld_executables"] == ["gh"]
    assert d(cc, reg.get("repomix")) and d(cc, reg.get("markitdown"))


def test_every_supported_mcp_without_a_launch_is_reported_undeliverable(cfg, reg):
    """`supported` + no launch is exactly the silent-drop trap selected_mcp() has; the predicate must catch all of it."""
    d = CP.worker_deliverable(cfg)
    for ex in reg.executors():
        for tool_id, state in ex.integrations:
            p = reg.providers.get(tool_id)
            if state != "supported" or p is None or p.kind != "mcp":
                continue
            spec = cfg.mcp["tools"].get((p.config_ref or "").split(".", 1)[-1]) or {}
            assert ("launch" in spec) == d(ex, p), f"{ex.id}/{tool_id}"


def test_worker_deny_list_does_not_reach_interactive_settings(cfg, tmp_path):
    """The gh/security patterns travel only in the per-launch --disallowedTools argv, never in a settings file."""
    launch = build_launch(cfg, WorkerSession.start(cfg, "claude_code", "coder"), "p", tmp_path)
    assert "--disallowedTools" in launch["argv"] and "--settings" not in launch["argv"]
    assert not any("settings" in str(f) for f in launch["files"].values())
