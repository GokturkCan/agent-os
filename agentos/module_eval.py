"""Acceptance suites for the R3.2G task-specific modules (WakeGate, ContextGate, tool pruner, rule cache). OFFLINE.

  agentos module-eval --suite wakegate|contextgate|toolpruner|rulecache [--backend laya-mlx|none] [--out F]

`--backend none` runs the deterministic-only ablation (model OFF). Each suite measures the MODULE (missed important events,
essential-fact loss, token savings, ...), not worker-routing accuracy.
"""
from __future__ import annotations

import json
import statistics
import tempfile
import time
from pathlib import Path

import yaml

from . import systemone as S
from .config import REPO_ROOT

SUITES = REPO_ROOT / "evals" / "data" / "modules"


def _backend(name, cfg):
    return None if name in (None, "none") else S.resolve_backend(name, cfg)


def _pct(xs, p):
    xs = sorted(xs)
    return round(xs[min(len(xs) - 1, int(p * len(xs)))], 3) if xs else None


def eval_wakegate(cfg, backend_name, suite_file=None) -> dict:
    from . import wakegate as W
    data = yaml.safe_load((Path(suite_file) if suite_file else SUITES / "wakegate-suite-v1.yaml").read_text())
    be = _backend(backend_name, cfg)
    recs = []
    for c in data["cases"]:
        ev = c["event"]
        event = W.Event(kind=ev["kind"], summary=ev.get("summary", ""), source=ev.get("source", ""), risk=ev.get("risk", "low"),
                        markers=tuple(ev.get("markers", ())), from_user=bool(ev.get("from_user")),
                        requires_approval=bool(ev.get("requires_approval")), deadline_minutes=ev.get("deadline_minutes"),
                        observation=ev.get("observation") or {})
        st = W.WaitState(c["waiting_for"], W.observation_sha(c["previous_observation"]) if c.get("previous_observation") else None,
                         skipped=c.get("skipped", 0))
        v = W.gate(event, st, be, use_model=be is not None)
        fn = c["gold"] == "must_wake" and not v.wake
        unnecessary = c["gold"] == "should_defer" and v.wake
        recs.append({"id": c["id"], "lang": c["lang"], "family": c["family"], "gold": c["gold"], "action": v.action,
                     "reason": v.reason, "model_called": v.model_called, "latency_ms": v.latency_ms,
                     "false_negative": fn, "unnecessary_wake": unnecessary})
    must = [r for r in recs if r["gold"] == "must_wake"]
    defer = [r for r in recs if r["gold"] == "should_defer"]
    model_lat = [r["latency_ms"] for r in recs if r["model_called"]]
    fam = {}
    for r in recs:
        f = fam.setdefault(r["family"], {"n": 0, "fn": 0, "unnecessary": 0, "deferred": 0})
        f["n"] += 1
        f["fn"] += r["false_negative"]
        f["unnecessary"] += r["unnecessary_wake"]
        f["deferred"] += r["action"] == W.DEFER
    return {"suite": data["suite"], "backend": backend_name, "cases": len(recs),
            "false_negatives": sum(r["false_negative"] for r in recs),
            "false_negative_rate": round(sum(r["false_negative"] for r in must) / len(must), 4),
            "unnecessary_wakes": sum(r["unnecessary_wake"] for r in recs),
            "unnecessary_wake_rate": round(sum(r["unnecessary_wake"] for r in defer) / len(defer), 4),
            "deferred_total": sum(r["action"] == W.DEFER for r in recs),
            "avoided_reasoning_turns_vs_always_wake": sum(r["action"] == W.DEFER for r in recs),
            "model_calls": sum(r["model_called"] for r in recs),
            "model_latency_ms": {"p50": _pct(model_lat, .5), "p95": _pct(model_lat, .95)},
            "by_family": fam, "by_lang": {l: {"fn": sum(r["false_negative"] for r in recs if r["lang"] == l),
                                              "unnecessary": sum(r["unnecessary_wake"] for r in recs if r["lang"] == l)}
                                          for l in ("en", "tr")},
            "records": recs}


