"""R3.3 compute-node contract: registry, authorization ladder, job/error/state contract. Mock client only:
no network, no MSI, no inference."""
import copy

import pytest

from agentos import compute, router
from agentos import config as C
from agentos import compute_jobs as J
from agentos.permissions import is_protected

REV = "rev-1234"
OFFER = {"node": "msi", "capability": "llm.chat", "operations": ["generate", "chat"], "runtime": "openai-compat",
         "model": {"id": "vendor/model", "revision": REV, "quantization": "q4", "license": "apache-2.0"},
         "limits": {"context_tokens": 8192}, "hardware": {"vram_mb": 6000},
         "features": {"streaming": True, "tool_calling": False},
         "benchmark": {"state": "benchmarked", "evidence": ["audit/laya-mlx-r3.2-2026-10-14.md"]}}
AUTH = {"offering": "msi-chat", "revision": REV, "max_data_class": "internal", "approval_ref": "HUMAN-1"}


def mkcfg(cfg, *, enabled=True, offering=True, auth=True, mutate=None):
    data = copy.deepcopy(cfg.data)
    if enabled:
        data["resources"]["nodes"]["msi"]["compute"].update(enabled=True, endpoint_ref="msi-private",
                                                            auth_ref="env:MSI_TOKEN")
    if offering:
        data["compute"]["offerings"] = {"msi-chat": copy.deepcopy(OFFER)}
    if auth:
        data["compute"]["authorizations"] = [dict(AUTH)]
    if mutate:
        mutate(data)
    return C.Config(root=cfg.root, data=data)


def req(**kw):
    base = dict(job_id="job1", idempotency_key="key1", capability="llm.chat", offering="msi-chat",
                approved_node="msi", operation="chat", audit=J.AuditRef("task-1", "run-1"),
                params={"prompt": "hi"}, deadline_seconds=30, data_class="internal")
    return J.JobRequest(**{**base, **kw})


def body(r, status="completed", **over):
    b = {"v": 1, "job_id": r.job_id, "status": status, "node": r.approved_node, "offering": r.offering,
         "capability": r.capability, "usage": {"wall_ms": 12, "tokens_in": 3, "tokens_out": 4},
         "provenance": {"model_id": "vendor/model", "model_revision": REV, "runtime": "x"}}
    if status == "completed":
        b["result"] = {"text": "ok"}
    return {**b, **over}


class Mock:
    def __init__(self, r=None, responses=(), advertise=True, healthy=True, health_exc=None):
        self.req, self.responses, self.calls = r, list(responses), []
        self.adv = {"offerings": {"msi-chat": {"revision": REV, "healthy": True}}} if advertise else {"offerings": {}}
        self.healthy, self.health_exc = healthy, health_exc

    def _next(self):
        r = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(r, Exception):
            raise r
        return r

    def health(self):
        self.calls.append("health")
        if self.health_exc:
            raise self.health_exc
        return {"ok": self.healthy}

    def capabilities(self): self.calls.append("capabilities"); return self.adv
    def resources(self): return {}
    def submit(self, payload): self.calls.append("submit"); return self._next()
    def get(self, job_id): self.calls.append("get"); return self._next()
    def cancel(self, job_id): self.calls.append("cancel"); return {}


def fast(cfg_, r, client, ledger=None, **kw):
    t = iter(range(0, 10_000))
    return J.run_job(cfg_, r, client, ledger, clock=lambda: float(next(t)), sleep=lambda _s: None, **kw)


# ---------------------------------------------------------------- 1-3 defaults / Mac-only
def test_shipped_defaults_valid_and_non_operational(cfg):
    assert C.validate(cfg) == []
    assert compute.offerings(cfg) == {} and compute.authorizations(cfg) == []
    assert compute.node_enabled(cfg, "msi") is False and compute.node_enabled(cfg, "mac") is False
    nc = cfg.resources["nodes"]["msi"]["compute"]
    assert nc["endpoint_ref"] is None and nc["auth_ref"] is None
    assert cfg.resources["nodes"]["msi"]["boot_critical"] is False
    assert is_protected("config/compute.yaml")


def test_run3_activation_defaults_untouched(cfg):
    assert cfg.routing["systemone"]["backend"] == "null" and cfg.models["tiers"]["fastgate"]["model"] is None
    assert cfg.systemone["activation"] == {"production_backends": [], "fastgate_models": []}


