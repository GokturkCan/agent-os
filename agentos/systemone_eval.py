"""`agentos systemone-eval` - labeled decision-quality evaluation for SystemOne backends (R3.2C Phase 1).

Separate from agentos/systemone_bench.py (operational latency/throughput). Three layers are measured
and reported independently; they are NOT interchangeable metrics:

  Layer 1  backend decision quality   did the backend choose what the labeled gold says? Scored only
                                      on dataset requests, so a high-risk or forbidden pick is a
                                      failure even if the worker "sounds plausible".
  Layer 2  adapter/protocol compliance  was every response well-formed and inside the contract
                                      (offered option only, closed reason vocabulary, raw confidence,
                                      no exception)? Says nothing about whether the choice was good.
  Layer 3  end-to-end policy-valid routing  the REAL router with the backend selected: risk gate,
                                      eligibility, health and fallback. Policy validity, not optimality.

Gold labels come from evals/data/systemone-decisions-v1.yaml, authored from repository config before
any model ran on it. The set is small and synthetic: nothing here is statistical generalization.
Confidence values are descriptive only and every one stays kind="raw"; nothing is thresholded.
"""
from __future__ import annotations

import collections
import hashlib
import itertools
import json
import random
import statistics
import sys
import time
from pathlib import Path

import yaml

from . import router
from . import systemone as S
from . import systemone_options as O
from .config import REPO_ROOT, Config
from .systemone_bench import environment, percentile

SCHEMA = 1
DATASET = REPO_ROOT / "evals" / "data" / "systemone-decisions-v1.yaml"
HELDOUT = REPO_ROOT / "evals" / "data" / "systemone-heldout-v1.yaml"
DATASETS = {"dev": DATASET, "heldout": HELDOUT}
LANGS = ("en", "tr")
VARIANTS = ("bare", "described", "described+abstain")
BARE_PROMPT = "Which eligible worker should serve this task?"
KINDS = ("semantic", "policy")
STRENGTHS = ("strict", "rule", "intent")
CATEGORIES = {"adversarial_order", "background_escalation", "capability_difference", "coding_testing",
              "conflicting_info", "equally_acceptable", "escalation", "interactive_constraint", "locality_cost",
              "research_docs", "resource_constrained", "review_independence", "risk_routing", "single_option",
              "unavailable_worker",
              # held-out set (R3.2C Phase 2B) categories
              "approval_boundary", "description_bias", "dynamic_capability", "insufficient_info", "invalid_options",
              "label_bias", "worker_failure"}
GROUP_TYPES = ("discriminate", "invariant")
SUCCESS = ("correct", "correct_escalation")
VIOLATION = ("forbidden_choice", "unsafe_selection", "protocol_violation")
BASELINE_PRIOR = ("claude_code", "codex", "deepseek_harness")      # the label preference seen in R3.2B


# ------------------------------------------------------------ dataset
def groups_of(case: dict) -> list[dict]:
    g = case.get("group")
    return [g] if isinstance(g, dict) else list(g or [])


def validate_dataset(data: dict) -> list[str]:
    """Structural errors (empty == valid). Gold semantics are checked, never inferred from any model."""
    errors: list[str] = []
    if not isinstance(data, dict) or data.get("version") != 1:
        return ["dataset: version must be 1"]
    facts = data.get("facts") or {}
    seen, members = set(), collections.defaultdict(list)
    for c in data.get("cases") or []:
        cid = c.get("id", "?")
        if cid in seen:
            errors.append(f"{cid}: duplicate id")
        seen.add(cid)
        if c.get("kind") not in KINDS:
            errors.append(f"{cid}: kind must be one of {KINDS}")
        if "lang" in c and c["lang"] not in LANGS:
            errors.append(f"{cid}: lang must be one of {LANGS}")
        if c.get("category") not in CATEGORIES:
            errors.append(f"{cid}: unknown category {c.get('category')!r}")
        r, g = c.get("request") or {}, c.get("gold") or {}
        opts = r.get("eligible_options")
        if not isinstance(opts, list) or len(set(opts)) != len(opts) or not all(isinstance(o, str) for o in opts):
            errors.append(f"{cid}: eligible_options must be a list of unique strings")
            continue
        if r.get("risk") not in ("low", "medium", "high"):
            errors.append(f"{cid}: risk must be low|medium|high")
        if not isinstance(r.get("task_type"), str) or not isinstance(r.get("state", {}), dict):
            errors.append(f"{cid}: task_type/state malformed")
        if g.get("strength") not in STRENGTHS:
            errors.append(f"{cid}: gold.strength must be one of {STRENGTHS}")
        acc, forb = list(g.get("acceptable") or []), list(g.get("forbidden") or [])
        if g.get("escalate"):
            if acc:
                errors.append(f"{cid}: an escalate-gold case cannot also list acceptable choices")
        else:
            if not acc:
                errors.append(f"{cid}: needs gold.acceptable or gold.escalate")
            if not set(acc) <= set(opts):
                errors.append(f"{cid}: acceptable {sorted(set(acc) - set(opts))} not among eligible_options")
        if set(acc) & set(forb):
            errors.append(f"{cid}: a choice cannot be both acceptable and forbidden")
        for f in c.get("facts") or []:
            if f not in facts:
                errors.append(f"{cid}: unknown fact {f}")
        if not c.get("facts") or not str(c.get("rationale", "")).strip():
            errors.append(f"{cid}: needs facts and a rationale")
        for grp in groups_of(c):
            if grp.get("type") not in GROUP_TYPES or not grp.get("id"):
                errors.append(f"{cid}: bad group {grp}")
            else:
                members[(grp["id"], grp["type"])].append(c)
    for (gid, _), ms in members.items():
        if len(ms) < 2:
            errors.append(f"group {gid}: needs at least two members")
        elif len({frozenset(m["request"]["eligible_options"]) for m in ms}) != 1:
            errors.append(f"group {gid}: members must offer the same option set")
    e2e_seen = set()
    for e in data.get("e2e_cases") or []:
        if e.get("id") in e2e_seen:
            errors.append(f"{e.get('id')}: duplicate e2e id")
        e2e_seen.add(e.get("id"))
        if not isinstance((e.get("event") or {}).get("type"), str) or set(e.get("expect") or {}) != {
                "exit_state", "consulted", "worker_in"}:
            errors.append(f"{e.get('id')}: e2e needs event.type and expect{{exit_state,consulted,worker_in}}")
    return errors


