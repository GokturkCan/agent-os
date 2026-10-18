"""Open-Jev-2B optimisation study (R3.2H): scorer client, decision policies, deterministic prefilter. EVALUATION ONLY, never a default.

Nothing here is registered in systemone.BACKENDS, config/systemone.yaml or routing; objects are passed explicitly to
`systemone_eval.run_eval(backend=...)`. Baseline reproduces the shipped `openjev-2b` worker's decisions; the other modes change ONLY how the per-candidate
probabilities are produced or turned into a decision:

  baseline   candidates scored in the caller's order, argmax (first index on ties)                  == shipped worker
  canonical  candidates sorted by id before scoring; ties -> lowest id                              order invariance by construction
  alias      ids replaced by neutral per-request aliases (systemone_pipeline.neutralize), sorted    reduces label reliance
  ensemble   mean of canonical-raw and alias probabilities per original id                          label de-biasing

Optional layers (all chosen on calibration/optimisation partitions only): `prefilter` (deterministic policy facts remove options BEFORE the model),
`tau` (escalate when the calibrated confidence is below tau), abstention through the existing `none_fits` candidate.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import time
from dataclasses import replace
from pathlib import Path

from . import systemone as S
from . import systemone_adapter as A
from . import systemone_calibration as K
from . import systemone_pipeline as P
from .systemone_workers.laya_worker import criteria_for

SCORER = "openjev_scorer.py"


class ScoreClient:
    """Cached client for the research scorer. The cache key is the exact (state, prompt, criteria) payload, so identical requests are never rescored."""

    def __init__(self, cfg, cache_path: str | os.PathLike | None = None, idle_exit_seconds: float = 0.0, timeout: float = 90.0):
        conf = A.definitions(cfg)["openjev-2b"]
        argv = [A._expand(a, cfg, conf) for a in conf["argv"]]
        argv[1] = str(Path(argv[1]).with_name(SCORER))               # same python, same checkpoint args, research scorer script
        if idle_exit_seconds:
            argv += ["--idle-exit-seconds", str(idle_exit_seconds)]
        self.runtime = A.SubprocessJsonRuntime(argv, name="openjev-scorer", cwd=str(Path(cfg.root).resolve()),
                                               startup_timeout=240.0, cooldown=0.0)
        self.timeout, self.cache, self.path = timeout, {}, Path(cache_path) if cache_path else None
        self.calls = self.hits = 0
        self.model_ms: list[float] = []
        if self.path and self.path.exists():
            for line in self.path.read_text().splitlines():
                rec = json.loads(line)
                self.cache[rec["k"]] = rec["p"]

    @staticmethod
    def key(state, prompt, criteria) -> str:
        return hashlib.sha256(json.dumps([state, prompt, criteria], sort_keys=False, ensure_ascii=False, default=str).encode()).hexdigest()

    def score(self, state, prompt, criteria: list) -> list[float]:
        k = self.key(state, prompt, criteria)
        if k in self.cache:
            self.hits += 1
            return self.cache[k]
        reply = self.runtime.ask({"state": state, "prompt": prompt, "criteria": criteria}, self.timeout)
        probs = reply.get("probs") if isinstance(reply, dict) else None
        if not (isinstance(probs, list) and len(probs) == len(criteria) and all(isinstance(p, (int, float)) and math.isfinite(p) for p in probs)
                and math.isclose(sum(probs), 1.0, abs_tol=1e-4)):
            raise A.AdapterReject("malformed-output", "scorer reply")
        self.calls += 1
        self.model_ms.append(float(reply.get("ms") or 0.0))
        self.cache[k] = probs
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a") as fh:
                fh.write(json.dumps({"k": k, "p": probs}) + "\n")
        return probs

    def close(self) -> None:
        self.runtime.close()


# ------------------------------------------------------------ deterministic prefilter (a PROPOSAL for policy, not production code)
def prefilter(request: S.SystemOneRequest) -> tuple[list[str], str | None]:
    """(surviving options, escalation reason or None) from deterministic facts the control plane already holds. It only ever REMOVES options."""
    opts, info, st = list(request.eligible_options), request.option_info or {}, request.state or {}
    if request.risk == "high" and not st.get("human_approval"):
        return [], "no-eligible-options"                              # the risk gate (routing.yaml) runs before SystemOne in production
    drop = set()
    for o in opts:
        i = info.get(o) or {}
        if i.get("missing") or i.get("status") == "unavailable":
            drop.add(o)
        if st.get("interactive") and i.get("interactive") is False:
            drop.add(o)
        if request.cost_profile == "subscription_first" and i.get("access") == "api":
            drop.add(o)
    for key in ("primary_worker", "previous_worker"):
        if st.get(key) in opts and len(opts) > 1:
            drop.add(st[key])
    left = [o for o in opts if o not in drop]
    return left, (None if left else "no-eligible-options")


def _confidence(probs: list[float]) -> float:
    n = len(probs)
    return 1.0 if n == 1 else (max(probs) - 1.0 / n) / (1.0 - 1.0 / n)         # same formula as jev.metrics.choice_confidence


class OpenJevBackend:
    """Evaluation backend over a ScoreClient. See module docstring for modes."""

    def __init__(self, client: ScoreClient | None, mode: str = "baseline", *, use_prefilter: bool = False, tau: float | None = None,
                 calibrator: dict | None = None, name: str | None = None):
        assert mode in ("baseline", "canonical", "alias", "ensemble", "deterministic")
        self.client, self.mode, self.use_prefilter, self.tau, self.calibrator = client, mode, use_prefilter, tau, calibrator
        self.name = name or f"openjev:{mode}{'+prefilter' if use_prefilter else ''}{f'+tau{tau}' if tau is not None else ''}"
        self.trace: list[dict] = []

    # -- helpers
    def _probs(self, request, options) -> tuple[list[str], list[float], str | None]:
        """(candidate keys incl. abstain label, probabilities aligned to keys, abstain key) in the mode's candidate order.
        The prompt/state/criteria are built from the SAME adapter payload the shipped worker receives, so `baseline` reproduces it."""
        def payload_for(req):
            sub = replace(req, eligible_options=tuple(options if req is request else req.eligible_options))
            return A.build_payload(sub, sub.questions[0])

        def score(payload, sorter):
            crit, abst = criteria_for({"options": payload["options"], "option_info": payload.get("option_info"),
                                       "allow_abstain": payload.get("allow_abstain")})
            pairs = self._ordered(crit, sorter)
            probs = self.client.score(payload["state"], payload["question"]["prompt"] or "Choose one.", [[k, d] for k, d in pairs])
            return [k for k, _ in pairs], probs, abst

        sub = replace(request, eligible_options=tuple(options))
        if self.mode in ("alias", "ensemble"):
            aliased, back = P.neutralize(sub)
            ka, pa, abst = score(A.build_payload(aliased, aliased.questions[0]), sorted)
            by_orig = {back.get(k, k): p for k, p in zip(ka, pa)}
            if self.mode == "alias":
                keys = sorted(by_orig)
                return keys, [by_orig[k] for k in keys], abst
        keys, probs, abst = score(A.build_payload(sub, sub.questions[0]), None if self.mode == "baseline" else sorted)
        if self.mode == "ensemble":
            pr = dict(zip(keys, probs))
            keys = sorted(pr)
            return keys, [(pr[k] + by_orig[k]) / 2.0 for k in keys], abst
        return keys, probs, abst

    @staticmethod
    def _ordered(criteria, sorter):
        pairs = list(criteria.items()) if isinstance(criteria, dict) else [(c, None) for c in criteria]
        return pairs if sorter is None else sorted(pairs, key=lambda kv: kv[0])

    def _escalate(self, code):
        return S.SystemOneResponse((), True, code, self.name)

    def decide(self, request: S.SystemOneRequest) -> S.SystemOneResponse:
        t0 = time.perf_counter()
        options = list(request.eligible_options)
        if self.use_prefilter or self.mode == "deterministic":
            options, why = prefilter(request)
            if why:
                return self._escalate(why)
            if len(options) == 1 or self.mode == "deterministic":
                pick = min(options, key=lambda o: ("claude_code", "codex", "deepseek_harness").index(o) if o in ("claude_code", "codex", "deepseek_harness") else 99)
                return S.SystemOneResponse((S.Answer("worker", pick, S.Confidence(), "policy-order"),), False, "policy-order", self.name)
        try:
            keys, probs, abstain = self._probs(request, options)
        except A.AdapterReject as exc:
            return self._escalate(exc.reason)
        top = max(range(len(probs)), key=lambda i: (probs[i], -i if self.mode == "baseline" else 0)) if self.mode == "baseline" \
            else min((i for i, p in enumerate(probs) if p == max(probs)), key=lambda i: keys[i])
        conf = _confidence(probs)
        cal = K.apply_map(self.calibrator, conf) if self.calibrator else conf
        self.trace.append({"keys": keys, "probs": probs, "choice": keys[top], "conf": conf, "ms": round((time.perf_counter() - t0) * 1000, 3)})
        if abstain is not None and keys[top] == abstain:
            return self._escalate("backend-abstained")
        if self.tau is not None and cal < self.tau:
            return self._escalate("low-confidence")
        return S.SystemOneResponse((S.Answer("worker", keys[top], S.Confidence(conf, "raw"), "backend-choice"),), False, "backend-choice", self.name)
