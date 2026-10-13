"""Deterministic pre-model rule: does this request clearly mutate a repository?

Pure function of (rules, text); rules live in config/routing.yaml `intent_rules`.
It only decides whether Hermes should preload `agent-os-orchestrate`. It never
launches a worker: execution still goes Hermes -> agent-os-orchestrate ->
`agentos dispatch` -> worker. Conservative by design: anything not clearly a
mutation request is NOT forced and Hermes behaves as before.

Boundary (all required, per clause; clauses split on . ; ! ? , newline, " and ", " then "):
  1. mutation verb in imperative position (first word after optional polite prefix);
  2. a code/repo target in the SAME clause (config word or a path/`code` token);
  3. no clause of the request opens with a read-only/question lead
     (explain, review, what, how, find, ...). Mixed requests are not forced.
Negation is clause-local: a clause opening with "do not"/"don't"/"never" is a constraint
("do not modify the test"). It is never a mutation and never a request-wide veto, so
"fix the bug and do not modify the test" still forces via its own mutation clause.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from .config import Config

_SPLIT = re.compile(r"\.(?=\s|$)|[;!?,\n]+|\s+(?:and|then|but)\s+", re.I)
_PATHLIKE = re.compile(r"`[^`]+`|[\w./-]+\.(?:py|js|ts|tsx|go|rs|java|rb|sh|ya?ml|json|toml|md)\b|\w+/[\w./-]+")
_WORD = re.compile(r"[a-z0-9_']+")
# A clause opening with one of these is a negated constraint ("do not modify the test"):
# clause-local, so it neither counts as a mutation nor vetoes the rest of the request.
_NEG_FIRST = {"don't", "dont", "never", "doesn't", "didn't"}


@dataclass
class IntentDecision:
    force: bool
    skill: str | None
    reason: str
    verb: str | None = None
    target: str | None = None
    clause: str | None = None
    rules_version: int | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _strip_prefix(clause: str, prefixes: list[str]) -> str:
    s, changed = clause.strip().lower(), True
    while changed:
        changed = False
        for p in sorted(prefixes, key=len, reverse=True):
            if s == p or s.startswith(p + " "):
                s, changed = s[len(p):].strip(), True
    return s


def classify(rules: dict, text: str) -> IntentDecision:
    v, skill = rules.get("version"), rules["skill"]
    verbs, leads = set(rules["mutation_verbs"]), set(rules["read_only_leads"])
    targets = set(rules["code_targets"])
    clauses = [c for c in _SPLIT.split(text or "") if c and c.strip()]
    if not clauses:
        return IntentDecision(False, None, "empty request", rules_version=v)

    hit = None
    for raw in clauses:
        body = _strip_prefix(raw, rules["polite_prefixes"])
        words = _WORD.findall(body)
        if not words:
            continue
        if words[0] in _NEG_FIRST or (words[0] in ("do", "does", "did") and words[1:2] == ["not"]):
            continue
        if words[0] in leads:
            return IntentDecision(False, None, f"read-only/question lead '{words[0]}'",
                                  clause=raw.strip(), rules_version=v)
        if hit is None and words[0] in verbs:
            target = next((w for w in words[1:] if w in targets), None) or \
                     next(iter(_PATHLIKE.findall(body)), None)
            if target:
                hit = (words[0], target, raw.strip())
    if not hit:
        return IntentDecision(False, None, "no imperative mutation verb with a code/repo target",
                              rules_version=v)
    return IntentDecision(True, skill, "mutation verb + code target, no read-only lead",
                          verb=hit[0], target=hit[1], clause=hit[2], rules_version=v)


def decide(cfg: Config, text: str) -> IntentDecision:
    return classify(cfg.routing["intent_rules"], text)
