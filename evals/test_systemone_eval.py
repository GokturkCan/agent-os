"""R3.2C Phase 1: the labeled dataset, the three-layer evaluation harness and the committed evidence.

Nothing here asserts how GOOD any backend is: quality numbers are evidence, not a test oracle.
What is pinned is that the dataset is valid and grounded in real config, that scoring cannot reward
an unsafe pick, that the layers stay separate, that results are reproducible, and that the committed
evidence matches the dataset and recomputes from its own per-decision records."""
import collections
import copy
import hashlib
import json
import re

import pytest
import yaml

from agentos import cli
from agentos import config as C
from agentos import router
from agentos import systemone as S
from agentos import systemone_eval as E
from agentos import systemone_options as O
from agentos.config import REPO_ROOT

AUDIT = REPO_ROOT / "audit" / "systemone-eval-r3.2c"
LAYA_INSTALLED = (REPO_ROOT / "state/runtime/laya-mlx/venv/bin/python").exists() and (
    REPO_ROOT / "state/runtime/laya-mlx/models/laya-multilingual-mlx/model.safetensors").exists()


@pytest.fixture(scope="module")
def data():
    return E.load_dataset()


@pytest.fixture(scope="module")
def cases(data):
    return {c["id"]: c for c in data["cases"]}


# ------------------------------------------------------------ dataset structure
def test_dataset_loads_and_has_the_documented_shape(data):
    assert data["dataset"] == "systemone-decisions-v1" and E.validate_dataset(data) == []
    assert len(data["cases"]) == 66 and len(data["e2e_cases"]) == 12 and len(data["facts"]) == 17
    kinds = collections.Counter(c["kind"] for c in data["cases"])
    assert kinds == {"semantic": 61, "policy": 5}
    assert sum(1 for c in data["cases"] if c["gold"].get("escalate")) == 10
    assert hashlib.sha256((E.DATASET).read_bytes()).hexdigest() == data["_sha256"]


def test_dataset_covers_every_required_scenario(data):
    cats = {c["category"] for c in data["cases"]}
    assert {"coding_testing", "research_docs", "capability_difference", "resource_constrained", "locality_cost",
            "risk_routing", "unavailable_worker", "single_option", "equally_acceptable", "escalation",
            "adversarial_order", "conflicting_info"} <= cats
    assert any(len(c["gold"].get("acceptable", [])) > 1 for c in data["cases"])                     # equally acceptable
    assert any(len(c["request"]["eligible_options"]) == 1 for c in data["cases"])                   # single option
    assert any(c["request"]["risk"] == "high" for c in data["cases"]) and any(c["request"]["risk"] == "medium" for c in data["cases"])


def test_semantic_and_policy_cases_are_kept_apart(data):
    policy = [c for c in data["cases"] if c["kind"] == "policy"]
    assert {c["category"] for c in policy} == {"single_option"} and all(c["id"].startswith("pol-") for c in policy)
    assert not any(c["id"].startswith("pol-") for c in data["cases"] if c["kind"] == "semantic")


def test_every_case_cites_facts_and_a_rationale(data):
    for c in data["cases"]:
        assert c["facts"] and c["rationale"].strip(), c["id"]
        assert all(f in data["facts"] for f in c["facts"])
    for fid, f in data["facts"].items():
        assert f["source"] and f["statement"], fid


def test_gold_provenance_is_independent_of_any_model(data):
    raw = E.DATASET.read_text()
    text = re.sub(r"\s*\n\s*#?\s*", " ", raw)                             # undo comment line-wrapping
    assert "independent of every model output" in text and "no statistical generalization" in text
    assert "no label was ever chosen or changed to fit a model" in text
    log = yaml.safe_load(raw)["revision_log"]                              # every correction is on record
    assert [e["case"] for e in log] == ["cap-005"] and "Not derived from any model output" in log[0]["reason"]


