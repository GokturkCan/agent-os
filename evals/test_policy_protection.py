"""Critical execution-policy files are protected (path guard + manifest), and the routing
risk gate - deliberately left unprotected as the tunable surface - is held by validation."""
import copy
import shutil

import pytest

from agentos import config as C
from agentos.permissions import is_protected
from agentos.selfimprove import Candidate, GateViolation, compute_manifest, verify_manifest
import json

NEW_PROTECTED = ("config/workers.yaml", "config/mcp.yaml", "config/capability_registry.yaml",
                 "agentos/workers.py", "agentos/githooks/pre-push")
UNPROTECTED_BY_DESIGN = ("config/routing.yaml", "agentos/router.py", "agentos/dispatch.py",
                         "config/models.yaml", "config/providers.yaml", "config/skills.yaml",
                         "config/resources.yaml", "docs/roadmap.md")


@pytest.mark.parametrize("path", NEW_PROTECTED)
def test_execution_policy_files_are_protected_and_hashed(path):
    assert is_protected(path)
    assert path in compute_manifest()
    assert path in json.loads((C.REPO_ROOT / "evals" / "protected-manifest.json").read_text())["files"]
    assert verify_manifest() == []


@pytest.mark.parametrize("path", UNPROTECTED_BY_DESIGN)
def test_protection_is_not_broadened_without_justification(path):
    assert not is_protected(path)
    assert path not in compute_manifest()


@pytest.mark.parametrize("path", NEW_PROTECTED)
def test_candidates_touching_execution_policy_are_rejected(tmp_path, path):
    c = Candidate.propose(tmp_path / "si", "c1", producer="codex", rationale="loosen", lesson_ref="x")
    with pytest.raises(GateViolation, match="protected"):
        c.isolate("agentos/cand", ["config/routing.yaml", path])
    assert c.rec["stage"] == "rejected"


@pytest.mark.parametrize("path", [p for p in NEW_PROTECTED])
def test_drift_in_each_newly_protected_file_is_detected(tmp_path, path):
    from agentos.permissions import PROTECTED_POLICY_PATHS
    assert any(p == path or p.endswith("/**") and path.startswith(p[:-2]) for p in PROTECTED_POLICY_PATHS)
    root = tmp_path / "repo"
    (root / "evals").mkdir(parents=True)
    (root / path).parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(C.REPO_ROOT / path, root / path)
    (root / "evals" / "protected-manifest.json").write_text(json.dumps({"files": compute_manifest(root)}))
    assert verify_manifest(root) == []
    with open(root / path, "a") as fh:
        fh.write("\n# weakened\n")
    assert verify_manifest(root) == [path]


def test_validate_holds_the_routing_risk_gate(cfg):
    assert C.validate(cfg) == []

    def broken(mutate):
        data = copy.deepcopy(cfg.data)
        mutate(data["routing"])
        return C.validate(C.Config(root=cfg.root, data=data))
    assert any("high_requires_human_approval must be true" in e
               for e in broken(lambda r: r["risk"].update(high_requires_human_approval=False)))
    assert any("high_requires_human_approval must be true" in e
               for e in broken(lambda r: r["risk"].pop("high_requires_human_approval")))
    errs = broken(lambda r: r["risk"].update(high_risk_task_markers=["payment"]))
    assert any("missing required markers" in e and "credential_change" in e for e in errs)
    # Adding markers is fine (tunable); removing required ones is not.
    assert broken(lambda r: r["risk"]["high_risk_task_markers"].append("new_marker")) == []
