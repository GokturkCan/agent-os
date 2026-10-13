"""Deterministic health check for the Mac control plane.

FAIL only for things that break the control plane. The MSI being absent is
INFO by design (never a boot dependency). Conflicts with the frozen
architecture are WARN so a human can decide.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import yaml

from . import config as C
from .knowledge import GateError, Vault
from .resources import probe_node
from .selfimprove import verify_manifest

PASS, WARN, FAIL, INFO = "PASS", "WARN", "FAIL", "INFO"


def _git(*args) -> str:
    r = subprocess.run(["git", "-C", str(C.REPO_ROOT), *args], capture_output=True, text=True)
    return r.stdout.strip()


def run_checks(cfg: C.Config | None = None) -> list[dict]:
    out: list[dict] = []

    def add(name, status, detail=""):
        out.append({"check": name, "status": status, "detail": detail})

    try:
        cfg = cfg or C.load()
        errs = C.validate(cfg)
        add("config.valid", FAIL if errs else PASS, "; ".join(errs[:5]))
    except Exception as exc:  # config unreadable -> nothing else is meaningful
        add("config.load", FAIL, repr(exc))
        return out

    try:
        from . import capability_registry
        reg = capability_registry.load(cfg)
        add("capabilities.registry", PASS, f"{len(reg.providers)} providers, {len(reg.capabilities)} "
            "capabilities registered (registration only; `agentos capabilities check` probes)")
    except Exception as exc:  # reported, never fatal to the rest of the health run
        add("capabilities.registry", FAIL, str(exc)[:300])

    remotes = _git("remote")
    add("repo.no_remote", WARN if remotes else PASS, remotes or "no git remote (expected)")
    add("repo.branch", INFO, _git("branch", "--show-current"))

    try:
        drift = verify_manifest(cfg.root)
        add("policy.protected_manifest", FAIL if drift else PASS,
            ("drift: " + ", ".join(drift)) if drift else "protected policy/eval files match reviewed manifest")
    except FileNotFoundError:
        add("policy.protected_manifest", WARN, "evals/protected-manifest.json missing")

    # SecondBrain
    try:
        v = Vault(cfg)
        doc = v.doctor()
        add("secondbrain.doctor", PASS if doc.get("ok") else FAIL, str(doc.get("checks")))
        lint = v.lint().get("summary", {})
        n = lint.get("issues_found")
        add("secondbrain.lint", PASS if n == 0 else WARN, f"issues_found={n} pages={lint.get('pages_scanned')}")
        for key in ("raw_manifest", "source_ledger", "claim_ledger"):
            p = v.root / cfg.knowledge["paths"][key]
            add(f"secondbrain.{key}", PASS if p.exists() else FAIL, str(p))
    except GateError as exc:
        add("secondbrain.engine", FAIL, str(exc))

    # Hermes (read-only inspection; never modified by agent-stack)
    hermes_cfg = Path.home() / ".hermes" / "config.yaml"
    add("hermes.binary", PASS if shutil.which("hermes") else FAIL, shutil.which("hermes") or "missing")
    if hermes_cfg.exists():
        h = yaml.safe_load(hermes_cfg.read_text()) or {}
        mem = h.get("memory", {})
        add("hermes.memory_disabled",
            PASS if mem.get("memory_enabled") is False and mem.get("user_profile_enabled") is False else FAIL,
            f"memory_enabled={mem.get('memory_enabled')} user_profile_enabled={mem.get('user_profile_enabled')}")
        default = (h.get("model") or {}).get("default")
        mstat = cfg.models["models"].get(default, {}).get("status")
        add("hermes.default_model_policy", WARN if mstat in ("disabled", "rejected") else PASS,
            f"Hermes default model {default!r} has agent-stack status {mstat!r}")
        add("hermes.fallback_model", PASS if h.get("fallback_model") else WARN,
            "configured" if h.get("fallback_model") else "no fallback_model — provider outage stops Hermes")
        from . import hermes_bridge as hb
        add("hermes.agentos_skills_wired", PASS if hb.is_wired(h) else WARN,
            "skills.external_dirs loads ~/agent-stack/skills" if hb.is_wired(h)
            else "pending approval: skills.external_dirs does not include ~/agent-stack/skills "
                 "(see docs/hermes-integration.md)")
        ok, detail = hb.probe_ok(hb.probe())
        add("hermes.agentos_skills_valid", PASS if ok else FAIL, detail)
        ok, detail = hb.entrypoint_status()
        add("hermes.canonical_entrypoint", PASS if ok else FAIL, f"{hb.CANONICAL_ENTRYPOINT}: {detail}")
        bare = hb.find_bare_invocations()
        add("hermes.bare_invocations", WARN if bare else PASS,
            f"bare hermes invocations in Agent OS files: {bare}" if bare
            else "no bare `hermes chat` in Agent OS scripts/docs")
        add("hermes.bare_chat_noncanonical", INFO,
            "a bare `hermes chat` stays possible but bypasses the deterministic preload; "
            "use bin/hermes-agentos for Agent OS work")
        direct = hb.direct_worker_skills_enabled(h)
        add("hermes.direct_worker_skills", WARN if direct else PASS,
            (f"bundled skills {direct} let Hermes launch workers without agentos policy; "
             "recommended: skills.disabled") if direct else "direct worker-launch skills disabled")
    else:
        add("hermes.config", FAIL, "~/.hermes/config.yaml missing")

    for name, spec in cfg.workers["workers"].items():
        b = spec.get("binary")
        if not b or spec.get("status") not in C.USABLE:
            continue
        found = shutil.which(b) or (Path(C.expand(b)).exists() and str(C.expand(b)))
        add(f"worker.{name}", PASS if found else WARN, found or f"{b} not found")

    for name, t in cfg.mcp["tools"].items():
        if t.get("kind") == "mcp" and t.get("status") in C.USABLE and t.get("health") not in (None, "ok"):
            add(f"mcp.{name}", WARN, f"health={t.get('health')} {t.get('note', '')[:120]}")

    msi = probe_node(cfg, "msi")
    add("node.msi", INFO, f"reachable={msi['reachable']} ({msi['reason']}); not boot-critical")
    add("node.mac", PASS, "control plane (this host)")

    du = shutil.disk_usage(str(Path.home()))
    free_gb = du.free / 2**30
    add("disk.free", PASS if free_gb > 20 else WARN, f"{free_gb:.1f} GiB free")
    return out


def summarize(results: list[dict]) -> int:
    for r in results:
        print(f"[{r['status']:4}] {r['check']:34} {r['detail']}")
    fails = sum(r["status"] == FAIL for r in results)
    warns = sum(r["status"] == WARN for r in results)
    print(f"\n{len(results)} checks: {fails} FAIL, {warns} WARN")
    return 1 if fails else 0