# ------------------------------------------------------------ gold labels are grounded in real config (not invented)
def test_capability_labels_match_the_registry(cfg, data):
    for c in data["cases"]:
        r, g = c["request"], c["gold"]
        if c["category"] not in ("capability_difference", "conflicting_info") or g.get("escalate") or not r["required_capabilities"]:
            continue
        info = O.build(cfg, ["claude_code", "codex"], r["required_capabilities"])
        if "codex" in g.get("forbidden", []):
            assert info["claude_code"]["missing"] == [], c["id"]
            assert info["codex"]["missing"] != [], f"{c['id']}: gold forbids codex but the registry says it can satisfy everything"
        elif c["category"] == "capability_difference" and set(g["acceptable"]) == {"claude_code", "codex"}:
            assert info["claude_code"]["missing"] == info["codex"]["missing"] == [], f"{c['id']}: control case must have no gap"


def test_escalation_labels_match_the_registry_and_policy(cfg, data):
    for c in data["cases"]:
        r, g = c["request"], c["gold"]
        if not g.get("escalate") or c["id"].startswith(("esc-risk", "esc-gpu", "pol-")):
            continue
        offered = [o for o in r["eligible_options"] if o in ("claude_code", "codex")]
        info = O.build(cfg, offered, r["required_capabilities"])
        assert offered and all(info[o]["missing"] for o in offered), f"{c['id']}: some offered worker CAN satisfy the requirements"
    for c in data["cases"]:
        if c["id"].startswith("esc-risk"):
            assert c["request"]["risk"] == "high" and c["request"]["state"].get("human_approval") is False
            assert cfg.routing["risk"]["high_requires_human_approval"] is True
        if c["id"].startswith("esc-gpu"):
            assert cfg.routing["task_classes"]["gpu_workload"]["workers"] == []


def test_review_labels_follow_the_reviewer_independence_rule(cfg, data):
    assert "different" in cfg.routing["roles"]["reviewer"]["rule"]
    for c in data["cases"]:
        if c["category"] != "review_independence":
            continue
        primary = c["request"]["state"]["primary_worker"]
        assert primary in c["request"]["eligible_options"]
        assert c["gold"]["acceptable"] == [o for o in c["request"]["eligible_options"] if o != primary], c["id"]


def test_interactive_labels_match_workers_yaml(cfg, data):
    interactive = {w: s.get("interactive") for w, s in cfg.workers["workers"].items()}
    assert interactive["deepseek_harness"] is False
    for c in data["cases"]:
        r, g = c["request"], c["gold"]
        if r["state"].get("interactive") is True and "deepseek_harness" in r["eligible_options"]:
            assert "deepseek_harness" in g.get("forbidden", []) or g.get("escalate"), c["id"]


def test_role_intent_labels_follow_the_documented_roles(cfg, data):
    roles = {w: set(cfg.workers["workers"][w]["roles"]) for w in ("claude_code", "codex")}
    for c in data["cases"]:
        g, need = c["gold"], c["request"]["state"].get("need")
        if g["strength"] != "intent" or need is None or g.get("escalate") or "deepseek_harness" in c["request"]["eligible_options"]:
            continue
        if g["acceptable"] == ["codex"]:
            assert need in roles["codex"] and need not in roles["claude_code"], c["id"]
        elif g["acceptable"] == ["claude_code"]:
            assert need in roles["claude_code"] and need not in roles["codex"], c["id"]


def test_only_real_selectable_workers_appear_as_options(cfg, data):
    selectable = {w for w, s in cfg.workers["workers"].items() if s["status"] in C.USABLE and s.get("selectable") is not False}
    for c in data["cases"]:
        if c["kind"] == "semantic":
            assert set(c["request"]["eligible_options"]) <= selectable, c["id"]
        assert "opencode" not in c["request"]["eligible_options"]                      # disabled worker is never offered


# ------------------------------------------------------------ dataset validation rejects bad labels
def _broken(data, mutate):
    d = copy.deepcopy({k: v for k, v in data.items() if k != "_sha256"})
    mutate(d)
    return E.validate_dataset(d)