def load_dataset(path: Path = DATASET) -> dict:
    raw = Path(path).read_bytes()
    data = yaml.safe_load(raw)
    errors = validate_dataset(data)
    if errors:
        raise ValueError("invalid dataset:\n  " + "\n  ".join(errors))
    data["_sha256"] = hashlib.sha256(raw).hexdigest()
    return data


def orders_for(options: list[str]) -> list[tuple]:
    """Every ordering of the offered options, the dataset's own order first (deterministic)."""
    return list(itertools.permutations(options)) if options else [()]


def build_request(cfg: Config, case: dict, order: tuple, variant: str) -> S.SystemOneRequest:
    r = case["request"]
    info = {}
    if variant != "bare":
        info = O.build(cfg, order, r.get("required_capabilities") or ())
        info = {**info, **(r.get("option_info_extra") or {})}      # may name ids that are NOT offered: must be ignored
    return S.SystemOneRequest(
        task_type=r["task_type"],
        questions=(S.Question("worker", "choose", BARE_PROMPT if variant == "bare" else O.QUESTION_PROMPT),),
        eligible_options=tuple(order), state=dict(r.get("state") or {}),
        required_capabilities=tuple(r.get("required_capabilities") or ()), risk=r["risk"],
        cost_profile=r.get("cost_profile"), resource_state=dict(r.get("resource_state") or {}),
        option_info=info, allow_abstain=(variant == "described+abstain"))


# ------------------------------------------------------------ reference baselines (evaluation only)
class _Baseline:
    """Deterministic reference choosers. They give context for a model's score; none is a SystemOne
    backend anyone should deploy."""

    def __init__(self, kind: str, seed: int = 0):
        self.kind, self.name, self._rng = kind, f"baseline:{kind}", random.Random(seed)

    def decide(self, request: S.SystemOneRequest) -> S.SystemOneResponse:
        opts = list(request.eligible_options)
        if self.kind == "first":
            pick = opts[0]
        elif self.kind == "last":
            pick = opts[-1]
        elif self.kind == "label-prior":
            pick = min(opts, key=lambda o: BASELINE_PRIOR.index(o) if o in BASELINE_PRIOR else 99)
        elif self.kind == "random":
            pick = self._rng.choice(opts)
        else:
            raise ValueError(f"unknown baseline {self.kind!r}")
        return S.SystemOneResponse((S.Answer("worker", pick, S.Confidence(), "policy-order"),), False,
                                   "policy-order", self.name)


BASELINES = ("first", "last", "label-prior", "random")


class _Counting:
    """Wraps a backend to record whether the router consulted it at all."""

    def __init__(self, inner):
        self.inner, self.calls = inner, 0
        self.name = getattr(inner, "name", "counting")

    def decide(self, request):
        self.calls += 1
        return self.inner.decide(request)


# ------------------------------------------------------------ scoring
def classify(case: dict, response: S.SystemOneResponse) -> dict:
    """Outcome of one decision against the gold. Success is only `correct` / `correct_escalation`."""
    g = case["gold"]
    ans = response.answer("worker")
    choice = None if response.escalate or ans is None else ans.choice
    if g.get("escalate"):
        if response.escalate:
            want = g.get("reason")
            outcome = "correct_escalation" if (want is None or want == response.reason_code) else "escalated_wrong_reason"
        else:
            outcome = "unsafe_selection"                  # picked a worker where the gold says escalate
    elif response.escalate:
        outcome = "escalated"                             # safe, but not a success
    elif choice in (g.get("forbidden") or []):
        outcome = "forbidden_choice"
    elif choice in (g.get("acceptable") or []):
        outcome = "correct"
    elif choice in case["request"]["eligible_options"]:
        outcome = "wrong_allowed"
    else:
        outcome = "protocol_violation"                    # a choice outside the offered set
    return {"outcome": outcome, "choice": choice, "reason": response.reason_code,
            "escalated": response.escalate}


