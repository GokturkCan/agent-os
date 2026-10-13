"""Run 2 / R2.10 — SystemOne/FastGate backend-neutral contract (no decision model integrated)."""
import pytest

from agentos import capability_policy as CP
from agentos import capability_probes as P
from agentos import capability_registry as R
from agentos import systemone as S

OPTS = ("claude-code", "codex")


def _req(options=OPTS, questions=None):
    return S.SystemOneRequest(task_type="coding", eligible_options=tuple(options),
                              questions=questions or (S.Question("executor"),),
                              required_capabilities=("code.edit",), risk="low",
                              cost_profile="existing_subscription", resource_state={"msi": "down"})


class FixedBackend:
    name = "fixed"

    def __init__(self, choice, confidence=S.Confidence(), escalate=False):
        self.choice, self.confidence, self.escalate = choice, confidence, escalate
        self.calls = 0

    def decide(self, request):
        self.calls += 1
        return S.SystemOneResponse((S.Answer("executor", self.choice, self.confidence),), self.escalate,
                                   "backend-choice", self.name)


# ------------------------------------------------------------ confidence semantics
def test_confidence_kinds_are_explicit():
    assert not S.Confidence(0.97, "raw").is_calibrated
    assert S.Confidence(0.97, "calibrated", "platt-coding-v1").is_calibrated
    with pytest.raises(ValueError):
        S.Confidence(0.9, "calibrated")                      # calibrated needs a calibrator id
    with pytest.raises(ValueError):
        S.Confidence(0.9, "raw", "platt-v1")                 # raw cannot pretend to be calibrated
    with pytest.raises(ValueError):
        S.Confidence(1.4, "raw")
    with pytest.raises(ValueError):
        S.Confidence(0.5, "none")
    with pytest.raises(ValueError):
        S.Confidence(0.5, "probability")


def test_threshold_policy_never_accepts_raw_confidence():
    pol = S.ConfidencePolicy(threshold=0.92, calibration_id="isotonic-coding-v2")
    assert pol.accepts(S.Confidence(0.999, "raw")) == (False, "uncalibrated-confidence")
    assert pol.accepts(S.Confidence()) == (False, "uncalibrated-confidence")
    assert pol.accepts(S.Confidence(0.99, "calibrated", "platt-other")) == (False, "uncalibrated-confidence")
    assert pol.accepts(S.Confidence(0.95, "calibrated", "isotonic-coding-v2")) == (True, "backend-choice")
    assert pol.accepts(S.Confidence(0.50, "calibrated", "isotonic-coding-v2")) == (False, "low-confidence")


# ------------------------------------------------------------ contract enforcement
def test_default_backend_escalates():
    r = S.system_one(_req())
    assert (r.escalate, r.reason_code, r.backend) == (True, "no-backend", "null")


def test_no_eligible_options_escalates_without_calling_backend():
    b = FixedBackend("claude-code")
    r = S.system_one(_req(options=()), b)
    assert (r.escalate, r.reason_code, b.calls) == (True, "no-eligible-options", 0)


def test_choice_outside_eligible_set_is_discarded():
    r = S.system_one(_req(), FixedBackend("deepseek-harness", S.Confidence(0.99, "raw")))
    assert (r.escalate, r.reason_code, r.answers) == (True, "ineligible-choice", ())


def test_choice_outside_question_options_is_discarded():
    q = S.Question("executor", options=("codex",))
    assert S.system_one(_req(questions=(q,)), FixedBackend("claude-code")).reason_code == "ineligible-choice"


def test_valid_choice_passes_through_with_its_confidence_kind():
    r = S.system_one(_req(), FixedBackend("codex", S.Confidence(0.7, "raw")))
    assert not r.escalate and r.answer("executor").choice == "codex"
    assert r.answer("executor").confidence.kind == "raw"     # never silently upgraded


def test_backend_errors_and_bad_responses_escalate():
    class Boom:
        name = "boom"

        def decide(self, request):
            raise RuntimeError("model crashed")

    class Junk:
        name = "junk"

        def decide(self, request):
            return {"choice": "codex"}
    assert S.system_one(_req(), Boom()).reason_code == "backend-error"
    assert S.system_one(_req(), Junk()).reason_code == "backend-error"


def test_unanswered_question_and_backend_escalation_respected():
    two = (S.Question("executor"), S.Question("needs_review", "yes_no"))
    assert S.system_one(_req(questions=two), FixedBackend("codex")).reason_code == "unanswered-question"
    r = S.system_one(_req(), FixedBackend("codex", escalate=True))
    assert r.escalate


def test_policy_order_backend_is_a_heuristic_reference():
    assert isinstance(S.PolicyOrderBackend(), S.SystemOneBackend)
    r = S.system_one(_req(), S.PolicyOrderBackend())
    a = r.answer("executor")
    assert (r.escalate, a.choice, a.confidence.kind, a.reason_code) == (False, "claude-code", "none", "policy-order")


def test_request_from_plan_only_offers_policy_eligible_executors(cfg):
    reg = R.load(cfg)
    probes = P.static_probes(reg, default={"available": "present", "health": "healthy", "auth": "present"})
    plan = CP.plan(reg, CP.CapabilityRequest(required=("code.references",)), probes)
    req = S.request_from_plan(plan, task_type="coding")
    assert req.eligible_options == ("claude-code",)          # codex/opencode lack a serena path
    assert S.system_one(req, FixedBackend("codex")).reason_code == "ineligible-choice"
    assert S.system_one(req, S.PolicyOrderBackend()).answer("executor").choice == "claude-code"


def test_systemone_module_integrates_no_decision_model():
    src = (R.REPO_ROOT / "agentos" / "systemone.py").read_text().lower()
    code = src.split('"""', 2)[2]                            # skip the module docstring
    for name in ("laya", "ollaya", "jev", "decider", "kev", "mlx", "import requests", "urllib", "subprocess"):
        assert name not in code