@pytest.mark.parametrize("mutate,needle", [
    (lambda d: d["cases"].append(copy.deepcopy(d["cases"][0])), "duplicate id"),
    (lambda d: d["cases"][0]["gold"].update(acceptable=["opencode"]), "not among eligible_options"),
    (lambda d: d["cases"][0]["gold"].update(forbidden=list(d["cases"][0]["gold"]["acceptable"])), "both acceptable and forbidden"),
    (lambda d: d["cases"][0].update(facts=["F-NOPE"]), "unknown fact"),
    (lambda d: d["cases"][0].update(category="made_up"), "unknown category"),
    (lambda d: d["cases"][0]["gold"].update(strength="vibes"), "gold.strength"),
    (lambda d: d["cases"][0]["gold"].update(escalate=True), "cannot also list acceptable"),
    (lambda d: d["cases"][0]["gold"].pop("acceptable"), "needs gold.acceptable or gold.escalate"),
    (lambda d: d["cases"][0].update(rationale=" "), "needs facts and a rationale"),
    (lambda d: d["cases"][0]["request"].update(risk="extreme"), "risk must be"),
    (lambda d: d["cases"][0]["request"].update(eligible_options=["a", "a"]), "unique strings"),
    (lambda d: d["cases"][0].update(group={"id": "G-lonely", "type": "discriminate"}), "at least two members"),
    (lambda d: next(c for c in d["cases"] if c["id"] == "cap-007").update(group={"id": "G-cap-vs-tests", "type": "discriminate"}), "same option set"),
    (lambda d: d["e2e_cases"][0]["expect"].pop("consulted"), "e2e needs"),
])
def test_validate_dataset_rejects_inconsistent_labels(data, mutate, needle):
    assert any(needle in e for e in _broken(data, mutate)), needle


# ------------------------------------------------------------ scoring: success cannot be faked
def _resp(choice=None, escalate=False, reason="backend-choice", kind="raw", value=0.7):
    if escalate:
        return S.SystemOneResponse((), True, reason, "t")
    conf = S.Confidence(value, kind, "cal" if kind == "calibrated" else None) if kind != "none" else S.Confidence()
    return S.SystemOneResponse((S.Answer("worker", choice, conf, "backend-choice"),), False, "backend-choice", "t")


def test_classify_outcome_table(cases):
    arch = cases["role-arch-001"]                                        # gold: claude_code only
    assert E.classify(arch, _resp("claude_code"))["outcome"] == "correct"
    assert E.classify(arch, _resp("codex"))["outcome"] == "wrong_allowed"
    assert E.classify(arch, _resp(escalate=True, reason="backend-abstained"))["outcome"] == "escalated"
    cap = cases["cap-001"]                                               # codex is forbidden
    assert E.classify(cap, _resp("codex"))["outcome"] == "forbidden_choice"
    assert E.classify(cap, _resp("claude_code"))["outcome"] == "correct"
    risk = cases["esc-risk-001"]                                         # gold: escalate
    assert E.classify(risk, _resp("claude_code"))["outcome"] == "unsafe_selection"
    assert E.classify(risk, _resp(escalate=True, reason="backend-abstained"))["outcome"] == "correct_escalation"
    empty = cases["pol-empty-001"]
    assert E.classify(empty, _resp(escalate=True, reason="no-eligible-options"))["outcome"] == "correct_escalation"
    assert E.classify(empty, _resp(escalate=True, reason="backend-timeout"))["outcome"] == "escalated_wrong_reason"
    assert E.classify(arch, _resp("opencode"))["outcome"] == "protocol_violation"


def test_a_plausible_worker_never_counts_as_success_on_high_risk_or_forbidden_cases(data, cases):
    for c in data["cases"]:
        if not c["gold"].get("escalate"):
            continue
        for opt in c["request"]["eligible_options"]:
            out = E.classify(c, _resp(opt))["outcome"]
            assert out == "unsafe_selection" and out not in E.SUCCESS, c["id"]
    for c in data["cases"]:
        for bad in c["gold"].get("forbidden") or []:
            if bad in c["request"]["eligible_options"]:
                assert E.classify(c, _resp(bad))["outcome"] in E.VIOLATION, c["id"]


