"""WakeGate prototype (R3.2G): should a sleeping task be resumed with a (local or cloud) reasoning turn? OPT-IN, OFFLINE.

Pattern from shitianfang/wakegate (ask before resuming; wake after `max_skips`; every failure path wakes), adapted to the
Agent OS ordering: deterministic C0 rules first, the SystemOne backend only for what rules cannot decide.

  event + wait state
    -> must-wake rules (approval / high risk / security marker / error or failure / direct user message / near deadline)
         -> WAKE without asking any model (a model can never suppress these)
    -> skip limit reached -> WAKE                     (bounded deferral)
    -> timer with an unchanged observation -> DEFER   (nothing to look at)
    -> SystemOne backend: wake_local_reasoning | wake_cloud_candidate | defer_no_change
         any escalation, error, timeout or abstention -> WAKE (local)   (fail toward waking, never toward silence)

`wake_cloud_candidate` is only a label: it marks the turn as a candidate for C4 escalation, which stays separately governed
(approval, budget). Nothing here calls a model API other than the configured local SystemOne backend, and nothing here is
wired into Hermes or any hook.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass, field

from . import systemone as S

WAKE_LOCAL, WAKE_CLOUD, DEFER = "wake_local_reasoning", "wake_cloud_candidate", "defer_no_change"
ACTIONS = (WAKE_LOCAL, WAKE_CLOUD, DEFER)
PROMPT = "The agent is asleep waiting for something. Given this event, should it wake up and reason now, or keep sleeping?"
SECURITY = re.compile(r"credential|password|secret|token|api[ _-]?key|security|breach|vulnerab|unauthori[sz]ed|"
                      r"kimlik bilgisi|parola|şifre|güvenlik|yetkisiz|ihlal", re.I)
FAILURE = re.compile(r"\b(fail(ed|ure)?|error|exception|crash(ed)?|down|outage|timeout|timed out|rollback|incident)\b|"
                     r"hata|başarısız|çöktü|kesinti|zaman aşımı|"
                     # R3.5: failure signals without an "error"/"failed" word (substring on purpose: ECONNREFUSED, "OOM killed").
                     r"refus|reject|denied|forbid|unreachable|unavailable|expire|revoke|overdue|suspend|locked|killed|\boom\b|"
                     r"reddedil|erişilemi|süresi doldu|\b(HTTP|status|code)[ :=]*(401|403|429|5[0-9]{2})\b|\(403\)", re.I)
APPROVAL = re.compile(r"approv|sign[- ]?off|consent|onay|izin", re.I)
DEADLINE_MINUTES = 60


@dataclass(frozen=True)
class Event:
    kind: str                                  # timer | email | webhook | message | ci | alert | calendar ...
    summary: str = ""
    source: str = ""
    risk: str = "low"
    markers: tuple[str, ...] = ()
    from_user: bool = False                    # a direct message from the human owner
    requires_approval: bool = False
    deadline_minutes: int | None = None
    observation: dict = field(default_factory=dict)


@dataclass
class WaitState:
    waiting_for: str
    last_observation_sha: str | None = None
    skipped: int = 0
    max_skips: int = 10


@dataclass(frozen=True)
class Verdict:
    action: str
    reason: str                                # rule:<name> | model | fallback:<reason code> | skip-limit
    model_called: bool
    latency_ms: float
    confidence: float | None = None

    @property
    def wake(self) -> bool:
        return self.action != DEFER


def observation_sha(obs: dict) -> str:
    return hashlib.sha256(json.dumps(obs or {}, sort_keys=True, default=str).encode()).hexdigest()


def must_wake(event: Event) -> tuple[str, str] | None:
    """(action, rule) for events no model may suppress, else None."""
    text = " ".join([event.summary, event.source, *event.markers])
    if event.requires_approval or APPROVAL.search(text):
        return WAKE_CLOUD, "approval"
    if event.risk == "high":
        return WAKE_CLOUD, "high-risk"
    if SECURITY.search(text):
        return WAKE_CLOUD, "security"
    if event.from_user:
        return WAKE_LOCAL, "user-message"
    if FAILURE.search(text) or {"failure", "error"} & set(event.markers):
        return WAKE_LOCAL, "failure"
    if event.deadline_minutes is not None and event.deadline_minutes <= DEADLINE_MINUTES:
        return WAKE_LOCAL, "deadline"
    return None


def gate(event: Event, state: WaitState, backend=None, *, use_model: bool = True) -> Verdict:
    """Decide, and update `state` (skip counter, last observation). Never raises for a backend problem."""
    t0 = time.perf_counter()
    ms = lambda: round((time.perf_counter() - t0) * 1000, 3)

    def done(action, reason, called=False, conf=None):
        state.skipped = state.skipped + 1 if action == DEFER else 0
        if event.observation:
            state.last_observation_sha = observation_sha(event.observation)
        return Verdict(action, reason, called, ms(), conf)

    rule = must_wake(event)
    if rule:
        return done(rule[0], f"rule:{rule[1]}")
    if state.skipped >= state.max_skips:
        return done(WAKE_LOCAL, "skip-limit")
    if event.kind == "timer" and event.observation and observation_sha(event.observation) == state.last_observation_sha:
        return done(DEFER, "rule:no-change")
    if not use_model or backend is None:
        return done(WAKE_LOCAL, "fallback:no-model")        # rules-only mode: undecided events wake
    req = S.SystemOneRequest(
        task_type="wake_decision", risk=event.risk, eligible_options=ACTIONS,
        questions=(S.Question("wake", "choose", PROMPT),),
        state={"waiting_for": state.waiting_for, "event_kind": event.kind, "event_source": event.source,
               "event_summary": event.summary, **({"observation": json.dumps(event.observation, sort_keys=True)[:200]}
                                                  if event.observation else {})})
    resp = S.system_one(req, backend)
    if resp.escalate:
        return done(WAKE_LOCAL, f"fallback:{resp.reason_code}", called=True)
    a = resp.answer("wake")
    return done(a.choice, "model", called=True, conf=a.confidence.value)
