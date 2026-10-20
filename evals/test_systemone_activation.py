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


# ------------------------------------------------ runtime guard: config.validate is NEVER called below
from agentos import systemone as S
from agentos import systemone_adapter as A

CLS = {"type": "classification"}


def _cfg(cfg, mutate):
    data = copy.deepcopy(cfg.data)
    mutate(data)
    return C.Config(root=cfg.root, data=data)


@pytest.mark.parametrize("name", ["laya-mlx", "decider-mlx", "kev-mlx", "openjev-2b", "openjev-masked"])
def test_runtime_rejects_unlisted_adapter_backend_without_validate(cfg, name):
    A.close_all()
    c = _cfg(cfg, lambda d: d["routing"].update(systemone={"backend": name}))
    d = router.route(c, CLS)
    base = router.route(cfg, CLS)
    assert d.systemone["backend"] == "null" and d.systemone["escalate"] is True
    assert any("not in activation.production_backends" in t and "using null backend" in t for t in d.trace)
    assert (d.stage, d.worker, d.provider, d.exit_state) == (base.stage, base.worker, base.provider, base.exit_state)
    assert A._CACHE == {}                                   # the adapter was never even built


def test_runtime_allows_listed_backend_and_builtins(cfg, monkeypatch):
    seen = []
    monkeypatch.setattr(S, "resolve_backend", lambda spec=None, cfg=None: (seen.append(spec), S.NullBackend())[1])
    def listed(d):
        d["routing"]["systemone"] = {"backend": "laya-mlx"}
        d["systemone"]["activation"]["production_backends"] = ["laya-mlx"]
    router.route(_cfg(cfg, listed), CLS)
    router.route(_cfg(cfg, lambda d: d["routing"].update(systemone={"backend": "policy-order"})), CLS)
    assert seen == ["laya-mlx", "policy-order"]


def test_runtime_guard_fails_closed_on_malformed_allowlist(cfg):
    for bad in (None, "laya-mlx", {"laya-mlx": 1}, [1, None]):
        def m(d, bad=bad):
            d["routing"]["systemone"] = {"backend": "laya-mlx"}
            d["systemone"]["activation"] = {"production_backends": bad}
        d = router.route(_cfg(cfg, m), CLS)
        assert d.systemone["backend"] == "null"
    d = router.route(_cfg(cfg, lambda d: (d["routing"].update(systemone={"backend": "laya-mlx"}),
                                          d["systemone"].pop("activation"))), CLS)
    assert d.systemone["backend"] == "null"


def test_explicit_backend_argument_is_the_research_path_and_stays_possible(cfg):
    d = router.route(cfg, CLS, systemone_backend="policy-order")
    assert d.systemone["backend"] == "policy-order"
    class Stub:
        name = "stub"
        def decide(self, request):
            return S.SystemOneResponse((), True, "backend-abstained", "stub")
    assert router.route(cfg, CLS, systemone_backend=Stub()).systemone["backend"] == "stub"


def test_runtime_fastgate_model_needs_allowlist_and_usable_status(cfg):
    def tier(d, status=None, listed=False):
        d["models"]["tiers"]["fastgate"]["model"] = "laya-mlx"
        if status:
            d["models"]["models"]["laya-mlx"]["status"] = status
        if listed:
            d["systemone"]["activation"]["fastgate_models"] = ["laya-mlx"]
    t = lambda **kw: router._tier_model(_cfg(cfg, lambda d: tier(d, **kw)), "fastgate")
    assert t() is None                                       # candidate, unlisted
    assert t(listed=True) is None                            # listed but candidate (not USABLE)
    assert t(status="measured") is None                      # USABLE but unlisted (the edit-two-files attack)
    assert t(status="measured", listed=True) == "laya-mlx"   # both required
    assert router._tier_model(cfg, "fastgate") is None       # shipped default
    d = router.route(_cfg(cfg, lambda d: tier(d, status="measured")), CLS)
    assert any("fastgate: skip" in x for x in d.trace)