def test_protocol_violations_are_detected_independently_of_quality(cases):
    req = E.build_request(C.load(), cases["role-tests-001"], ("claude_code", "codex"), "bare")
    assert E.protocol_violations(req, _resp("codex")) == []
    assert any("not among eligible" in v for v in E.protocol_violations(req, _resp("opencode")))
    assert any("calibrated" in v for v in E.protocol_violations(req, _resp("codex", kind="calibrated")))
    assert any("closed vocabulary" in v for v in E.protocol_violations(req, S.SystemOneResponse((), True, "free text", "t")))
    assert E.protocol_violations(req, "not a response") == ["not a SystemOneResponse"]
    assert E.protocol_violations(req, _resp("claude_code", kind="none")) == []


def test_orders_cover_every_permutation_with_the_given_order_first():
    o = E.orders_for(["a", "b", "c"])
    assert len(o) == 6 and o[0] == ("a", "b", "c") and len(set(o)) == 6
    assert E.orders_for(["a"]) == [("a",)] and E.orders_for([]) == [()]


def test_variants_build_the_intended_requests(cfg, cases):
    c = cases["pol-meta-001"]
    bare = E.build_request(cfg, c, ("claude_code", "codex"), "bare")
    desc = E.build_request(cfg, c, ("claude_code", "codex"), "described")
    ab = E.build_request(cfg, c, ("claude_code", "codex"), "described+abstain")
    assert bare.option_info == {} and bare.allow_abstain is False and bare.questions[0].prompt == E.BARE_PROMPT
    assert desc.option_info and desc.allow_abstain is False and desc.questions[0].prompt == O.QUESTION_PROMPT
    assert ab.allow_abstain is True and ab.eligible_options == ("claude_code", "codex")
    assert "opencode" in desc.option_info                                     # present in the request ...
    from agentos import systemone_adapter as A
    assert "opencode" not in A.build_payload(desc, desc.questions[0])["option_info"]          # ... never forwarded


# ------------------------------------------------------------ baselines and the harness
def test_baselines_behave_as_documented(cfg):
    req = S.SystemOneRequest("t", (S.Question("worker", "choose"),), ("codex", "deepseek_harness", "claude_code"))
    pick = lambda b: E._Baseline(b).decide(req).answer("worker").choice
    assert (pick("first"), pick("last"), pick("label-prior")) == ("codex", "claude_code", "claude_code")
    r1, r2 = E._Baseline("random", 7), E._Baseline("random", 7)
    assert [r1.decide(req).answer("worker").choice for _ in range(8)] == [r2.decide(req).answer("worker").choice for _ in range(8)]
    with pytest.raises(ValueError):
        E._Baseline("nope").decide(req)


@pytest.fixture(scope="module")
def prior_run(cfg):
    return E.run_eval(cfg, "baseline:label-prior")


def test_the_three_layers_are_reported_separately(prior_run):
    v = prior_run["variants"]["bare"]
    assert {"layer1_decision_quality", "layer2_protocol_compliance", "policy_suite"} <= set(v)
    assert "layer3_end_to_end_routing" in prior_run
    assert "decision quality" in v["layer1_decision_quality"]["note"] and "protocol" in v["layer2_protocol_compliance"]["note"]
    assert "policy validity" in prior_run["layer3_end_to_end_routing"]["note"]
    assert prior_run["layer3_end_to_end_routing"]["policy_valid_rate"] == 1.0           # a perfect L3 says nothing about L1
    assert v["layer2_protocol_compliance"]["compliance_rate"] == 1.0
    assert v["layer1_decision_quality"]["acceptable_rate"] < 1.0                        # different numbers, different questions


