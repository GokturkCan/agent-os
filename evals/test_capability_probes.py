"""Run 2 / R2.3 — availability / health / auth probes: isolated, tri-state, secret-safe, offline."""
import json
import subprocess

import pytest

from agentos import capability_probes as P
from agentos import capability_registry as R


def _p(pid="tool-x", auth="none", probe=(), kind="cli"):
    return R.Provider(id=pid, kind=kind, adoption="adopted", capabilities=("code.edit",), auth=auth,
                      probe=tuple(probe))


def _ctx(**kw):
    kw.setdefault("env", {})
    kw.setdefault("which", lambda name: None)
    return P.ProbeContext(**kw)


def test_unprobed_is_unknown_not_unhealthy():
    r = P.probe_provider(_p(probe=[{"type": "declared"}]), _ctx())
    assert (r.installed, r.available, r.health) == ("unknown", "unknown", "unknown")
    assert r.auth == "not_required" and r.probed is False


def test_executable_presence_does_not_imply_health():
    present = P.probe_provider(_p(probe=[{"type": "executable", "target": "tool"}]),
                               _ctx(which=lambda n: f"/bin/{n}"))
    assert (present.installed, present.available, present.health) == ("present", "present", "unknown")
    absent = P.probe_provider(_p(probe=[{"type": "executable", "target": "tool"}]), _ctx())
    assert (absent.installed, absent.available) == ("absent", "absent")


def test_deep_health_check_uses_exit_code_only():
    spec = [{"type": "executable", "target": "tool", "health_args": ["--version"]}]
    ok = lambda argv: subprocess.CompletedProcess(argv, 0, stdout="SECRET-OUTPUT", stderr="")
    bad = lambda argv: subprocess.CompletedProcess(argv, 3, stdout="", stderr="boom")
    which = lambda n: f"/bin/{n}"
    assert P.probe_provider(_p(probe=spec), _ctx(which=which, deep=False, run=ok)).health == "unknown"
    r = P.probe_provider(_p(probe=spec), _ctx(which=which, deep=True, run=ok))
    assert r.health == "healthy" and "SECRET-OUTPUT" not in json.dumps(r.to_dict())
    assert P.probe_provider(_p(probe=spec), _ctx(which=which, deep=True, run=bad)).health == "unhealthy"

    def hang(argv):
        raise subprocess.TimeoutExpired(argv, 5)
    assert P.probe_provider(_p(probe=spec), _ctx(which=which, deep=True, run=hang)).health == "unhealthy"


def test_auth_required_vs_present_distinguished_and_value_never_leaks():
    secret = "sk-live-THIS-IS-A-SECRET-VALUE"
    spec = [{"type": "env_auth", "env": ["MY_TOKEN"]}]
    have = P.probe_provider(_p(auth="required", probe=spec), _ctx(env={"MY_TOKEN": secret}))
    miss = P.probe_provider(_p(auth="required", probe=spec), _ctx(env={}))
    assert (have.auth, miss.auth) == ("present", "missing")
    blob = json.dumps(have.to_dict()) + repr(have)
    assert secret not in blob and "MY_TOKEN" in blob                # name only, never the value
    unprobed = P.probe_provider(_p(auth="required", probe=[{"type": "declared"}]), _ctx())
    assert unprobed.auth == "unknown"                                # unknown != missing


def test_failing_probe_is_isolated(monkeypatch):
    def boom(spec, ctx):
        raise RuntimeError("probe exploded")
    monkeypatch.setitem(P.PROBES, "path", boom)
    p = _p(probe=[{"type": "path", "paths": ["/x"]}, {"type": "executable", "target": "tool"}])
    r = P.probe_provider(p, _ctx(which=lambda n: "/bin/tool"))
    assert r.errors == ("path: RuntimeError",) and r.installed == "present"


def test_one_failed_provider_does_not_break_probe_all(cfg, monkeypatch):
    reg = R.load(cfg)
    monkeypatch.setitem(P.PROBES, "claude_plugin", lambda s, c: 1 / 0)
    res = P.probe_all(reg, _ctx(cfg=cfg))
    assert set(res) == set(reg.providers)
    assert res["superpowers"].errors == ("claude_plugin: ZeroDivisionError",)
    assert res["superpowers"].available == "unknown"


def test_negative_evidence_wins_when_merging():
    p = _p(probe=[{"type": "executable", "target": "a"}, {"type": "path", "paths": ["/definitely/not/here"]}])
    r = P.probe_provider(p, _ctx(which=lambda n: "/bin/a"))
    assert r.available == "absent"


def test_claude_plugin_probe(tmp_path):
    f = tmp_path / "installed_plugins.json"
    f.write_text(json.dumps({"plugins": {"superpowers@claude-plugins-official": [{}]}}))
    hit = P.probe_provider(_p(probe=[{"type": "claude_plugin", "target": "superpowers"}]), _ctx(plugins_file=f))
    miss = P.probe_provider(_p(probe=[{"type": "claude_plugin", "target": "ponytail"}]), _ctx(plugins_file=f))
    assert (hit.available, miss.available) == ("present", "absent")
    nofile = P.probe_provider(_p(probe=[{"type": "claude_plugin", "target": "x"}]),
                              _ctx(plugins_file=tmp_path / "nope.json"))
    assert nofile.available == "unknown"


def test_config_health_maps_last_observed_state(cfg):
    gh = P.probe_provider(_p(auth="required", probe=[{"type": "config_health", "ref": "mcp.github_mcp"}]),
                          _ctx(cfg=cfg))
    assert gh.health == "unhealthy"                                   # mcp.yaml: health=failing (401)
    pm = R.Provider(id="pm", kind="mcp", adoption="adopted", capabilities=("code.edit",), auth="required",
                    probe=({"type": "config_health", "ref": "mcp.postman"},))
    assert P.probe_provider(pm, _ctx(cfg=cfg)).auth == "missing"      # needs_auth
    ok = P.probe_provider(_p(probe=[{"type": "config_health", "ref": "mcp.serena"}]), _ctx(cfg=cfg))
    assert (ok.health, ok.installed) == ("healthy", "present")


def test_service_probe_makes_no_network_call():
    r = P.probe_provider(_p(probe=[{"type": "service", "url": "https://example.invalid"}]), _ctx())
    assert r.available == "unknown" and "deferred" in r.details[0]


def test_overrides_and_static_probes_are_validated(cfg):
    reg = R.load(cfg)
    res = P.probe_all(reg, _ctx(cfg=cfg), overrides={"serena": {"available": "absent"}})
    assert res["serena"].available == "absent" and "override" in res["serena"].details
    with pytest.raises(ValueError):
        P.probe_all(reg, _ctx(cfg=cfg), overrides={"serena": {"available": "kinda"}})
    st = P.static_probes(reg, default={"available": "present", "health": "healthy", "auth": "present"})
    assert st["serena"].auth == "not_required" and st["claude-code"].auth == "present"


def test_live_registry_probe_is_offline_and_complete(cfg):
    reg = R.load(cfg)
    res = P.probe_all(reg, P.ProbeContext(cfg=cfg))                   # real which/paths, no subprocess/network
    assert set(res) == set(reg.providers) and not any(r.errors for r in res.values())
    for r in res.values():
        assert r.installed in P.PRESENCE and r.health in P.HEALTH and r.auth in P.AUTH_STATES