def test_mac_only_operation_needs_no_msi(cfg, monkeypatch):
    monkeypatch.setenv("AGENTOS_NODE_MSI", "down")
    base = router.route(cfg, {"type": "classification"})
    enabled = router.route(mkcfg(cfg), {"type": "classification"})       # compute fully configured, node absent
    assert base.to_dict() == enabled.to_dict()                          # routing is untouched by the contract
    assert base.exit_state is None


# ---------------------------------------------------------------- 4 unknown/offline fail safe
def test_default_offline_client_fails_safe_with_no_authorization(cfg):
    r = fast(cfg, req(), None)
    assert (r.status, r.error.code, r.ok) == (J.Status.FAILED, "NOT_AUTHORIZED", False)


def test_offline_node_is_node_unavailable(cfg):
    r = fast(mkcfg(cfg), req(), None)                                   # authorized+enabled, OfflineClient
    assert (r.status, r.error.code, r.error.retryable) == (J.Status.FAILED, "NODE_UNAVAILABLE", True)
    r = fast(mkcfg(cfg), req(), Mock(health_exc=ConnectionError("boom")))
    assert r.error.code == "NODE_UNAVAILABLE"


def test_disabled_node_never_touches_the_client(cfg):
    m = Mock(responses=[body(req())])
    r = fast(mkcfg(cfg, enabled=False), req(), m)
    assert r.error.code == "NODE_UNAVAILABLE" and m.calls == []


def test_unknown_node_or_offering_is_rejected_before_any_call(cfg):
    m = Mock(responses=[body(req())])
    assert fast(mkcfg(cfg), req(approved_node="ghost"), m).error.code == "NOT_AUTHORIZED"
    assert fast(mkcfg(cfg), req(offering="ghost"), m).error.code == "NOT_AUTHORIZED"
    assert m.calls == []


# ---------------------------------------------------------------- 5-6 authorization is config-only
def test_unauthorized_offering_is_rejected_even_if_node_advertises_and_is_healthy(cfg):
    m = Mock(responses=[body(req())])
    r = fast(mkcfg(cfg, auth=False), req(), m)
    assert r.error.code == "NOT_AUTHORIZED" and m.calls == []


def test_advertised_status_cannot_expand_permissions(cfg):
    c = mkcfg(cfg, auth=False)
    adv = {"offerings": {"msi-chat": {"revision": REV, "healthy": True, "authorized": True, "active": True,
                                      "max_data_class": "secret"}}}
    e = compute.evaluate(c, "msi-chat", advertised=adv, node_reachable=True, node_healthy=True)
    assert (e.installed, e.healthy, e.benchmarked, e.authorized, e.active) == (True, True, True, False, False)
    # a node advertising an offering that is not configured creates nothing
    e2 = compute.evaluate(c, "rogue", advertised={"offerings": {"rogue": {"revision": "x", "healthy": True}}},
                          node_reachable=True, node_healthy=True)
    assert e2.configured is False and e2.active is False


def test_ladder_levels_are_independent(cfg):
    c = mkcfg(cfg)
    ok = dict(advertised={"offerings": {"msi-chat": {"revision": REV, "healthy": True}}},
              node_reachable=True, node_healthy=True)
    assert compute.evaluate(c, "msi-chat", **ok).active is True
    assert compute.evaluate(c, "msi-chat", **{**ok, "node_reachable": False}).active is False
    assert compute.evaluate(c, "msi-chat", **{**ok, "node_healthy": False}).healthy is False
    drift = {"offerings": {"msi-chat": {"revision": "other", "healthy": True}}}
    assert compute.evaluate(c, "msi-chat", **{**ok, "advertised": drift}).installed is False
    assert compute.evaluate(mkcfg(cfg, enabled=False), "msi-chat", **ok).active is False
    unbench = mkcfg(cfg, mutate=lambda d: d["compute"]["offerings"]["msi-chat"].update(
        benchmark={"state": "unbenchmarked"}))
    e = compute.evaluate(unbench, "msi-chat", **ok)
    assert (e.benchmarked, e.authorized, e.active) == (False, False, False)   # no benchmark => no valid grant


