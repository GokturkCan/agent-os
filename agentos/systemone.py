"""SystemOne / FastGate — backend-neutral typed decision contract (Run 2, R2.10).

CONTRACT ONLY. No decision model is integrated here; Laya-MLX, Decider-2B,
Kev-4B, OpenJev-like, Jev cloud and similar backends are Run 3. FastGate is
this abstraction, not any one of those models.

  deterministic policy -> eligible options -> system_one(request) -> choice/confidence
                                                               -> execute or escalate

Invariants enforced by `system_one()` (not by backends):
- SystemOne only chooses among policy-eligible options. An answer naming
  anything outside `eligible_options` is discarded and the call escalates;
  hard policy can never be bypassed.
- No eligible options => escalate without calling the backend.
- Backend failure => escalate (never raise into the caller).

Confidence semantics (designed for Run 3 calibration):
- A raw backend score is NOT a probability. `Confidence.kind` says what it is:
  `none` (no score), `raw` (uncalibrated score), or `calibrated` (mapped by a
  named calibrator, e.g. Platt/isotonic fitted on a workload; requires
  `calibration_id`).
- Threshold policies accept only calibrated confidence carrying the expected
  `calibration_id` (`ConfidencePolicy.accepts`). `if confidence > 0.92:
  execute` on a raw score is unrepresentable by design.
- Run 3 will measure accuracy/ECE and fit calibrators; nothing here does.

ContextGate (result pruning, compaction, retrieval selection; KEEP / DROP /
TRUNCATE) is a future consumer of this same request/answer shape and is not
implemented in Run 2.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Protocol, runtime_checkable

CONFIDENCE_KINDS = ("none", "raw", "calibrated")
QUESTION_KINDS = ("choose", "yes_no")
REASON_CODES = ("backend-choice", "policy-order", "no-backend", "no-eligible-options", "ineligible-choice",
                "backend-error", "low-confidence", "uncalibrated-confidence", "unanswered-question")


@dataclass(frozen=True)
class Confidence:
    value: float | None = None
    kind: str = "none"
    calibration_id: str | None = None    # calibrator name/version; required iff kind == "calibrated"

    def __post_init__(self):
        if self.kind not in CONFIDENCE_KINDS:
            raise ValueError(f"invalid confidence kind {self.kind!r}")
        if self.kind == "none":
            if self.value is not None:
                raise ValueError("confidence kind 'none' carries no value")
        elif self.value is None or not 0.0 <= float(self.value) <= 1.0:
            raise ValueError("confidence value must be within [0, 1]")
        if (self.kind == "calibrated") != bool(self.calibration_id):
            raise ValueError("calibration_id is required for, and only for, calibrated confidence")

    @property
    def is_calibrated(self) -> bool:
        return self.kind == "calibrated"


@dataclass(frozen=True)
class Question:
    id: str
    kind: str = "choose"
    prompt: str = ""
    options: tuple[str, ...] = ()        # for "choose": defaults to the request's eligible options

    def __post_init__(self):
        if self.kind not in QUESTION_KINDS:
            raise ValueError(f"invalid question kind {self.kind!r}")


@dataclass(frozen=True)
class SystemOneRequest:
    task_type: str
    questions: tuple[Question, ...]
    eligible_options: tuple[str, ...]    # produced by deterministic policy — the only legal choices
    state: Mapping = field(default_factory=dict)
    required_capabilities: tuple[str, ...] = ()
    risk: str = "low"
    cost_profile: str | None = None
    resource_state: Mapping = field(default_factory=dict)


@dataclass(frozen=True)
class Answer:
    question_id: str
    choice: str | bool | None
    confidence: Confidence = Confidence()
    reason_code: str = "backend-choice"


@dataclass(frozen=True)
class SystemOneResponse:
    answers: tuple[Answer, ...]
    escalate: bool
    reason_code: str
    backend: str

    def answer(self, question_id: str) -> Answer | None:
        return next((a for a in self.answers if a.question_id == question_id), None)


@runtime_checkable
class SystemOneBackend(Protocol):
    name: str

    def decide(self, request: SystemOneRequest) -> SystemOneResponse: ...


class NullBackend:
    """Default: no decision model configured -> always escalate."""
    name = "null"

    def decide(self, request: SystemOneRequest) -> SystemOneResponse:
        return SystemOneResponse((), True, "no-backend", self.name)


class PolicyOrderBackend:
    """Reference heuristic backend: picks the first eligible option (the
    deterministic policy's ranking) with no confidence claim."""
    name = "policy-order"

    def decide(self, request: SystemOneRequest) -> SystemOneResponse:
        answers = []
        for q in request.questions:
            if q.kind == "choose":
                opts = [o for o in (q.options or request.eligible_options) if o in request.eligible_options]
                answers.append(Answer(q.id, opts[0] if opts else None, Confidence(), "policy-order"))
        return SystemOneResponse(tuple(answers), False, "policy-order", self.name)


def _escalate(code: str, backend: str, answers=()) -> SystemOneResponse:
    return SystemOneResponse(tuple(answers), True, code, backend)


def system_one(request: SystemOneRequest, backend: SystemOneBackend | None = None) -> SystemOneResponse:
    """Ask a backend to choose among ALREADY ELIGIBLE options; enforce the contract."""
    backend = backend or NullBackend()
    name = getattr(backend, "name", type(backend).__name__)
    if not request.eligible_options:
        return _escalate("no-eligible-options", name)
    try:
        resp = backend.decide(request)
    except Exception:
        return _escalate("backend-error", name)
    if not isinstance(resp, SystemOneResponse):
        return _escalate("backend-error", name)
    if resp.escalate:
        return resp
    allowed = set(request.eligible_options)
    for q in request.questions:
        a = resp.answer(q.id)
        if a is None or a.choice is None:
            return _escalate("unanswered-question", name, resp.answers)
        if q.kind == "choose" and (a.choice not in allowed or (q.options and a.choice not in q.options)):
            return _escalate("ineligible-choice", name)       # never bypass deterministic policy
        if q.kind == "yes_no" and not isinstance(a.choice, bool):
            return _escalate("ineligible-choice", name)
    return resp


@dataclass(frozen=True)
class ConfidencePolicy:
    """Auto-execute threshold that is only meaningful for one calibrator."""
    threshold: float
    calibration_id: str

    def accepts(self, confidence: Confidence) -> tuple[bool, str]:
        if not confidence.is_calibrated:
            return False, "uncalibrated-confidence"
        if confidence.calibration_id != self.calibration_id:
            return False, "uncalibrated-confidence"
        return (True, "backend-choice") if confidence.value >= self.threshold else (False, "low-confidence")


def request_from_plan(plan, questions: tuple[Question, ...] | None = None, *, task_type: str = "",
                      state: Mapping | None = None, risk: str = "low", cost_profile: str | None = None,
                      resource_state: Mapping | None = None) -> SystemOneRequest:
    """Build a request whose only legal choices are a CapabilityPlan's eligible executors."""
    return SystemOneRequest(
        task_type=task_type, eligible_options=tuple(plan.eligible_executors),
        questions=questions or (Question("executor", "choose", "Which eligible executor should run this task?"),),
        state=dict(state or {}), required_capabilities=tuple(plan.required), risk=risk,
        cost_profile=cost_profile, resource_state=dict(resource_state or {}))