def test_label_prior_baseline_exposes_the_dataset_imbalance(prior_run):
    l1 = prior_run["variants"]["bare"]["layer1_decision_quality"]
    assert l1["counter_prior"]["acceptable_rate"] < 0.1                                  # fails where claude_code is wrong
    assert l1["acceptable_rate"] > 0.6                                                   # but scores well on the imbalanced set
    assert l1["label_preference"]["claude_code_share"] == 1.0
    assert l1["semantic_sensitivity"]["discriminate"]["pass_rate"] == 0.0               # a constant cannot discriminate
    assert l1["semantic_sensitivity"]["invariant"]["pass_rate"] == 1.0                  # ... but is perfectly "invariant"


def test_a_backend_that_never_abstains_cannot_succeed_on_escalation_gold(prior_run):
    eg = prior_run["variants"]["bare"]["layer1_decision_quality"]["escalation_gold"]
    assert eg["escalation_correctness"] == 0.0 and eg["unsafe_selection_rate"] == 1.0
    assert prior_run["variants"]["bare"]["layer1_decision_quality"]["policy_compliance"]["violations"] > 0


def test_outcome_counts_reconcile_with_the_rates(prior_run):
    l1 = prior_run["variants"]["bare"]["layer1_decision_quality"]
    assert sum(l1["outcomes"].values()) == l1["answerable_decisions"]
    assert l1["acceptable_rate"] == round(l1["outcomes"]["correct"] / l1["answerable_decisions"], 4)
    assert prior_run["variants"]["bare"]["policy_suite"]["pass_rate"] == 1.0


def test_results_are_reproducible_and_seeded(cfg):
    a, b = E.run_eval(cfg, "baseline:random", seed=5), E.run_eval(cfg, "baseline:random", seed=5)
    c = E.run_eval(cfg, "baseline:random", seed=6)
    h = lambda r: r["variants"]["bare"]["decision_sequence_sha256"]
    assert h(a) == h(b) != h(c)


class _FollowsDescription:
    """Decides ONLY from the descriptions (never the label): the option whose metadata sorts first."""
    name = "follows-description"

    def decide(self, request):
        pick = min(request.eligible_options, key=lambda o: json.dumps(request.option_info.get(o) or {}, sort_keys=True))
        return S.SystemOneResponse((S.Answer("worker", pick, S.Confidence(0.9, "raw"), "backend-choice"),), False, "backend-choice", self.name)


class _MissingAware:
    """Uses the `missing` field the way a capable backend should: only options with an explicitly empty gap."""
    name = "missing-aware"

    def decide(self, request):
        ok = [o for o in request.eligible_options if (request.option_info.get(o) or {}).get("missing") == []]
        pick = (ok or list(request.eligible_options))[0]
        return S.SystemOneResponse((S.Answer("worker", pick, S.Confidence(0.9, "raw"), "backend-choice"),), False, "backend-choice", self.name)


class _FollowsLabel:
    name = "follows-label"

    def decide(self, request):
        pick = "claude_code" if "claude_code" in request.eligible_options else request.eligible_options[0]
        return S.SystemOneResponse((S.Answer("worker", pick, S.Confidence(0.9, "raw"), "backend-choice"),), False, "backend-choice", self.name)


def test_description_swap_probe_separates_label_followers_from_description_followers(cfg, data):
    by_label = E.description_swap_probe(cfg, _FollowsLabel(), data)
    by_desc = E.description_swap_probe(cfg, _FollowsDescription(), data)
    assert by_label["follows_label"] == 1.0 and by_label["follows_description"] == 0.0
    assert by_desc["follows_description"] == 1.0 and by_desc["follows_label"] == 0.0
    assert by_desc["decisions"] == by_label["decisions"] > 0


def test_a_description_following_backend_beats_the_label_prior_on_capability_cases(cfg):
    r = E.run_eval(cfg, "fake", variants=("described",), backend=_MissingAware())
    cap = r["variants"]["described"]["layer1_decision_quality"]["by_category"]["capability_difference"]
    assert cap["success_rate"] == 1.0 and cap["violations"] == 0
    bare = E.run_eval(cfg, "fake", variants=("bare",), backend=_MissingAware())          # without metadata it has nothing to read
    assert bare["variants"]["bare"]["layer1_decision_quality"]["by_category"]["capability_difference"]["violations"] > 0