def eval_contextgate(cfg, backend_name, suite_file=None) -> dict:
    from . import contextgate as C
    data = yaml.safe_load((Path(suite_file) if suite_file else SUITES / "contextgate-suite-v1.yaml").read_text())
    be = _backend(backend_name, cfg)
    out, tb, ta = [], 0, 0
    with tempfile.TemporaryDirectory() as tmp:
        store = C.Store(tmp)
        for t in data["transcripts"]:
            items = [C.Item(i["id"], i["role"], i["kind"], i["text"], i.get("tool", "")) for i in t["items"]]
            t0 = time.perf_counter()
            res = C.compact(items, store, backend=be)
            ms = (time.perf_counter() - t0) * 1000
            view = "\n".join(v["text"] for v in res.view)
            missing = [e for e in t["essential"] if e not in view]
            recovered = all(store.get(d["sha256"]) == it.text for d, it in zip(res.decisions, items))
            tb += res.stats["tokens_before"]
            ta += res.stats["tokens_after"]
            out.append({"id": t["id"], "lang": t["lang"], **res.stats, "missing_essential": missing,
                        "recovery_exact": recovered, "latency_ms": round(ms, 1),
                        "actions": {a: sum(d["action"] == a for d in res.decisions) for a in C.ACTIONS}})
    ess = sum(len(t["essential"]) for t in data["transcripts"])
    return {"suite": data["suite"], "backend": backend_name, "transcripts": len(out), "essential_facts": ess,
            "false_drops": sum(len(r["missing_essential"]) for r in out),
            "false_drop_rate": round(sum(len(r["missing_essential"]) for r in out) / ess, 4),
            "recovery_exact_all": all(r["recovery_exact"] for r in out),
            "tokens_before": tb, "tokens_after": ta, "token_reduction": round(1 - ta / tb, 4),
            "model_calls": sum(r["model_calls"] for r in out),
            "latency_ms_per_transcript": {"p50": _pct([r["latency_ms"] for r in out], .5), "max": max(r["latency_ms"] for r in out)},
            "records": out}


def eval_toolpruner(cfg, backend_name, suite_file=None) -> dict:
    from . import toolpruner as P
    from .contextgate import Store
    data = yaml.safe_load((Path(suite_file) if suite_file else SUITES / "toolpruner-suite-v1.yaml").read_text())
    be = _backend(backend_name, cfg)
    out, tb, ta = [], 0, 0
    with tempfile.TemporaryDirectory() as tmp:
        store = Store(tmp)
        for o in data["outputs"]:
            t0 = time.perf_counter()
            r = P.prune(o["output"], store, goal=o["goal"], backend=be)
            ms = (time.perf_counter() - t0) * 1000
            missing = [e for e in o["essential"] if e not in r.view]
            tb += r.stats["tokens_before"]
            ta += r.stats["tokens_after"]
            out.append({"id": o["id"], "lang": o["lang"], **r.stats, "missing_essential": missing,
                        "recovery_exact": store.get(r.sha256) == o["output"], "latency_ms": round(ms, 1)})
    ess = sum(len(o["essential"]) for o in data["outputs"])
    return {"suite": data["suite"], "backend": backend_name, "outputs": len(out), "essential_lines": ess,
            "essential_lost": sum(len(r["missing_essential"]) for r in out),
            "essential_loss_rate": round(sum(len(r["missing_essential"]) for r in out) / ess, 4),
            "recovery_exact_all": all(r["recovery_exact"] for r in out),
            "tokens_before": tb, "tokens_after": ta, "token_reduction": round(1 - ta / tb, 4),
            "model_calls": sum(r["model_calls"] for r in out),
            "latency_ms": {"p50": _pct([r["latency_ms"] for r in out], .5), "max": max(r["latency_ms"] for r in out)},
            "records": out}


