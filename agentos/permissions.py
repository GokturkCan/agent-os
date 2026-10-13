"""Capability checks for workers and protected-policy guards.

A worker's effective grants come only from its active profile in
config/capabilities.yaml. Escalation needs an operator grant record carrying
a human approval reference; never-grantable capabilities can never be held.
Every denial is returned with a reason so callers can log it to telemetry.
"""
from __future__ import annotations

import fnmatch
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .config import REPO_ROOT, Config

# Paths no worker / self-improvement candidate may modify (repo-relative).
PROTECTED_POLICY_PATHS = (
    "config/permissions.yaml",
    "config/capabilities.yaml",
    "config/promotion.yaml",
    "CLAUDE.md",
    "evals/**",
    "agentos/permissions.py",
    "agentos/selfimprove.py",
    # Worker execution / tool-exposure policy and the code that enforces it at launch.
    # config/routing.yaml and agentos/router.py stay unprotected on purpose: they are the
    # tunable surface self-improvement candidates may change (the human-approval risk gate in
    # routing.yaml is held by config.validate + a pinned eval instead).
    "config/workers.yaml",
    "config/mcp.yaml",
    "config/capability_registry.yaml",
    "agentos/workers.py",
    "agentos/githooks/**",
)


def is_protected(rel_path: str) -> bool:
    rel_path = rel_path.removeprefix("./")
    return any(fnmatch.fnmatch(rel_path, pat) for pat in PROTECTED_POLICY_PATHS)


class PermissionDenied(Exception):
    pass


@dataclass
class WorkerSession:
    cfg: Config
    worker: str
    profile: str
    audit: list = field(default_factory=list)

    @classmethod
    def start(cls, cfg: Config, worker: str, profile: str | None = None) -> "WorkerSession":
        spec = cfg.workers["workers"][worker]
        profile = profile or spec["default_profile"]
        if profile not in spec.get("allowed_profiles", []):
            raise PermissionDenied(f"{worker} may not run under profile {profile}")
        prof = cfg.capabilities["profiles"][profile]
        if prof.get("human_only"):
            raise PermissionDenied(f"profile {profile} is human-only")
        return cls(cfg, worker, profile)

    @property
    def grants(self) -> set[str]:
        return set(self.cfg.capabilities["profiles"][self.profile]["grants"])

    def check(self, capability: str) -> bool:
        never = set(self.cfg.capabilities["never_grantable"])
        if capability in never:
            ok, why = False, "never_grantable"
        elif capability in self.grants:
            ok, why = True, "granted"
        else:
            ok, why = False, f"not in profile {self.profile}"
        self.audit.append({"capability": capability, "allowed": ok, "reason": why})
        return ok

    def require(self, capability: str):
        if not self.check(capability):
            raise PermissionDenied(f"{self.worker}/{self.profile}: {capability} denied "
                                   f"({self.audit[-1]['reason']})")

    def request_escalation(self, target_profile: str, grant_record: dict | None) -> "WorkerSession":
        """Switch profile only with an operator grant carrying human approval."""
        spec = self.cfg.workers["workers"][self.worker]
        if target_profile not in spec.get("allowed_profiles", []):
            raise PermissionDenied(f"{target_profile} not allowed for {self.worker}")
        if not grant_record or not grant_record.get("human_approval_ref") \
                or grant_record.get("issued_by") != "operator" \
                or grant_record.get("worker") != self.worker \
                or grant_record.get("profile") != target_profile:
            self.audit.append({"escalation": target_profile, "allowed": False,
                               "reason": "missing/invalid operator grant with human approval"})
            raise PermissionDenied("escalation requires operator grant with human approval")
        self.audit.append({"escalation": target_profile, "allowed": True,
                           "reason": grant_record["human_approval_ref"]})
        return WorkerSession(self.cfg, self.worker, target_profile, self.audit)


def write_grant(worker: str, profile: str, human_approval_ref: str,
                directory: Path | None = None) -> dict:
    rec = {"issued_by": "operator", "worker": worker, "profile": profile,
           "human_approval_ref": human_approval_ref,
           "issued_at": datetime.now(timezone.utc).isoformat()}
    d = directory or (REPO_ROOT / "state" / "approvals")
    d.mkdir(parents=True, exist_ok=True)
    (d / f"grant-{worker}-{profile}-{datetime.now(timezone.utc):%Y%m%dT%H%M%S}.json").write_text(
        json.dumps(rec, indent=2))
    return rec
