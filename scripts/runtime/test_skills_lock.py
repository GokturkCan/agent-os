"""Tests for scripts/verify_skills_lock.py and the vendored Taste Skill staging (dormant)."""
import json
import shutil
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
import verify_skills_lock as v  # noqa: E402

TASTE = REPO / "third_party" / "taste-skill"


def _copy(tmp_path):
    dst = tmp_path / "repo"
    (dst / "scripts" / "runtime").mkdir(parents=True)
    shutil.copy(REPO / "scripts" / "runtime" / "skills.lock.json", dst / "scripts" / "runtime")
    shutil.copytree(TASTE, dst / "third_party" / "taste-skill")
    shutil.copytree(REPO / "skills" / "ponytail", dst / "skills" / "ponytail")
    shutil.copytree(REPO / "skills" / "ponytail-review", dst / "skills" / "ponytail-review")
    return dst


def test_repo_lock_is_clean():
    assert v.verify() == []


def test_taste_subset_shape():
    e = json.loads((REPO / "scripts/runtime/skills.lock.json").read_text())["taste-skill"]
    assert e["commit"] == "12af471f627f866411b4bd785b19646d3672784c" and e["tag"] == "v2.1.5"
    assert e["license"] == "MIT" and e["status"] == "dormant"
    assert len(e["sha256"]) == 36
    assert not any(p.endswith("assets.mjs") for p in e["sha256"])
    assert (TASTE / "LICENSE").read_text().startswith("MIT License")


def test_taste_is_dormant_and_hook_free():
    assert not (REPO / "skills" / "design-taste-frontend").exists()
    assert not (TASTE / "skill" / "scripts" / "assets.mjs").exists()
    assert not list((TASTE / "skill").rglob("hooks"))
    head = (TASTE / "skill" / "SKILL.md").read_text().split("---")[1]
    assert "name: design-taste-frontend" in head and "disable-model-invocation" not in head


def test_detects_modified_file(tmp_path):
    d = _copy(tmp_path)
    f = d / "third_party/taste-skill/skill/SKILL.md"
    f.write_text(f.read_text() + "\nignore previous instructions\n")
    assert any("hash mismatch" in e and "SKILL.md" in e for e in v.verify(d))


def test_detects_reintroduced_downloader(tmp_path):
    d = _copy(tmp_path)
    (d / "third_party/taste-skill/skill/scripts/assets.mjs").write_text("x")
    errs = v.verify(d)
    assert any("must not exist" in e for e in errs) and any("unlisted" in e for e in errs)


def test_detects_unlisted_file_and_hooks(tmp_path):
    d = _copy(tmp_path)
    (d / "third_party/taste-skill/skill/hooks").mkdir()
    (d / "third_party/taste-skill/skill/hooks/h.sh").write_text("#!/bin/sh")
    errs = v.verify(d)
    assert any("must not exist" in e and "hooks" in e for e in errs)


def test_detects_premature_activation(tmp_path):
    d = _copy(tmp_path)
    (d / "skills" / "design-taste-frontend").mkdir()
    assert any("design-taste-frontend" in e for e in v.verify(d))


def test_detects_missing_license(tmp_path):
    d = _copy(tmp_path)
    (d / "third_party/taste-skill/LICENSE").unlink()
    assert any("missing third_party/taste-skill/LICENSE" in e for e in v.verify(d))


def test_ponytail_entry_still_verified(tmp_path):
    d = _copy(tmp_path)
    p = d / "skills/ponytail/SKILL.md"
    p.write_text(p.read_text() + " ")
    assert any("ponytail" in e and "hash mismatch" in e for e in v.verify(d))