def test_data_class_ceiling_and_revision_pin(cfg):
    m = Mock(responses=[body(req(data_class="private"))])
    assert fast(mkcfg(cfg), req(data_class="private"), m).error.code == "NOT_AUTHORIZED" and m.calls == []
    stale = mkcfg(cfg, mutate=lambda d: d["compute"]["authorizations"][0].update(revision="old"))
    assert compute.authorization_for(stale, "msi-chat") is None
    assert fast(stale, req(), Mock(responses=[body(req())])).error.code == "NOT_AUTHORIZED"


def test_not_advertised_or_unhealthy_is_capability_unavailable(cfg):
    assert fast(mkcfg(cfg), req(), Mock(advertise=False, responses=[body(req())])).error.code == "CAPABILITY_UNAVAILABLE"
    assert fast(mkcfg(cfg), req(), Mock(healthy=False, responses=[body(req())])).error.code == "CAPABILITY_UNAVAILABLE"


# ---------------------------------------------------------------- happy path + provenance
def test_authorized_job_completes_with_structured_result(cfg):
    r = req()
    res = fast(mkcfg(cfg), r, Mock(responses=[body(r, "queued"), body(r, "running"), body(r)]))
    assert res.ok and res.status is J.Status.COMPLETED and res.result == {"text": "ok"}
    assert res.usage.tokens_out == 4 and res.provenance["model_revision"] == REV


# ---------------------------------------------------------------- 7 busy / timeout / exhausted
@pytest.mark.parametrize("code", ["RESOURCE_BUSY", "RESOURCE_EXHAUSTED", "BACKEND_FAILURE"])
def test_node_reported_failure_propagates_its_code(cfg, code):
    r = req()
    failed = body(r, "failed", error={"code": code, "message": "no"})
    res = fast(mkcfg(cfg), r, Mock(responses=[failed]))
    assert (res.status, res.error.code, res.ok) == (J.Status.FAILED, code, False)
    assert res.error.retryable is (code in J.RETRYABLE)


def test_deadline_exceeded_is_timeout_and_cancels(cfg):
    r = req(deadline_seconds=3)
    m = Mock(responses=[body(r, "queued"), body(r, "running")])
    res = fast(mkcfg(cfg), r, m)
    assert res.error.code == "TIMEOUT" and res.status is J.Status.FAILED and "cancel" in m.calls


def test_client_raised_timeout_propagates(cfg):
    r = req()
    res = fast(mkcfg(cfg), r, Mock(responses=[J.ComputeError("TIMEOUT", "read")]))
    assert res.error.code == "TIMEOUT" and not res.ok


def test_node_cancellation_is_cancelled_not_success(cfg):
    r = req()
    res = fast(mkcfg(cfg), r, Mock(responses=[body(r, "running"), body(r, "cancelled")]))
    assert (res.status, res.error.code, res.ok) == (J.Status.CANCELLED, "CANCELLED", False)


# ---------------------------------------------------------------- 8 idempotency
def test_same_key_same_request_replays_without_resending(cfg):
    r, led, c = req(), J.JobLedger(), mkcfg(cfg)
    m = Mock(responses=[body(r)])
    first = fast(c, r, m, led)
    n = m.calls.count("submit")
    again = fast(c, r, m, led)
    assert first.ok and again.replayed and again.result == first.result and m.calls.count("submit") == n


def test_same_key_different_request_is_duplicate_request(cfg):
    r, led, c = req(), J.JobLedger(), mkcfg(cfg)
    m = Mock(responses=[body(r)])
    fast(c, r, m, led)
    other = req(params={"prompt": "different"})
    res = fast(c, other, m, led)
    assert res.error.code == "DUPLICATE_REQUEST" and not res.ok and m.calls.count("submit") == 1


def test_refused_before_send_does_not_burn_the_key(cfg):
    led, r = J.JobLedger(), req()
    assert fast(mkcfg(cfg), r, None, led).error.code == "NODE_UNAVAILABLE"
    assert led.get("key1") is None
    assert fast(mkcfg(cfg), r, Mock(responses=[body(r)]), led).ok