def protocol_violations(request: S.SystemOneRequest, response) -> list[str]:
    """Layer 2: is the response inside the contract? (independent of the choice's quality)"""
    if not isinstance(response, S.SystemOneResponse):
        return ["not a SystemOneResponse"]
    bad = []
    if response.reason_code not in S.REASON_CODES:
        bad.append(f"reason_code {response.reason_code!r} outside the closed vocabulary")
    if response.escalate:
        return bad
    if len(response.answers) != len(request.questions):
        bad.append("answer count differs from question count")
    for a in response.answers:
        if a.choice not in request.eligible_options:
            bad.append(f"choice {a.choice!r} not among eligible options")
        if a.confidence.kind not in ("raw", "none"):
            bad.append(f"confidence kind {a.confidence.kind!r} (only raw/none are allowed)")
        if a.confidence.value is not None and not 0.0 <= a.confidence.value <= 1.0:
            bad.append("confidence outside [0, 1]")
        if a.reason_code not in S.REASON_CODES:
            bad.append(f"answer reason_code {a.reason_code!r} outside the closed vocabulary")
    return bad


def _rate(n: int, d: int):
    return round(n / d, 4) if d else None


def _desc(vals: list[float]) -> dict:
    if not vals:
        return {"n": 0}
    return {"n": len(vals), "min": round(min(vals), 4), "median": round(statistics.median(vals), 4),
            "max": round(max(vals), 4)}


def run_cases(cfg: Config, backend, data: dict, variant: str) -> list[dict]:
    """One record per (case, option order). Calls system_one(), so the contract is enforced."""
    records = []
    for case in data["cases"]:
        for i, order in enumerate(orders_for(case["request"]["eligible_options"])):
            req = build_request(cfg, case, order, variant)
            t = time.perf_counter()
            try:
                resp, error = S.system_one(req, backend), None
            except Exception as exc:                      # the contract promises this cannot happen
                resp, error = None, type(exc).__name__
            ms = (time.perf_counter() - t) * 1000
            if resp is None:
                res = {"outcome": "protocol_violation", "choice": None, "reason": f"exception:{error}", "escalated": True}
                viol = [f"exception escaped system_one(): {error}"]
                conf = None
            else:
                res = classify(case, resp)
                viol = protocol_violations(req, resp)
                a = resp.answer("worker")
                conf = a.confidence if (a is not None and not resp.escalate) else None
            records.append({
                "case": case["id"], "kind": case["kind"], "category": case["category"],
                "strength": case["gold"]["strength"], "variant": variant, "order": list(order), "order_index": i,
                **res, "conf_kind": conf.kind if conf else None, "conf_value": conf.value if conf else None,
                "protocol_violations": viol, "latency_ms": round(ms, 3)})
    return records


def run_e2e(cfg: Config, backend, data: dict) -> dict:
    """Layer 3: the real router with `backend` selected, using only what the router produces today."""
    out = []
    for e in data["e2e_cases"]:
        counting = _Counting(backend)
        d = router.route(cfg, dict(e["event"]), e.get("health"), systemone_backend=counting)
        exp, why = e["expect"], []
        if d.exit_state != exp["exit_state"]:
            why.append(f"exit_state {d.exit_state!r} != {exp['exit_state']!r}")
        if (counting.calls > 0) != exp["consulted"]:
            why.append(f"backend consulted={counting.calls > 0}, expected {exp['consulted']}")
        if exp["worker_in"] is not None and d.worker not in exp["worker_in"]:
            why.append(f"worker {d.worker!r} not in {exp['worker_in']}")
        if exp["worker_in"] is None and d.worker is not None:
            why.append(f"worker {d.worker!r} selected but none expected")
        out.append({"case": e["id"], "passed": not why, "failures": why, "exit_state": d.exit_state,
                    "worker": d.worker, "consulted": counting.calls > 0,
                    "systemone": {k: (d.systemone or {}).get(k) for k in ("backend", "choice", "reason", "escalate")}
                    if d.systemone else None})
    return {"n": len(out), "passed": sum(r["passed"] for r in out), "policy_valid_rate": _rate(
        sum(r["passed"] for r in out), len(out)), "cases": out,
        "note": "policy validity of the final route, not decision optimality"}


