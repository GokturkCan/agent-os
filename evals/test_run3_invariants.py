"""Run 3 release invariants (integration): what must stay true however the Run 3 branches were combined.

These pin the SHIPPED posture (fail closed, nothing neural or remote active, experimental modules not wired). Changing any of them is a
protected-policy decision that needs explicit human approval; this file is part of the protected delta (evals/**).
"""
import re
import subprocess
from pathlib import Path

import pytest

from agentos import compute, systemone
from agentos import config as C
from agentos.permissions import is_protected

ROOT = C.REPO_ROOT
EXPERIMENTAL = ("contextgate", "toolpruner", "wakegate", "retrieval_select", "rulecache")
OPT_IN_ENTRYPOINTS = {"module_eval.py"} | {f"{m}.py" for m in EXPERIMENTAL}


@pytest.fixture(scope="module")
def cfg():
    return C.load()


def test_systemone_production_posture_is_null_and_empty(cfg):
    assert cfg.routing["systemone"] == {"backend": "null"}
    assert cfg.models["tiers"]["fastgate"]["model"] is None
    assert cfg.systemone["activation"] == {"production_backends": [], "fastgate_models": []}
    assert C.activation_allowlists(cfg) == ([], [])
    assert isinstance(systemone.resolve_backend("null", cfg), systemone.NullBackend)


def test_laya_is_a_candidate_not_a_usable_model(cfg):
    assert cfg.models["models"]["laya-mlx"]["status"] == "candidate"
    assert "candidate" not in C.USABLE


def test_compute_is_disabled_and_empty(cfg):
    assert compute.offerings(cfg) == {} and compute.authorizations(cfg) == []
    assert all(compute.node_enabled(cfg, n) is False for n in (cfg.resources.get("nodes") or {}))
    assert compute.section(cfg)["nodes"]["msi"] == {"enabled": False, "endpoint_ref": None, "auth_ref": None,
                                                    "declared_resources": {"vram_mb": 8192, "ram_mb": 32768}}
    assert is_protected("config/compute.yaml")


def test_security_sensitive_node_settings_are_not_in_the_tunable_file(cfg):
    assert not any("compute" in n for n in (cfg.resources.get("nodes") or {}).values())
    assert not is_protected("config/resources.yaml")                  # tunable on purpose; so it must hold no compute settings


def test_no_automatic_remote_execution_path():
    # CN-1 ships a contract and a mock client protocol only: no network/SSH client in the production package.
    banned = re.compile(r"\b(import|from)\s+(socket|http\.client|urllib\.request|requests|httpx|paramiko|fabric)\b|\bssh\b.*\bsubprocess\b|"
                        r"subprocess\.\w+\(\s*\[\s*[\"']ssh[\"']")
    for name in ("compute.py", "compute_jobs.py"):
        text = (ROOT / "agentos" / name).read_text()
        assert not banned.search(text), name


def test_research_and_model_launching_code_is_outside_the_production_package():
    pkg = ROOT / "agentos"
    assert not (pkg / "openjev_opt.py").exists() and not (pkg / "systemone_workers" / "openjev_scorer.py").exists()
    assert (ROOT / "scripts" / "openjev" / "openjev_opt.py").exists()


def test_experimental_efficiency_modules_are_not_wired_into_runtime():
    for path in (ROOT / "agentos").glob("*.py"):
        if path.name in OPT_IN_ENTRYPOINTS:
            continue
        text = path.read_text()
        for m in EXPERIMENTAL:
            assert not re.search(rf"(from\s+\.\s+import[^\n]*\b{m}\b|from\s+\.{m}\s+import|import\s+agentos\.{m}\b|from\s+agentos\s+import[^\n]*\b{m}\b)", text), \
                f"{path.name} imports opt-in module {m}"
    for sub in ("bin", "skills", "agentos/githooks"):
        for f in (ROOT / sub).rglob("*"):
            if f.is_file() and f.suffix in ("", ".py", ".sh", ".md"):
                text = f.read_text(errors="ignore")
                assert not any(re.search(rf"\b{m}\b", text) for m in ("contextgate", "toolpruner", "wakegate")), f


def test_cli_research_commands_do_not_change_production_selection(cfg):
    # Research CLI paths name a backend explicitly; none of them mutates config or the production selection.
    before = (cfg.routing["systemone"], cfg.systemone["activation"])
    assert C.load().routing["systemone"] == before[0] and C.load().systemone["activation"] == before[1]
    cli = (ROOT / "agentos" / "cli.py").read_text()
    for banned in ("production_backends", "fastgate_models"):
        assert banned not in cli                                      # the CLI never edits the activation allowlists


def test_hermes_remains_the_only_orchestrator():
    text = (ROOT / "CLAUDE.md").read_text()
    assert "Hermes = WHO runs/orchestrates the system" in text
    assert not (ROOT / "agentos" / "orchestrator.py").exists()


def test_no_private_absolute_paths_or_weights_in_tracked_source():
    files = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split("\n")
    for f in filter(None, files):
        assert not f.endswith((".safetensors", ".gguf", ".onnx", ".pt", ".pth", ".bin")) or f.startswith("bin/"), f
    pat = re.compile(r"/Users/[A-Za-z0-9._-]+/")
    for f in filter(None, files):
        if f.endswith((".py", ".yaml", ".yml", ".md", ".sh", ".json")) and not f.startswith(("audit/", "evals/data/")):
            p = ROOT / f
            if p.is_file():
                assert not pat.search(p.read_text(errors="ignore")), f"private absolute path in {f}"