def eval_rulecache(cfg, backend_name, suite_file=None) -> dict:
    """Behavioural acceptance of the review/scoping/invalidation rules on the dev set's requests (no model needed)."""
    from . import rulecache as R
    from . import systemone_eval as E
    data = E.load_dataset(E.DATASET)
    checks = {}
    with tempfile.TemporaryDirectory() as tmp:
        cache = R.RuleCache(Path(tmp) / "rules.yaml")
        h = R.config_hash(cfg.root)
        reqs = [E.build_request(cfg, c, tuple(c["request"]["eligible_options"]), "described") for c in data["cases"]
                if c["request"]["eligible_options"]]
        pol = S.PolicyOrderBackend()
        proposed = [cache.propose(r, pol.decide(r), h, "dev-set:policy-order") for r in reqs]
        checks["proposed_rules"] = len({p["id"] for p in proposed})
        cb = R.CachedBackend(pol, cache, h)
        for r in reqs:
            cb.decide(r)
        checks["hits_before_approval"] = cb.hits
        first = proposed[0]
        try:
            cache.approve(first["id"], "agentos")
            checks["non_human_approval_refused"] = False
        except ValueError:
            checks["non_human_approval_refused"] = True
        cache.approve(first["id"], "human:fixture")
        cb2 = R.CachedBackend(S.NullBackend(), cache, h)
        hit = next(r for r in reqs if cache.lookup(r, h))
        checks["approved_rule_hits"] = not S.system_one(hit, cb2).escalate
        checks["config_change_invalidates"] = cache.lookup(hit, "0" * 64) is None
        from dataclasses import replace
        narrowed = replace(hit, eligible_options=tuple(o for o in hit.eligible_options if o != first["decision"]) or ("x",))
        checks["rule_never_adds_option"] = cache.lookup(narrowed, h) is None
        cache.save()
        reloaded = R.RuleCache.load(cache.path)
        checks["store_reviewable_roundtrip"] = reloaded.rules[first["id"]]["status"] == "approved"
        cache.revoke(first["id"], "fixture")
        checks["revoked_stops_applying"] = cache.lookup(hit, h) is None
    checks["all_pass"] = (checks["hits_before_approval"] == 0 and checks["non_human_approval_refused"]
                          and checks["approved_rule_hits"] and checks["config_change_invalidates"]
                          and checks["rule_never_adds_option"] and checks["store_reviewable_roundtrip"]
                          and checks["revoked_stops_applying"])
    return {"suite": "rulecache-behaviour-v1", "backend": "n/a", **checks}


EVALS = {"wakegate": eval_wakegate, "contextgate": eval_contextgate, "toolpruner": eval_toolpruner, "rulecache": eval_rulecache}


def acceptance(res: dict) -> bool:
    if "false_negatives" in res:
        return res["false_negatives"] == 0
    if "false_drops" in res:
        return res["false_drops"] == 0 and res.get("recovery_exact_all") is True
    if "essential_lost" in res:
        return res["essential_lost"] == 0 and res.get("recovery_exact_all") is True
    return res.get("all_pass") is True


def add_parser(sub) -> None:
    sp = sub.add_parser("module-eval", help="R3.2G module acceptance suites (wakegate/contextgate/toolpruner/rulecache)")
    sp.add_argument("--suite", required=True, choices=sorted(EVALS))
    sp.add_argument("--backend", default="none", help="a SystemOne backend name, or none (deterministic-only)")
    sp.add_argument("--suite-file", help="evaluate this suite file instead of the v1 suite (same schema)")
    sp.add_argument("--out")


def run(cfg, a) -> int:
    from . import systemone_adapter as A
    try:
        res = EVALS[a.suite](cfg, a.backend, a.suite_file)
    finally:
        A.close_all()
    res["acceptance_pass"] = acceptance(res)
    res["suite_file"] = a.suite_file
    res["token_measurement"] = "character-count estimate: ceil(chars/4), not tokenizer-measured"
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(res, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({k: v for k, v in res.items() if k != "records"}, indent=2, ensure_ascii=False))
    return 0 if res["acceptance_pass"] else 1