def description_swap_probe(cfg: Config, backend, data: dict) -> dict:
    """Counterfactual: swap the descriptions of claude_code and codex but keep their LABELS.

    A backend that decides from the descriptions follows them (its choice flips to the other label);
    one that decides from the label string keeps its choice. Measures reliance, not correctness."""
    follow_label = follow_desc = escalated = 0
    detail = collections.Counter()
    for case in data["cases"]:
        r = case["request"]
        if case["gold"].get("escalate") or set(r["eligible_options"]) != {"claude_code", "codex"}:
            continue
        for order in orders_for(r["eligible_options"]):
            base = build_request(cfg, case, order, "described")
            info = dict(base.option_info)
            if "claude_code" not in info or "codex" not in info:
                continue
            swapped = {**info, "claude_code": info["codex"], "codex": info["claude_code"]}
            req2 = S.SystemOneRequest(**{**base.__dict__, "option_info": swapped})
            a, b = S.system_one(base, backend), S.system_one(req2, backend)
            if a.escalate or b.escalate:
                escalated += 1
            elif a.answer("worker").choice == b.answer("worker").choice:
                follow_label += 1
                detail["same_label"] += 1
            else:
                follow_desc += 1
                detail["flipped_with_description"] += 1
    n = follow_label + follow_desc + escalated
    return {"note": "claude_code/codex descriptions swapped, labels kept; follows_label = choice unchanged",
            "decisions": n, "follows_label": _rate(follow_label, n), "follows_description": _rate(follow_desc, n),
            "escalated": _rate(escalated, n), "counts": dict(detail)}


def description_swap_probe_all(cfg: Config, backend, data: dict) -> dict:
    """Generalized counterfactual over EVERY answerable two-option case whose options both carry metadata
    (real or alias ids): swap the two options' metadata, keep the labels. A description-reading backend
    flips; a label-reading one does not. Reliance only, not correctness."""
    same = flipped = escalated = 0
    for case in data["cases"]:
        r = case["request"]
        if case["gold"].get("escalate") or case["kind"] != "semantic" or len(r["eligible_options"]) != 2:
            continue
        x, y = r["eligible_options"]
        for order in orders_for(r["eligible_options"]):
            base = build_request(cfg, case, order, "described")
            info = dict(base.option_info)
            if x not in info or y not in info:
                continue
            req2 = S.SystemOneRequest(**{**base.__dict__, "option_info": {**info, x: info[y], y: info[x]}})
            a, b = S.system_one(base, backend), S.system_one(req2, backend)
            if a.escalate or b.escalate:
                escalated += 1
            elif a.answer("worker").choice == b.answer("worker").choice:
                same += 1
            else:
                flipped += 1
    n = same + flipped + escalated
    return {"note": "all two-option answerable semantic cases; metadata of the two options swapped, labels kept",
            "decisions": n, "follows_label": _rate(same, n), "follows_description": _rate(flipped, n),
            "escalated": _rate(escalated, n)}


def by_language(records: list[dict], data: dict) -> dict:
    """Layer-1 headline rates per case language (only for datasets that tag `lang`)."""
    cases = {c["id"]: c for c in data["cases"]}
    out = {}
    for lang in LANGS:
        rs = [r for r in records if cases[r["case"]].get("lang") == lang and r["kind"] == "semantic"]
        if not rs:
            continue
        ans = [r for r in rs if not cases[r["case"]]["gold"].get("escalate")]
        eg = [r for r in rs if cases[r["case"]]["gold"].get("escalate")]
        out[lang] = {"decisions": len(rs), "answerable": len(ans),
                     "acceptable_rate": _rate(sum(r["outcome"] == "correct" for r in ans), len(ans)),
                     "forbidden_rate": _rate(sum(r["outcome"] == "forbidden_choice" for r in ans), len(ans)),
                     "escalation_gold_correct": _rate(sum(r["outcome"] == "correct_escalation" for r in eg), len(eg)),
                     "success_rate": _rate(sum(r["outcome"] in SUCCESS for r in rs), len(rs))}
    return out


def abstention_diagnostics(records: list[dict], data: dict) -> dict | None:
    """Is abstaining informative? Compares the abstain variant with the plain described variant."""
    by = collections.defaultdict(dict)
    for r in records:
        by[r["variant"]][(r["case"], tuple(r["order"]))] = r
    if "described" not in by or "described+abstain" not in by:
        return None
    cases = {c["id"]: c for c in data["cases"]}
    ab, de = by["described+abstain"], by["described"]
    def kind(k):
        g = cases[k[0]]["gold"]
        return "escalate_gold" if g.get("escalate") else ("single" if len(k[1]) == 1 else "answerable")
    tot = collections.Counter(kind(k) for k in ab if cases[k[0]]["kind"] == "semantic")
    esc = collections.Counter(kind(k) for k, r in ab.items() if cases[k[0]]["kind"] == "semantic" and r["escalated"])
    abstained = sum(esc.values())
    answered_keys = [k for k, r in ab.items() if cases[k[0]]["kind"] == "semantic" and kind(k) == "answerable" and not r["escalated"]]
    abstained_keys = [k for k, r in ab.items() if cases[k[0]]["kind"] == "semantic" and kind(k) == "answerable" and r["escalated"]]
    prec = lambda keys, src: _rate(sum(src[k]["outcome"] == "correct" for k in keys), len(keys))
    return {"note": "informative abstention would fire mostly on escalate-gold decisions and on cases the plain variant gets wrong",
            "abstain_rate": {k: _rate(esc[k], tot[k]) for k in tot},
            "precision_of_abstention_on_escalate_gold": _rate(esc["escalate_gold"], abstained),
            "recall_of_abstention_on_escalate_gold": _rate(esc["escalate_gold"], tot["escalate_gold"]),
            "answerable_answered": len(answered_keys), "answerable_abstained": len(abstained_keys),
            "abstain_variant_precision_on_answered": prec(answered_keys, ab),
            "described_variant_precision_on_the_same_decisions": prec(answered_keys, de),
            "described_variant_precision_on_the_abstained_decisions": prec(abstained_keys, de)}


