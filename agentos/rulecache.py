"""Decision -> rule cache prototype (R3.2G). Reviewed, scoped, invalidating; never silent. OPT-IN.

Pattern from kitze/unclutter (a model result becomes a reusable rule keyed by a scope incl. a policy version; failed or stale
analyses never change rules; rules can be disabled/forgotten), adapted to Agent OS review rules:

* A rule is created only as `proposed`, from an answered (non-escalated) SystemOne decision plus an evidence reference.
* Only `approved` rules apply, and approval records a named human approver. Nothing in this module approves automatically.
* The key is exact: task type, task class, the eligible option set, required capabilities, risk, a hash of the option
  metadata and a hash of the routing-relevant config files. Any difference -> no hit (re-decided normally).
* A hit is re-checked against the request's eligible options; a rule can never introduce an option.
* The store is a reviewable YAML file; `revoke` keeps the record (audit trail) and stops it applying.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from . import systemone as S

CONFIG_FILES = ("config/workers.yaml", "config/routing.yaml", "config/capability_registry.yaml", "config/providers.yaml")


def config_hash(root: str | Path) -> str:
    h = hashlib.sha256()
    for rel in sorted(str(p.relative_to(root)) for p in (Path(root) / "config").glob("*.yaml")):
        p = Path(root) / rel
        h.update(rel.encode() + b"\0" + (p.read_bytes() if p.exists() else b"<missing>") + b"\0")
    return h.hexdigest()


def key_for(request: S.SystemOneRequest, cfg_hash: str) -> dict:
    return {"task_type": request.task_type, "task_class": str(request.state.get("task_class", "")),
            "options": sorted(request.eligible_options), "capabilities": sorted(request.required_capabilities),
            "risk": request.risk,
            "option_info_sha": hashlib.sha256(json.dumps(request.option_info or {}, sort_keys=True, default=str).encode()).hexdigest()[:16],
            "config_sha": cfg_hash,
            "request_sha": hashlib.sha256(json.dumps({
                "state": dict(request.state), "resources": dict(request.resource_state),
                "cost_profile": request.cost_profile, "allow_abstain": request.allow_abstain,
                "questions": [q.__dict__ for q in request.questions],
            }, sort_keys=True, default=str).encode()).hexdigest()}


def _kid(key: dict) -> str:
    return hashlib.sha256(json.dumps(key, sort_keys=True).encode()).hexdigest()[:16]


@dataclass
class RuleCache:
    path: Path
    rules: dict = field(default_factory=dict)

    @classmethod
    def load(cls, path: str | Path) -> "RuleCache":
        p = Path(path)
        data = yaml.safe_load(p.read_text()) if p.exists() else None
        return cls(p, {r["id"]: r for r in ((data or {}).get("rules") or [])})

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("# Decision->rule cache (R3.2G prototype). Only status=approved rules apply.\n"
                             + yaml.safe_dump({"version": 1, "rules": list(self.rules.values())}, sort_keys=False))

    def propose(self, request: S.SystemOneRequest, response: S.SystemOneResponse, cfg_hash: str, evidence: str) -> dict:
        if response.escalate or not evidence:
            raise ValueError("only an answered decision with an evidence reference can be proposed")
        if len(request.questions) != 1 or request.questions[0].kind != "choose" or len(response.answers) != 1:
            raise ValueError("only one answered choice question can be proposed")
        ans = response.answers[0]
        q = request.questions[0]
        if ans.question_id != q.id or (q.options and ans.choice not in q.options):
            raise ValueError("answer does not match question scope")
        if ans.choice not in request.eligible_options:
            raise ValueError("decision outside the eligible options")
        key = key_for(request, cfg_hash)
        rid = _kid(key)
        if rid in self.rules and self.rules[rid]["status"] == "approved":
            return self.rules[rid]                         # an approved rule is never overwritten by a new proposal
        self.rules[rid] = {"id": rid, "status": "proposed", "key": key, "decision": ans.choice,
                           "provenance": {"backend": response.backend, "evidence": evidence,
                                          "confidence": ans.confidence.value, "confidence_kind": ans.confidence.kind,
                                          "proposed_at": time.strftime("%Y-%m-%dT%H:%M:%S")},
                           "approved_by": None}
        return self.rules[rid]

    def approve(self, rule_id: str, approver: str) -> dict:
        if not approver or not approver.startswith("human:") or not approver.removeprefix("human:").strip():
            raise ValueError("approval requires a named human approver (human:<name>)")
        r = self.rules[rule_id]
        r["status"], r["approved_by"] = "approved", approver
        r["provenance"]["approved_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        return r

    def revoke(self, rule_id: str, reason: str) -> None:
        self.rules[rule_id]["status"] = "revoked"
        self.rules[rule_id]["provenance"]["revoked"] = reason

    def lookup(self, request: S.SystemOneRequest, cfg_hash: str) -> dict | None:
        r = self.rules.get(_kid(key_for(request, cfg_hash)))
        if r and r["status"] == "approved" and str(r.get("approved_by", "")).startswith("human:") and str(r.get("approved_by", "")).removeprefix("human:").strip() and r["key"] == key_for(request, cfg_hash) \
                and r["decision"] in request.eligible_options:
            return r
        return None


class CachedBackend:
    """Approved rule hit -> deterministic answer (reason `policy-order`, no confidence); otherwise the inner backend."""

    def __init__(self, inner, cache: RuleCache, cfg_hash: str):
        self.inner, self.cache, self.cfg_hash = inner, cache, cfg_hash
        self.name = f"rulecache:{getattr(inner, 'name', 'inner')}"
        self.hits = self.misses = 0

    def decide(self, request: S.SystemOneRequest) -> S.SystemOneResponse:
        r = self.cache.lookup(request, self.cfg_hash)
        if r and len(request.questions) == 1 and request.questions[0].kind == "choose":
            self.hits += 1
            return S.SystemOneResponse((S.Answer(request.questions[0].id, r["decision"], S.Confidence(), "policy-order"),),
                                       False, "policy-order", self.name)
        self.misses += 1
        return self.inner.decide(request)