# ---------------------------------------------------------------- 9 transitions and malformed responses
def test_transition_table():
    for terminal in (J.Status.COMPLETED, J.Status.FAILED, J.Status.CANCELLED):
        assert J.TRANSITIONS[terminal] == set()
    rec = J.JobRecord(req(), "fp")
    rec.advance(J.Status.RUNNING)
    rec.advance(J.Status.COMPLETED)
    with pytest.raises(J.InvalidTransition):
        rec.advance(J.Status.RUNNING)
    with pytest.raises(J.InvalidTransition):
        J.JobRecord(req(), "fp").advance(J.Status.COMPLETED)           # queued -> completed skips running


def test_fast_job_finishing_between_observations_passes_through_running(cfg):
    r, led = req(), J.JobLedger()
    assert fast(mkcfg(cfg), r, Mock(responses=[body(r)]), led).ok
    assert led.get("key1").history == [J.Status.QUEUED, J.Status.RUNNING, J.Status.COMPLETED]


def test_backwards_state_from_node_is_invalid_response(cfg):
    r = req()
    res = fast(mkcfg(cfg), r, Mock(responses=[body(r, "running"), body(r, "queued")]))
    assert res.error.code == "INVALID_RESPONSE" and not res.ok


@pytest.mark.parametrize("mutate", [
    lambda b: b.pop("result"),                                          # completed without a result
    lambda b: b.update(error={"code": "BACKEND_FAILURE"}),              # completed with an error
    lambda b: b.update(job_id="other"),
    lambda b: b.update(node="evil"),                                    # node picked a different node
    lambda b: b.update(offering="other-offering"),
    lambda b: b.update(capability="image.generate"),                    # node picked a different capability
    lambda b: b["provenance"].update(model_revision="unapproved"),      # unapproved model/revision
    lambda b: b.update(status="weird"),
    lambda b: b.update(extra="field"),                                  # unknown fields
    lambda b: b.update(usage={"wall_ms": -1}),
    lambda b: b.update(v=2),
])
def test_malformed_or_out_of_contract_responses_are_invalid(cfg, mutate):
    r = req()
    b = body(r)
    mutate(b)
    res = fast(mkcfg(cfg), r, Mock(responses=[b]))
    assert res.error.code == "INVALID_RESPONSE" and not res.ok and res.result is None


@pytest.mark.parametrize("raw", [None, "ok", [], 7])
def test_non_object_response_is_invalid(cfg, raw):
    assert fast(mkcfg(cfg), req(), Mock(responses=[raw])).error.code == "INVALID_RESPONSE"


def test_failed_without_error_or_with_result_is_invalid(cfg):
    r = req()
    assert fast(mkcfg(cfg), r, Mock(responses=[body(r, "failed")])).error.code == "INVALID_RESPONSE"
    assert fast(mkcfg(cfg), r, Mock(responses=[body(r, "failed", result={"x": 1},
                error={"code": "BACKEND_FAILURE"})])).error.code == "INVALID_RESPONSE"


def test_unexpected_client_exception_is_backend_failure_not_success(cfg):
    assert fast(mkcfg(cfg), req(), Mock(responses=[RuntimeError("x")])).error.code == "BACKEND_FAILURE"


# ---------------------------------------------------------------- request validation
@pytest.mark.parametrize("kw", [
    {"job_id": "bad id"}, {"capability": "nope"}, {"operation": "embed"}, {"deadline_seconds": 0},
    {"deadline_seconds": 99999}, {"data_class": "top"}, {"inputs": (J.ArtifactRef("https://x/y"),)},
    {"inputs": (J.ArtifactRef("secondbrain:../etc/passwd"),)}, {"params": {"x": "y" * 9000}},
    {"audit": J.AuditRef("")},
])
def test_malformed_requests_are_rejected(cfg, kw):
    with pytest.raises(J.RequestInvalid):
        J.run_job(mkcfg(cfg), req(**kw), Mock(responses=[{}]))


def test_payload_carries_no_policy_or_credentials(cfg):
    p = req().payload()
    assert "approved_node" not in p and "data_class" not in p and "auth" not in str(p).lower()


# ---------------------------------------------------------------- config validation
def _errs(cfg, mutate):
    return C.validate(mkcfg(cfg, enabled=False, offering=False, auth=False, mutate=mutate))