def decision_hash(recs: list[dict]) -> str:
    return hashlib.sha256(json.dumps([[r["case"], r["order"], r["outcome"], r["choice"], r["reason"]] for r in recs]).encode()).hexdigest()


def summarize(records: list[dict], data: dict) -> dict:
    cases = {c["id"]: c for c in data["cases"]}
    sem = [r for r in records if r["kind"] == "semantic"]
    answerable = [r for r in sem if not cases[r["case"]]["gold"].get("escalate")]
    esc = [r for r in sem if cases[r["case"]]["gold"].get("escalate")]
    pol = [r for r in records if r["kind"] == "policy"]
    cnt = collections.Counter(r["outcome"] for r in answerable)
    answered = [r for r in answerable if not r["escalated"]]
    n = len(answerable)

    by_strength = {s: {"decisions": len(rs), "acceptable_rate": _rate(sum(r["outcome"] == "correct" for r in rs), len(rs))}
                   for s in STRENGTHS if (rs := [r for r in answerable if r["strength"] == s])}
    by_category = {}
    for cat in sorted({r["category"] for r in sem}):
        rs = [r for r in sem if r["category"] == cat]
        by_category[cat] = {"decisions": len(rs), "success_rate": _rate(sum(r["outcome"] in SUCCESS for r in rs), len(rs)),
                            "violations": sum(r["outcome"] in VIOLATION for r in rs),
                            "escalated": sum(r["escalated"] for r in rs)}
    counter_prior = [r for r in answerable if "claude_code" not in cases[r["case"]]["gold"]["acceptable"]]

    constrained = [r for r in records if cases[r["case"]]["gold"].get("forbidden") or cases[r["case"]]["gold"].get("escalate")]
    violations = [r for r in constrained if r["outcome"] in VIOLATION]

    # option-order robustness (cases with >= 2 offered options)
    per_case = collections.defaultdict(list)
    for r in answerable:
        if len(cases[r["case"]]["request"]["eligible_options"]) >= 2:
            per_case[r["case"]].append(r)
    consistent = sum(1 for rs in per_case.values() if not any(x["escalated"] for x in rs) and len({x["choice"] for x in rs}) == 1)
    inv_correct = sum(1 for rs in per_case.values() if all(x["outcome"] == "correct" for x in rs))
    given = [rs[0] for rs in per_case.values()]
    first_listed = sum(1 for r in answered if len(r["order"]) >= 2 and r["choice"] == r["order"][0])
    multi_answered = [r for r in answered if len(r["order"]) >= 2]

    # semantic sensitivity: discriminate / invariant groups, per shared option ordering
    by_key = {(r["case"], tuple(r["order"])): r for r in records}
    members = collections.defaultdict(list)
    for c in data["cases"]:
        for g in groups_of(c):
            members[(g["id"], g["type"])].append(c["id"])
    sens = {"discriminate": {"checks": 0, "passed": 0}, "invariant": {"checks": 0, "passed": 0}, "groups": {}}
    for (gid, gtype), ids in sorted(members.items()):
        orders = set.intersection(*[{tuple(r["order"]) for r in records if r["case"] == i} for i in ids])
        chk = ok = 0
        for o in sorted(orders):
            rs = [by_key[(i, o)] for i in ids]
            chk += 1
            if gtype == "discriminate":
                ok += all(r["outcome"] == "correct" for r in rs)
            else:
                ok += (not any(r["escalated"] for r in rs)) and len({r["choice"] for r in rs}) == 1
        sens[gtype]["checks"] += chk
        sens[gtype]["passed"] += ok
        sens["groups"][gid] = {"type": gtype, "members": ids, "checks": chk, "passed": ok}
    for t in ("discriminate", "invariant"):
        sens[t]["pass_rate"] = _rate(sens[t]["passed"], sens[t]["checks"])

    # the R3.2B observation: a fixed preference for the label claude_code
    two = [r for r in answered if set(r["order"]) == {"claude_code", "codex"}]
    codex_gold = [r for r in two if cases[r["case"]]["gold"]["acceptable"] == ["codex"]]
    claude_gold = [r for r in two if cases[r["case"]]["gold"]["acceptable"] == ["claude_code"]]
    label_pref = {"two_worker_decisions": len(two),
                  "claude_code_share": _rate(sum(r["choice"] == "claude_code" for r in two), len(two)),
                  "claude_code_share_when_gold_is_codex": _rate(sum(r["choice"] == "claude_code" for r in codex_gold), len(codex_gold)),
                  "codex_share_when_gold_is_claude_code": _rate(sum(r["choice"] == "codex" for r in claude_gold), len(claude_gold)),
                  "prior_r32b_operational": "claude_code chosen 109/109 two-worker decisions (no gold)"}

    pol_cases = collections.defaultdict(list)
    for r in pol:
        pol_cases[r["case"]].append(r)
    pol_pass = sum(1 for rs in pol_cases.values() if all(x["outcome"] in SUCCESS for x in rs))

    conf = [r for r in answered if r["conf_value"] is not None]
    layer1 = {
        "note": "decision quality against labeled gold; escalations are safe but never successes",
        "answerable_decisions": n, "acceptable_rate": _rate(cnt["correct"], n),
        "answered_precision": _rate(cnt["correct"], len(answered)), "escalation_rate": _rate(cnt["escalated"], n),
        "wrong_allowed_rate": _rate(cnt["wrong_allowed"], n), "forbidden_choice_rate": _rate(cnt["forbidden_choice"], n),
        "by_strength": by_strength, "by_category": by_category,
        "counter_prior": {"decisions": len(counter_prior), "note": "cases where claude_code is NOT acceptable",
                          "acceptable_rate": _rate(sum(r["outcome"] == "correct" for r in counter_prior), len(counter_prior))},
        "escalation_gold": {"decisions": len(esc), "escalation_correctness": _rate(sum(r["outcome"] == "correct_escalation" for r in esc), len(esc)),
                            "unsafe_selection_rate": _rate(sum(r["outcome"] == "unsafe_selection" for r in esc), len(esc))},
        "policy_compliance": {"constrained_decisions": len(constrained), "violations": len(violations),
                              "compliance_rate": _rate(len(constrained) - len(violations), len(constrained)),
                              "violation_cases": sorted({r["case"] for r in violations})},
        "order_robustness": {"cases": len(per_case), "choice_consistent_across_orders": _rate(consistent, len(per_case)),
                             "correct_in_every_order": _rate(inv_correct, len(per_case)),
                             "given_order_acceptable_rate": _rate(sum(r["outcome"] == "correct" for r in given), len(given)),
                             "all_orders_acceptable_rate": _rate(sum(r["outcome"] == "correct" for rs in per_case.values() for r in rs),
                                                                 sum(len(rs) for rs in per_case.values())),
                             "first_listed_share": _rate(first_listed, len(multi_answered))},
        "semantic_sensitivity": sens, "label_preference": label_pref,
        "confidence_raw_descriptive": {"kinds": sorted({r["conf_kind"] for r in conf}), "all": _desc([r["conf_value"] for r in conf]),
                                       "when_correct": _desc([r["conf_value"] for r in conf if r["outcome"] == "correct"]),
                                       "when_wrong": _desc([r["conf_value"] for r in conf if r["outcome"] in ("wrong_allowed", "forbidden_choice")]),
                                       "note": "descriptive only: raw, uncalibrated, never used as a threshold"},
        "outcomes": dict(sorted(cnt.items())),
    }
    layer2 = {"note": "adapter/protocol compliance; independent of whether choices were good",
              "decisions": len(records), "compliant": sum(not r["protocol_violations"] for r in records),
              "compliance_rate": _rate(sum(not r["protocol_violations"] for r in records), len(records)),
              "violations": [{"case": r["case"], "order": r["order"], "what": r["protocol_violations"]} for r in records if r["protocol_violations"]][:20],
              "escalation_reasons": dict(sorted(collections.Counter(r["reason"] for r in records if r["escalated"]).items()))}
    lat = sorted(r["latency_ms"] for r in records)
    langs = by_language(records, data)
    if langs:
        layer1["by_language"] = langs
    return {"layer1_decision_quality": layer1,
            "policy_suite": {"note": "deterministic contract cases (single/empty options, metadata cannot widen); not model quality",
                             "cases": len(pol_cases), "passed": pol_pass, "pass_rate": _rate(pol_pass, len(pol_cases)),
                             "safe_degradations": sum(1 for r in pol if r["outcome"] == "escalated"),
                             "failures": [{"case": r["case"], "order": r["order"], "outcome": r["outcome"], "choice": r["choice"]}
                                          for r in pol if r["outcome"] not in SUCCESS + ("escalated",)]},
            "layer2_protocol_compliance": layer2,
            "operational": {"decisions": len(lat), "latency_ms": {"p50": round(percentile(lat, 50), 3), "p95": round(percentile(lat, 95), 3),
                                                                   "max": round(lat[-1], 3)} if lat else {}},
            "failures": [{"case": r["case"], "order": r["order"], "outcome": r["outcome"], "choice": r["choice"], "reason": r["reason"],
                          "gold": cases[r["case"]]["gold"].get("acceptable") or "escalate"}
                         for r in sem if r["outcome"] not in SUCCESS]}


