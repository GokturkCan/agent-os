"""R3.2B: the SystemOne benchmark harness, and the integrity of the committed Laya evidence."""
import json
import sys

import pytest

from agentos import cli
from agentos import config as C
from agentos import systemone_adapter as A
from agentos import systemone_bench as B
from agentos.config import REPO_ROOT
from evals.test_systemone_adapter import STUB

REQUIRED = {"schema", "backend", "command", "params", "environment", "accuracy", "accuracy_note", "cold_start",
            "runtime", "warm_latency_ms", "throughput_decisions_per_s", "rates", "confidence", "choice_distribution",
            "decision_sequence_sha256", "latency_samples_ms", "repeat_consistency", "memory", "footprint"}


@pytest.fixture
def stub_backend(tmp_path):
    path = tmp_path / "stub.py"
    path.write_text(STUB)

    def make(mode="ok"):
        rt = A.SubprocessJsonRuntime([sys.executable, str(path), mode], name=f"stub-{mode}", cooldown=0, startup_timeout=5)
        return A.AdapterBackend(f"stub-{mode}", rt, timeout=1.0)
    yield make
    A.close_all()


def test_percentile_is_linear_interpolated():
    v = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert B.percentile(v, 0) == 1.0 and B.percentile(v, 50) == 3.0 and B.percentile(v, 100) == 5.0
    assert B.percentile(v, 25) == 2.0 and B.percentile(v, 90) == pytest.approx(4.6)
    assert B.percentile([7.0], 95) == 7.0
    assert B._stats([])["n"] == 0


def test_workload_is_deterministic_compact_and_only_offers_known_workers():
    a, b = B.workload(50, 1337), B.workload(50, 1337)
    assert [repr(x) for x in a] == [repr(x) for x in b]
    assert [repr(x) for x in B.workload(50, 1)] != [repr(x) for x in a]
    for r in a:
        assert 1 <= len(r.eligible_options) <= 3 and set(r.eligible_options) <= {"claude_code", "codex", "deepseek_harness"}
        assert len(json.dumps(A.build_payload(r, r.questions[0])).encode()) < A.MAX_PAYLOAD_BYTES // 2


def test_benchmark_reports_every_required_metric_and_claims_no_accuracy(cfg, stub_backend):
    res = B.run_benchmark(cfg, "stub", n=30, warmup=3, seed=5, repeat=4, backend=stub_backend("ok"))
    assert REQUIRED <= set(res)
    assert res["accuracy"] is None and "no labeled dataset" in res["accuracy_note"]
    assert {"p50", "p95", "p99", "min", "max", "mean", "n"} <= set(res["warm_latency_ms"]) and res["warm_latency_ms"]["n"] == 30
    assert res["rates"]["valid_choice_rate"] == 1.0 and res["rates"]["malformed_response_rate"] == 0.0
    assert res["throughput_decisions_per_s"] > 0 and len(res["latency_samples_ms"]) == 30
    assert res["confidence"]["kinds"] == ["raw"] and res["repeat_consistency"] == {"repeats": 4, "distinct_answers": 1}
    assert res["cold_start"]["first_decision_incl_spawn_ms"] > 0 and res["memory"]["worker_rss_mib_min"] > 0


def test_benchmark_result_is_reproducible_for_a_deterministic_backend(cfg, stub_backend):
    a = B.run_benchmark(cfg, "stub", n=25, warmup=2, seed=11, repeat=2, backend=stub_backend("ok"))
    b = B.run_benchmark(cfg, "stub", n=25, warmup=2, seed=11, repeat=2, backend=stub_backend("ok"))
    c = B.run_benchmark(cfg, "stub", n=25, warmup=2, seed=12, repeat=2, backend=stub_backend("ok"))
    assert a["decision_sequence_sha256"] == b["decision_sequence_sha256"] != c["decision_sequence_sha256"]


@pytest.mark.parametrize("mode,rate_key", [("garbage", "malformed_response_rate"), ("ineligible", "escalation_rate"),
                                           ("crash", "escalation_rate")])
def test_benchmark_survives_and_counts_a_failing_backend(cfg, stub_backend, mode, rate_key):
    res = B.run_benchmark(cfg, "stub", n=10, warmup=2, seed=3, repeat=2, backend=stub_backend(mode))
    assert res["rates"]["valid_choice_rate"] == 0.0 and res["rates"][rate_key] == 1.0
    assert res["rates"]["escalation_rate"] == 1.0 and res["rates"]["escalation_reasons"]


def test_benchmark_output_contains_no_environment_secrets(cfg, stub_backend, monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "hf_SECRETVALUE123456789")
    monkeypatch.setenv("MY_API_KEY", "sk-live-SECRETVALUE")
    blob = json.dumps(B.run_benchmark(cfg, "stub", n=5, warmup=1, seed=1, repeat=1, backend=stub_backend("ok")))
    assert "SECRETVALUE" not in blob


def test_cli_rejects_an_unconfigured_backend(capsys):
    assert cli.main(["systemone", "smoke", "--backend", "no-such-backend"]) == 2
    assert "unknown configured backend" in capsys.readouterr().out


# ------------------------------------------------------------ committed evidence supports the status
def test_committed_laya_evidence_supports_the_measured_status():
    cfg = C.load()
    model = cfg.models["models"]["laya-mlx"]
    paths = [REPO_ROOT / e for e in model["evidence"]]
    assert model["status"] == "measured" and all(p.exists() for p in paths)
    runs = [json.loads(p.read_text()) for p in paths if p.suffix == ".json"]
    assert len(runs) == 2
    r1, r2 = runs
    for r in runs:
        assert r["backend"] == "laya-mlx" and r["schema"] == 1 and r["params"]["n"] == 200
        assert r["rates"]["valid_choice_rate"] == 1.0 and r["rates"]["malformed_response_rate"] == 0.0
        assert r["accuracy"] is None and r["confidence"]["kinds"] == ["raw"]
        assert r["runtime"]["laya_mlx"] == "0.4.0" and r["repeat_consistency"]["distinct_answers"] == 1
    assert r1["decision_sequence_sha256"] == r2["decision_sequence_sha256"]        # reproducible across processes
    assert abs(r1["warm_latency_ms"]["p50"] - r2["warm_latency_ms"]["p50"]) / r1["warm_latency_ms"]["p50"] < 0.10
    md = (REPO_ROOT / "audit" / "laya-mlx-r3.2-2026-10-14.md").read_text()
    assert "not** a production" in md and "Decision *quality* has **not** been measured" in md


def test_laya_is_still_not_wired_as_a_default_or_a_tier_model():
    cfg = C.load()
    assert cfg.routing["systemone"]["backend"] == "null" and cfg.models["tiers"]["fastgate"]["model"] is None