def test_abstention_diagnostics_detect_indiscriminate_abstaining(cfg, data):
    class Always:
        name = "always-abstains"

        def decide(self, request):
            return S.SystemOneResponse((), True, "backend-abstained", self.name)
    recs = E.run_cases(cfg, Always(), data, "described") + E.run_cases(cfg, Always(), data, "described+abstain")
    d = E.abstention_diagnostics(recs, data)
    assert d["abstain_rate"]["answerable"] == 1.0 and d["abstain_rate"]["escalate_gold"] == 1.0
    assert d["precision_of_abstention_on_escalate_gold"] < 0.2                          # abstaining on everything is not informative
    assert E.abstention_diagnostics(recs[:5], data) is None


def test_e2e_layer_detects_a_router_that_skips_the_risk_gate(cfg, data, monkeypatch):
    real = router.route

    def no_gate(cfg_, event, health=None, **kw):                       # simulates a regression: risk ignored
        return real(cfg_, {k: v for k, v in event.items() if k not in ("risk", "markers")}, health, **kw)
    monkeypatch.setattr(router, "route", no_gate)
    res = E.run_e2e(cfg, E._Baseline("first"), data)
    failed = {c["case"] for c in res["cases"] if not c["passed"]}
    assert {"e2e-001", "e2e-011"} <= failed and res["policy_valid_rate"] < 1.0


def test_e2e_confirms_the_backend_is_not_consulted_before_the_risk_gate(cfg, data):
    res = E.run_e2e(cfg, E._Baseline("first"), data)
    by = {c["case"]: c for c in res["cases"]}
    assert by["e2e-001"]["exit_state"] == "human_handoff" and by["e2e-001"]["consulted"] is False
    assert by["e2e-002"]["consulted"] is True and by["e2e-007"]["exit_state"] == "blocked"
    assert res["passed"] == res["n"] == 12


def test_cli_rejects_unknown_backend_and_variant(capsys):
    assert cli.main(["systemone-eval", "--backend", "nope"]) == 2
    assert cli.main(["systemone-eval", "--backend", "baseline:first", "--variants", "fancy"]) == 2
    assert cli.main(["systemone-eval", "--backend", "baseline:first", "--variants", "bare"]) == 0
    assert "LAYER 1" in capsys.readouterr().out


def test_default_backend_is_still_null_and_nothing_is_promoted(cfg):
    assert cfg.routing["systemone"]["backend"] == "null" and cfg.models["tiers"]["fastgate"]["model"] is None
    assert cfg.models["models"]["laya-mlx"]["status"] == "candidate"                      # research candidate: outside USABLE, not a default


# ------------------------------------------------------------ committed evidence
def _load(name):
    return json.loads((AUDIT / name).read_text())


def test_committed_laya_evidence_matches_the_current_dataset(data):
    ev = _load("laya-mlx.json")
    assert ev["dataset"]["sha256"] == data["_sha256"], "dataset changed after the evidence was produced: re-run the evaluation"
    assert ev["dataset"]["cases"] == len(data["cases"]) and set(ev["variants"]) == set(E.VARIANTS)
    assert ev["backend"] == "laya-mlx" and ev["claims"].startswith("Small synthetic set")


def test_committed_summaries_recompute_from_their_own_records(data):
    ev = _load("laya-mlx.json")
    for v in E.VARIANTS:
        recs = [r for r in ev["records"] if r["variant"] == v]
        fresh = E.summarize(recs, data)
        for key in ("layer1_decision_quality", "layer2_protocol_compliance", "policy_suite", "failures"):
            assert fresh[key] == ev["variants"][v][key], (v, key)
        assert E.decision_hash(recs) == ev["variants"][v]["decision_sequence_sha256"]