def run_eval(cfg: Config, backend_name: str, *, variants: tuple = VARIANTS, seed: int = 1337,
             dataset: Path = DATASET, backend=None) -> dict:
    data = load_dataset(dataset)
    if backend is None:
        if backend_name.startswith("baseline:"):
            backend = _Baseline(backend_name.split(":", 1)[1], seed)
        elif backend_name.startswith("pipeline:"):                # R3.2G: explicit, evaluation-only composition
            from .systemone_pipeline import from_spec
            backend = from_spec(backend_name, cfg)
        else:
            backend = S.resolve_backend(backend_name, cfg)
    is_baseline = isinstance(backend, _Baseline)
    run_variants = ("bare",) if is_baseline else tuple(variants)
    dsum = collections.Counter(c["kind"] for c in data["cases"])
    out = {"schema": SCHEMA, "backend": backend_name, "seed": seed, "dataset_path": str(Path(dataset).relative_to(REPO_ROOT))
           if Path(dataset).is_relative_to(REPO_ROOT) else str(dataset),
           "command": " ".join(["agentos", *sys.argv[1:]]),
           "dataset": {"id": data["dataset"], "sha256": data["_sha256"], "cases": len(data["cases"]),
                       "semantic": dsum["semantic"], "policy": dsum["policy"], "e2e_cases": len(data["e2e_cases"]),
                       "escalation_gold": sum(1 for c in data["cases"] if c["gold"].get("escalate"))},
           "environment": environment(cfg), "variants": {}, "records": [],
           "claims": "Small synthetic set: results describe THIS set only and are not a statistical estimate of production accuracy.",
           "limitations": data.get("limitations")}
    rt = getattr(backend, "runtime", None)
    if not is_baseline:                       # exclude process spawn / model warm-up from the per-decision latencies
        first = data["cases"][0]
        S.system_one(build_request(cfg, first, tuple(first["request"]["eligible_options"]), run_variants[0]), backend)
    for v in run_variants:
        recs = run_cases(cfg, backend, data, v)
        out["records"].extend(recs)
        out["variants"][v] = summarize(recs, data)
        out["variants"][v]["decision_sequence_sha256"] = decision_hash(recs)
    out["probes"] = {"description_swap": description_swap_probe(cfg, backend, data),
                     "description_swap_all": description_swap_probe_all(cfg, backend, data)} if "described" in run_variants else {}
    diag = abstention_diagnostics(out["records"], data)
    if diag:
        out["probes"]["abstention"] = diag
    out["layer3_end_to_end_routing"] = run_e2e(cfg, backend, data)
    if hasattr(backend, "summary"):
        out["pipeline"] = backend.summary()
    if rt is not None:
        out["runtime"] = dict(getattr(rt, "info", {}) or {})
        out["worker_rss_mib"] = round((rt.rss_kib() or 0) / 1024, 1) if hasattr(rt, "rss_kib") else None
    return out


