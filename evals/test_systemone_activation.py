"""Activation boundary: routing.yaml / models.yaml are the tunable (unprotected) surface, so selecting a
model-backed SystemOne backend or a fastgate tier model must be a validation error unless the protected
config/systemone.yaml lists it. Laya is a research candidate and never production-usable."""
import copy

import pytest

from agentos import config as C
from agentos import router
from agentos.permissions import is_protected
from agentos.selfimprove import Candidate, GateViolation


def _validate(cfg, mutate):
    data = copy.deepcopy(cfg.data)
    mutate(data)
    return C.validate(C.Config(root=cfg.root, data=data))


def test_shipped_defaults_validate_and_stay_null(cfg):
    assert C.validate(cfg) == []
    assert cfg.routing["systemone"]["backend"] == "null"
    assert cfg.models["tiers"]["fastgate"]["model"] is None
    act = cfg.systemone["activation"]
    assert act["production_backends"] == [] and act["fastgate_models"] == []


def test_laya_is_not_a_usable_status(cfg):
    m = cfg.models["models"]["laya-mlx"]
    assert m["status"] == "candidate" and m["status"] not in C.USABLE
    assert m["evidence"]                                   # historical benchmark evidence is preserved


@pytest.mark.parametrize("name", ["laya-mlx", "decider-mlx", "kev-mlx", "openjev-2b", "openjev-masked"])
def test_selecting_an_adapter_backend_in_routing_is_rejected(cfg, name):
    errs = _validate(cfg, lambda d: d["routing"].update(systemone={"backend": name}))
    assert any("benchmark-only adapter backend" in e and name in e for e in errs)


@pytest.mark.parametrize("name", ["null", "policy-order"])
def test_builtin_backends_stay_selectable(cfg, name):
    assert _validate(cfg, lambda d: d["routing"].update(systemone={"backend": name})) == []


def test_setting_fastgate_model_in_models_yaml_is_rejected(cfg):
    errs = _validate(cfg, lambda d: d["models"]["tiers"]["fastgate"].update(model="laya-mlx"))
    assert any("not listed" in e and "activation.fastgate_models" in e for e in errs)


def test_even_when_listed_a_non_usable_model_is_rejected(cfg):
    def both(d):
        d["models"]["tiers"]["fastgate"]["model"] = "laya-mlx"
        d["systemone"]["activation"]["fastgate_models"] = ["laya-mlx"]
    errs = _validate(cfg, both)
    assert any("does not have a usable status" in e for e in errs)
    assert not any("not listed" in e for e in errs)


def test_router_still_ignores_a_candidate_fastgate_model(cfg):
    data = copy.deepcopy(cfg.data)
    data["models"]["tiers"]["fastgate"]["model"] = "laya-mlx"
    assert router._tier_model(C.Config(root=cfg.root, data=data), "fastgate") is None


def test_listing_in_the_protected_file_is_the_only_way_to_activate_a_backend(cfg):
    assert is_protected("config/systemone.yaml")
    assert not is_protected("config/routing.yaml") and not is_protected("config/models.yaml")   # tunable by design
    def activated(d):
        d["routing"]["systemone"] = {"backend": "laya-mlx"}
        d["systemone"]["activation"]["production_backends"] = ["laya-mlx"]
    assert _validate(cfg, activated) == []


def test_unrelated_routing_changes_remain_valid(cfg):
    assert _validate(cfg, lambda d: d["routing"]["risk"]["high_risk_task_markers"].append("new_marker")) == []


def test_candidate_cannot_edit_the_activation_lists(tmp_path):
    c = Candidate.propose(tmp_path / "si", "act1", producer="codex", rationale="activate", lesson_ref="x")
    with pytest.raises(GateViolation, match="protected"):
        c.isolate("agentos/cand", ["config/routing.yaml", "config/systemone.yaml"])