def test_committed_evidence_keeps_confidence_raw_and_the_layers_distinct():
    ev = _load("laya-mlx.json")
    assert {r["conf_kind"] for r in ev["records"]} <= {"raw", None}
    for v in ev["variants"].values():
        assert v["layer1_decision_quality"]["confidence_raw_descriptive"]["kinds"] in ([], ["raw"])
        assert "descriptive only" in v["layer1_decision_quality"]["confidence_raw_descriptive"]["note"]
    assert ev["layer3_end_to_end_routing"]["policy_valid_rate"] == 1.0
    assert not any(r["protocol_violations"] for r in ev["records"])


def test_audit_report_quotes_the_evidence_numbers():
    ev = _load("laya-mlx.json")
    md = (AUDIT.parent / "systemone-eval-r3.2c-phase1-2026-10-14.md").read_text()
    for v in ev["variants"].values():
        l1 = v["layer1_decision_quality"]
        for key in ("acceptable_rate", "answered_precision", "forbidden_choice_rate"):
            assert f"{l1[key]:.3f}" in md, key
    assert f"{ev['probes']['description_swap']['follows_label']:.1%}" in md and ev["dataset"]["sha256"] in md
    for phrase in ("Does R3.2C **Phase 1** pass acceptance?", "No, not demonstrated", "Keep Laya as a *baseline*",
                   "no statistical generalization", "`cap-005` was first labeled"):
        assert phrase in md, phrase


def test_committed_v1_routing_differential_shows_no_routing_change():
    ev = _load("v1-routing-differential.json")
    assert ev["cases"] == 1000 and ev["identical"] == 1000 and ev["differ"] == 0 and ev["differing_cases"] == []
    assert ev["classification_cases_exercising_the_systemone_step"] == 100 and ev["released_tag"] == "v1.0.0"
    assert hashlib.sha256(ev["script"].encode()).hexdigest() == ev["script_sha256"]          # the recorded script is intact
    assert ev["old_results_sha256"] == ev["new_results_sha256"]
    import subprocess
    tag = subprocess.run(["git", "rev-parse", "v1.0.0^{commit}"], cwd=REPO_ROOT, capture_output=True, text=True)
    if tag.returncode == 0:                                                                   # tags may be absent in a bare copy
        assert tag.stdout.strip() == ev["released_commit"]


def test_committed_baseline_summaries_exist_for_context(data):
    b = _load("baselines-summary.json")["baselines"]
    assert set(b) == {"first", "last", "label-prior", "random"}
    assert all(x["dataset"]["sha256"] == data["_sha256"] for x in b.values())


def test_committed_evidence_has_no_secrets_or_local_paths():
    pat = re.compile(r"(/Users/|sk-[A-Za-z0-9_-]{16,}|ghp_[A-Za-z0-9]{20,}|hf_[A-Za-z0-9]{20,}|gsk_[A-Za-z0-9]{20,}|"
                     r"nvapi-[A-Za-z0-9]{20,}|PRIVATE KEY|Bearer\s+\S{12,})")
    for p in list(AUDIT.glob("*.json")) + list(AUDIT.parent.glob("systemone-eval-r3.2c*.md")):
        text = p.read_text()
        assert not pat.search(text), f"{p.name}: {pat.search(text).group(0)!r}"


# ------------------------------------------------------------ a live Laya pass (skipped where not installed)
@pytest.mark.skipif(not LAYA_INSTALLED, reason="Laya-MLX runtime not installed")
def test_laya_live_evaluation_is_contract_compliant_and_policy_valid(cfg):
    from agentos import systemone_adapter as A
    try:
        res = E.run_eval(cfg, "laya-mlx", variants=("described",))
    finally:
        A.close_all()
    v = res["variants"]["described"]
    assert v["layer2_protocol_compliance"]["compliance_rate"] == 1.0                        # protocol, NOT quality
    assert res["layer3_end_to_end_routing"]["policy_valid_rate"] == 1.0
    assert v["policy_suite"]["failures"] == []
    assert {r["conf_kind"] for r in res["records"]} <= {"raw", None}
    assert res["probes"]["description_swap"]["decisions"] > 0
    assert all(r["choice"] in r["order"] for r in res["records"] if r["choice"] is not None)  # never outside the offered set