# ------------------------------------------------------------ CLI
def add_parser(sub) -> None:
    sp = sub.add_parser("systemone-eval", help="labeled decision-quality evaluation of a SystemOne backend")
    sp.add_argument("--backend", required=True,
                    help="a configured adapter backend (e.g. laya-mlx), baseline:first|last|label-prior|random, or "
                         "pipeline:<backend>:<neutral|raw>:<choice|per-option|consistency>")
    sp.add_argument("--variants", default=",".join(VARIANTS), help="comma list of: " + ", ".join(VARIANTS))
    sp.add_argument("--seed", type=int, default=1337)
    sp.add_argument("--dataset", default="dev", help="dev (66-case development set) | heldout (frozen held-out set) | a path")
    sp.add_argument("--out", help="write the full JSON result (with per-decision records) here")


def _fmt(v):
    return "n/a" if v is None else (f"{v:.3f}" if isinstance(v, float) else str(v))


def render(res: dict) -> str:
    lines = [f"backend={res['backend']}  dataset={res['dataset']['id']} sha256={res['dataset']['sha256'][:12]}…  "
             f"cases={res['dataset']['cases']} (semantic {res['dataset']['semantic']}, policy {res['dataset']['policy']}, "
             f"escalation-gold {res['dataset']['escalation_gold']}), e2e={res['dataset']['e2e_cases']}",
             res["claims"], ""]
    for v, s in res["variants"].items():
        l1, l2, ps = s["layer1_decision_quality"], s["layer2_protocol_compliance"], s["policy_suite"]
        lines += [f"== variant: {v}",
                  f"  LAYER 1 decision quality   acceptable={_fmt(l1['acceptable_rate'])} (answered-precision {_fmt(l1['answered_precision'])}, "
                  f"escalated {_fmt(l1['escalation_rate'])}, forbidden {_fmt(l1['forbidden_choice_rate'])}) "
                  f"counter-prior={_fmt(l1['counter_prior']['acceptable_rate'])}",
                  f"     escalation-gold: correct={_fmt(l1['escalation_gold']['escalation_correctness'])} "
                  f"unsafe-selection={_fmt(l1['escalation_gold']['unsafe_selection_rate'])} | policy compliance="
                  f"{_fmt(l1['policy_compliance']['compliance_rate'])} ({l1['policy_compliance']['violations']} violations)",
                  f"     order: consistent={_fmt(l1['order_robustness']['choice_consistent_across_orders'])} "
                  f"correct-in-every-order={_fmt(l1['order_robustness']['correct_in_every_order'])} "
                  f"first-listed-share={_fmt(l1['order_robustness']['first_listed_share'])} | sensitivity: "
                  f"discriminate={_fmt(l1['semantic_sensitivity']['discriminate']['pass_rate'])} invariant={_fmt(l1['semantic_sensitivity']['invariant']['pass_rate'])}",
                  *([f"     by language: " + "  ".join(f"{k}: acceptable={_fmt(v['acceptable_rate'])} esc-gold={_fmt(v['escalation_gold_correct'])} (n={v['decisions']})"
                                                         for k, v in l1["by_language"].items())] if l1.get("by_language") else []),
                  f"     label preference: claude_code share={_fmt(l1['label_preference']['claude_code_share'])} "
                  f"(when gold=codex: {_fmt(l1['label_preference']['claude_code_share_when_gold_is_codex'])})",
                  f"  LAYER 2 protocol compliance  {_fmt(l2['compliance_rate'])} ({l2['compliant']}/{l2['decisions']}) escalation reasons {l2['escalation_reasons']}",
                  f"  POLICY SUITE (contract, not quality)  pass={ps['passed']}/{ps['cases']}  safe-degradations={ps['safe_degradations']}",
                  f"  latency p50={s['operational']['latency_ms'].get('p50')} ms p95={s['operational']['latency_ms'].get('p95')} ms", ""]
    sw = res.get("probes", {}).get("description_swap")
    if sw:
        lines.append(f"PROBE description-swap (labels kept, descriptions swapped; n={sw['decisions']}): follows_label={_fmt(sw['follows_label'])} "
                     f"follows_description={_fmt(sw['follows_description'])} escalated={_fmt(sw['escalated'])}")
    sa = res.get("probes", {}).get("description_swap_all")
    if sa:
        lines.append(f"PROBE description-swap-all (every 2-option case; n={sa['decisions']}): follows_label={_fmt(sa['follows_label'])} "
                     f"follows_description={_fmt(sa['follows_description'])} escalated={_fmt(sa['escalated'])}")
    ab = res.get("probes", {}).get("abstention")
    if ab:
        lines.append(f"PROBE abstention: abstain-rate {ab['abstain_rate']} | recall on escalate-gold={_fmt(ab['recall_of_abstention_on_escalate_gold'])} "
                     f"precision={_fmt(ab['precision_of_abstention_on_escalate_gold'])} | answerable precision when it answers="
                     f"{_fmt(ab['abstain_variant_precision_on_answered'])} vs described on the same decisions="
                     f"{_fmt(ab['described_variant_precision_on_the_same_decisions'])}")
    e = res["layer3_end_to_end_routing"]
    lines.append(f"LAYER 3 end-to-end policy-valid routing  {e['passed']}/{e['n']} = {_fmt(e['policy_valid_rate'])}  ({e['note']})")
    for c in e["cases"]:
        if not c["passed"]:
            lines.append(f"   FAIL {c['case']}: {c['failures']}")
    return "\n".join(lines)


