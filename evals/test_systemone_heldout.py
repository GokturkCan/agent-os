"""Deterministic checks of the frozen held-out set (evals/data/systemone-heldout-v1.yaml, R3.2C Phase 2B).

These tests check the LABELS against repository config - they never look at a model's output - and that
the file is the frozen version recorded in the audit report.
"""
import collections

import pytest

from agentos import config as C
from agentos import systemone_eval as E
from agentos import systemone_options as O

FROZEN_SHA256 = "3affe3b44a1734357f32a5675540f9dedf9d6802715385f6607c7c781b2e6253"
REAL = ("claude_code", "codex", "deepseek_harness")


@pytest.fixture(scope="module")
def cfg():
    return C.load()


@pytest.fixture(scope="module")
def data():
    return E.load_dataset(E.HELDOUT)


def test_heldout_is_the_frozen_file(data):
    assert data["_sha256"] == FROZEN_SHA256, "held-out set changed: create systemone-heldout-v2 instead of editing v1"


def test_heldout_is_separate_from_dev(data):
    dev = E.load_dataset(E.DATASET)
    assert not {c["id"] for c in data["cases"]} & {c["id"] for c in dev["cases"]}
    assert data["dataset"] != dev["dataset"]


def test_language_mix_and_coverage(data):
    langs = collections.Counter(c["lang"] for c in data["cases"])
    assert set(langs) == {"en", "tr"} and langs["tr"] / sum(langs.values()) >= 0.4
    cats = {c["category"] for c in data["cases"]}
    for need in ("dynamic_capability", "label_bias", "description_bias", "review_independence", "risk_routing",
                 "approval_boundary", "worker_failure", "invalid_options", "insufficient_info", "escalation",
                 "locality_cost", "interactive_constraint"):
        assert need in cats, need


def test_alias_metadata_is_real_worker_metadata(cfg, data):
    real = O.build(cfg, REAL, ())
    for c in data["cases"]:
        for opt, info in (c["request"].get("option_info_extra") or {}).items():
            if opt == "opencode":
                continue                           # deliberately non-offered metadata (must be ignored)
            core = {k: v for k, v in info.items() if k not in ("missing", "status")}
            assert core in list(real.values()), f"{c['id']}:{opt} metadata is not any real worker's metadata"


def test_capability_labels_match_the_registry(cfg, data):
    for c in data["cases"]:
        r, g = c["request"], c["gold"]
        offered = [o for o in r["eligible_options"] if o in ("claude_code", "codex")]
        if not r["required_capabilities"] or not offered or c["kind"] != "semantic":
            continue
        info = O.build(cfg, offered, r["required_capabilities"])
        missing = {o for o in offered if info[o]["missing"]}
        if g.get("escalate"):
            assert missing == set(offered), f"{c['id']}: some offered worker CAN satisfy the requirements"
        else:
            assert missing == set(g.get("forbidden") or []) & set(offered), c["id"]
            assert not missing & set(g["acceptable"]), c["id"]


def test_alias_capability_labels_follow_explicit_missing(data):
    for c in data["cases"]:
        extra, g = c["request"].get("option_info_extra") or {}, c["gold"]
        for opt, info in extra.items():
            if info.get("missing"):
                assert opt in (g.get("forbidden") or []), f"{c['id']}: {opt} lacks a capability but is not forbidden"


def test_review_and_failure_and_availability_rules(cfg, data):
    assert "different" in cfg.routing["roles"]["reviewer"]["rule"]
    for c in data["cases"]:
        st, g = c["request"]["state"], c["gold"]
        if c["category"] == "review_independence":
            assert st["primary_worker"] in g["forbidden"] and st["primary_worker"] not in g["acceptable"]
        if c["category"] == "worker_failure":
            assert st["previous_worker"] not in g["acceptable"]
        for opt, info in (c["request"].get("option_info_extra") or {}).items():
            if info.get("status") == "unavailable":
                assert opt in g["forbidden"]


def test_interactive_cases_forbid_background_only_options(cfg, data):
    assert cfg.workers["workers"]["deepseek_harness"]["interactive"] is False
    for c in data["cases"]:
        if c["request"]["state"].get("interactive") is True:
            bg = [o for o in c["request"]["eligible_options"]
                  if o == "deepseek_harness" or (c["request"].get("option_info_extra") or {}).get(o, {}).get("interactive") is False]
            assert set(bg) <= set(c["gold"].get("forbidden") or []), c["id"]


def test_risk_gate_labels(cfg, data):
    assert cfg.routing["risk"]["high_requires_human_approval"] is True
    for c in data["cases"]:
        r = c["request"]
        if r["risk"] == "high":
            approved = bool(r["state"].get("human_approval"))
            assert bool(c["gold"].get("escalate")) is (not approved), c["id"]


def test_gpu_cases_escalate(cfg, data):
    assert cfg.routing["task_classes"]["gpu_workload"]["workers"] == []
    for c in data["cases"]:
        if c["request"]["task_type"] == "gpu_workload":
            assert c["gold"].get("escalate")


def test_heldout_e2e_expectations_hold_under_policy(cfg, data):
    """Layer-3 expectations are policy facts: a deterministic chooser must satisfy all of them."""
    res = E.run_e2e(cfg, E._Baseline("first"), data)
    assert res["passed"] == res["n"] == len(data["e2e_cases"]), [c for c in res["cases"] if not c["passed"]]


def test_heldout_runs_end_to_end_with_a_baseline(cfg):
    res = E.run_eval(cfg, "baseline:label-prior", dataset=E.HELDOUT)
    l1 = res["variants"]["bare"]["layer1_decision_quality"]
    assert set(l1["by_language"]) == {"en", "tr"}
    assert res["layer3_end_to_end_routing"]["passed"] == res["layer3_end_to_end_routing"]["n"]
    assert res["variants"]["bare"]["layer2_protocol_compliance"]["compliance_rate"] == 1.0
