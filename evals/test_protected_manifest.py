"""Protected manifest: eval files are really hashed, independent of pathlib glob quirks.

Regression for the pre-release finding that `Path.glob("evals/**")` yields only directories on
Python 3.11 (so zero eval files were hashed) and files too on 3.13+ (false drift)."""
import json
from pathlib import Path

import pytest

from agentos import selfimprove
from agentos.config import REPO_ROOT
from agentos.permissions import PROTECTED_POLICY_PATHS, is_protected
from agentos.selfimprove import compute_manifest, verify_manifest


def _tree(root: Path) -> Path:
    for rel, text in {
        "config/permissions.yaml": "p", "config/capabilities.yaml": "c", "config/promotion.yaml": "r",
        "CLAUDE.md": "claude", "agentos/permissions.py": "perm", "agentos/selfimprove.py": "self",
        "evals/test_one.py": "one", "evals/conftest.py": "conf", "evals/sub/deep/test_two.py": "two",
        "evals/intent-corpus.yaml": "corpus",
        "evals/__pycache__/test_one.cpython-311.pyc": "pyc", "evals/sub/stray.pyc": "pyc",
        "evals/.DS_Store": "junk", "evals/.pytest_cache/x": "junk",
    }.items():
        f = root / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text)
    (root / "evals" / "protected-manifest.json").write_text("{}")
    (root / "evals" / "dir_named_like_a_file.py").mkdir()
    return root


def _write_manifest(root: Path):
    (root / "evals" / "protected-manifest.json").write_text(
        json.dumps({"files": compute_manifest(root)}))


def test_protected_eval_files_are_included(tmp_path):
    m = compute_manifest(_tree(tmp_path))
    assert {"evals/test_one.py", "evals/conftest.py", "evals/sub/deep/test_two.py",
            "evals/intent-corpus.yaml"} <= set(m)               # recursive, any suffix
    assert {"config/permissions.yaml", "CLAUDE.md", "agentos/selfimprove.py"} <= set(m)


def test_real_repo_hashes_every_eval_file():
    on_disk = {p.relative_to(REPO_ROOT).as_posix() for p in (REPO_ROOT / "evals").rglob("*")
               if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"
               and p.name not in (".DS_Store", "protected-manifest.json")}
    in_manifest = {k for k in compute_manifest() if k.startswith("evals/")}
    assert len(on_disk) >= 25 and in_manifest == on_disk
    assert {"evals/test_a7_permissions.py", "evals/conftest.py", "evals/test_protected_manifest.py"} <= in_manifest


def test_directories_caches_and_the_manifest_itself_are_not_hashed(tmp_path):
    m = compute_manifest(_tree(tmp_path))
    assert "evals/dir_named_like_a_file.py" not in m               # a directory is not a file
    assert not [k for k in m if "__pycache__" in k or k.endswith(".pyc") or ".pytest_cache" in k]
    assert "evals/.DS_Store" not in m and "evals/protected-manifest.json" not in m
    assert all(len(h) == 64 and set(h) <= set("0123456789abcdef") for h in m.values())


def test_result_does_not_depend_on_glob_semantics(tmp_path, monkeypatch):
    root = _tree(tmp_path)
    baseline = compute_manifest(root)
    real_glob, real_rglob = Path.glob, Path.rglob

    def forbid(real):
        def wrapped(self, pattern, *a, **kw):
            assert "**" not in pattern, "manifest must not use '**' globbing"
            return real(self, pattern, *a, **kw)
        return wrapped
    monkeypatch.setattr(Path, "glob", forbid(real_glob))
    monkeypatch.setattr(Path, "rglob", lambda self, pattern, *a, **kw: (_ for _ in ()).throw(
        AssertionError("manifest must not use rglob")))
    assert compute_manifest(root) == baseline

    # Simulate both interpreter behaviours of "**": directories only (3.11) / files too (3.13+).
    for variant in ("dirs_only", "files_and_dirs"):
        def fake(self, pattern, variant=variant):
            if "**" not in pattern:
                return real_glob(self, pattern)
            base = self / pattern.split("**")[0]
            return [p for p in real_rglob(base, "*") if variant == "files_and_dirs" or p.is_dir()]
        monkeypatch.setattr(Path, "glob", fake)
        assert compute_manifest(root) == baseline, variant


def test_unsupported_double_star_pattern_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(selfimprove, "PROTECTED_POLICY_PATHS", ("evals/**/x.py",))
    with pytest.raises(ValueError, match="trailing"):
        compute_manifest(_tree(tmp_path))


def test_drift_is_detected_for_changed_added_and_removed_eval_files(tmp_path):
    root = _tree(tmp_path)
    _write_manifest(root)
    assert verify_manifest(root) == []
    (root / "evals" / "sub" / "deep" / "test_two.py").write_text("weakened judge")
    assert verify_manifest(root) == ["evals/sub/deep/test_two.py"]
    _write_manifest(root)
    (root / "evals" / "test_new.py").write_text("new judge")
    assert verify_manifest(root) == ["evals/test_new.py"]
    _write_manifest(root)
    (root / "evals" / "conftest.py").unlink()
    assert verify_manifest(root) == ["evals/conftest.py"]
    _write_manifest(root)
    (root / "config" / "permissions.yaml").write_text("loosened")
    assert verify_manifest(root) == ["config/permissions.yaml"]


def test_caches_never_cause_drift(tmp_path):
    root = _tree(tmp_path)
    _write_manifest(root)
    (root / "evals" / "__pycache__" / "new.cpython-314.pyc").write_text("x")
    (root / "evals" / ".DS_Store").write_text("changed")
    assert verify_manifest(root) == []


def test_path_level_protection_semantics_unchanged():
    assert "evals/**" in PROTECTED_POLICY_PATHS
    for p in ("evals/test_a1_knowledge.py", "evals/sub/deep/x.py", "./evals/conftest.py",
              "config/permissions.yaml", "CLAUDE.md", "agentos/permissions.py"):
        assert is_protected(p), p
    assert not is_protected("agentos/router.py") and not is_protected("docs/roadmap.md")