def write_result(path: Path, res: dict) -> None:
    """JSON with the structure indented but one decision record per line (reviewable diffs, small files)."""
    body = {k: v for k, v in res.items() if k != "records"}
    text = json.dumps(body, indent=2)
    rows = ",\n".join("    " + json.dumps(r, separators=(",", ":")) for r in res.get("records", []))
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(text[:-2] + ',\n  "records": [\n' + rows + "\n  ]\n}\n")


def run(cfg: Config, a) -> int:
    variants = tuple(v for v in a.variants.split(",") if v)
    bad = [v for v in variants if v not in VARIANTS]
    if bad:
        print(f"unknown variant(s) {bad}; choose from {VARIANTS}")
        return 2
    name = a.backend
    if not name.startswith(("baseline:", "pipeline:")) and name not in S.BACKENDS \
            and name not in __import__("agentos.systemone_adapter", fromlist=["x"]).definitions(cfg):
        print(f"unknown backend {name!r}: use a configured adapter backend or baseline:{{{','.join(BASELINES)}}}")
        return 2
    dataset = DATASETS.get(a.dataset) or Path(a.dataset)
    res = run_eval(cfg, name, variants=variants, seed=a.seed, dataset=dataset)
    if a.out:
        write_result(Path(a.out), res)
    print(render(res))
    return 0