@pytest.mark.parametrize("ep", ["http://10.0.0.5:8000", "10.0.0.5", "user@host", "msi.example.com"])
def test_endpoint_must_be_symbolic(cfg, ep):
    errs = _errs(cfg, lambda d: d["resources"]["nodes"]["msi"]["compute"].update(endpoint_ref=ep))
    assert any("endpoint_ref" in e for e in errs)


@pytest.mark.parametrize("ref", ["sk-live-abcdef", "hunter2", "env:", "file:/etc/x"])
def test_auth_ref_cannot_be_an_inline_secret(cfg, ref):
    assert any("auth_ref" in e for e in _errs(cfg, lambda d: d["resources"]["nodes"]["msi"]["compute"]
                                              .update(auth_ref=ref)))


def test_enabling_requires_refs_and_mac_is_never_a_compute_node(cfg):
    assert any("enabled requires" in e for e in _errs(
        cfg, lambda d: d["resources"]["nodes"]["msi"]["compute"].update(enabled=True)))
    def mac(d):
        d["resources"]["nodes"]["mac"]["compute"] = {"enabled": True, "endpoint_ref": "a", "auth_ref": "env:X"}
    assert any("not a remote compute node" in e for e in _errs(cfg, mac))


def test_authorization_validation(cfg):
    def with_off(**authkw):
        def m(d):
            d["compute"]["offerings"] = {"msi-chat": copy.deepcopy(OFFER)}
            d["compute"]["authorizations"] = [{**AUTH, **authkw}]
        return m
    assert _errs(cfg, with_off()) == []
    assert any("revision" in e for e in _errs(cfg, with_off(revision="x")))
    assert any("max_data_class" in e for e in _errs(cfg, with_off(max_data_class="everything")))
    assert any("approval_ref" in e for e in _errs(cfg, with_off(approval_ref=" ")))
    assert any("declared offering" in e for e in _errs(cfg, with_off(offering="ghost")))
    def unbench(d):
        with_off()(d)
        d["compute"]["offerings"]["msi-chat"]["benchmark"] = {"state": "unbenchmarked"}
    assert any("unbenchmarked" in e for e in _errs(cfg, unbench))
    def dup(d):
        with_off()(d)
        d["compute"]["authorizations"].append(dict(AUTH))
    assert any("duplicate" in e for e in _errs(cfg, dup))


def test_offering_validation(cfg):
    def mut(**kw):
        def m(d):
            o = copy.deepcopy(OFFER)
            o.update(kw)
            d["compute"]["offerings"] = {"x-1": o}
        return m
    assert _errs(cfg, mut()) == []
    assert any("declared non-control-plane node" in e for e in _errs(cfg, mut(node="mac")))
    assert any("capability type" in e for e in _errs(cfg, mut(capability="llm.nope")))
    assert any("subset" in e for e in _errs(cfg, mut(operations=["embed"])))
    assert any("pinned id and revision" in e for e in _errs(cfg, mut(model={"id": "m"})))
    assert any("benchmarked requires evidence" in e for e in _errs(cfg, mut(benchmark={"state": "benchmarked"})))
    assert any("unknown field" in e for e in _errs(cfg, mut(secret_token="x")))


def test_job_limits_can_tighten_never_loosen(cfg):
    assert compute.limits(mkcfg(cfg, mutate=lambda d: d["compute"].update(job_limits={"max_deadline_seconds": 10}))
                          )["max_deadline_seconds"] == 10
    assert compute.limits(mkcfg(cfg, mutate=lambda d: d["compute"].update(job_limits={"max_deadline_seconds": 10**6}))
                          )["max_deadline_seconds"] == 3600
    assert any("max_deadline_seconds" in e for e in _errs(
        cfg, lambda d: d["compute"].update(job_limits={"max_deadline_seconds": 10**6})))


def test_missing_compute_section_fails_closed(cfg):
    c = mkcfg(cfg, mutate=lambda d: d.update(compute={}))
    assert compute.offerings(c) == {} and any("compute" in e for e in C.validate(c))


def test_candidate_cannot_edit_the_authorization_file(tmp_path):
    from agentos.selfimprove import Candidate, GateViolation
    c = Candidate.propose(tmp_path / "si", "cmp1", producer="codex", rationale="authorize msi", lesson_ref="x")
    with pytest.raises(GateViolation, match="protected"):
        c.isolate("agentos/cand", ["config/resources.yaml", "config/compute.yaml"])
