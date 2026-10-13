"""Run 2 — `agentos capabilities` CLI smoke tests (human + JSON output, exit codes)."""
import json
import subprocess

import pytest

from agentos import cli, events
from agentos.config import REPO_ROOT


def _run(capsys, *args):
    rc = cli.main(["capabilities", *args])
    return rc, capsys.readouterr().out


def test_list_human_and_json(capsys):
    rc, out = _run(capsys, "list")
    assert rc == 0 and "serena" in out and "registration != availability" in out
    rc, out = _run(capsys, "list", "--kind", "worker", "--json")
    assert rc == 0 and {p["id"] for p in json.loads(out)} == {"claude-code", "codex", "opencode"}


def test_show_with_probe(capsys):
    rc, out = _run(capsys, "show", "serena", "--probe", "--json")
    d = json.loads(out)
    assert rc == 0 and d["id"] == "serena" and d["probe_result"]["provider"] == "serena"
    assert _run(capsys, "show", "nope")[0] == 2


def test_match_selected_and_blocked_exit_codes(capsys):
    rc, out = _run(capsys, "match", "web.docs_lookup")
    assert rc == 0 and "web.docs_lookup -> context7" in out
    rc, out = _run(capsys, "match", "web.interact", "--unavailable", "playwright", "--json")
    d = json.loads(out)
    assert rc == 2 and d["status"] == "blocked" and d["exit_state"] == "blocked"
    rc, _ = _run(capsys, "match", "code.telepathy")
    assert rc == 2
    assert _run(capsys, "match", "web.interact", "--unavailable", "ghost")[0] == 2


def test_match_task_type_mapping_and_record(capsys):
    rc, out = _run(capsys, "match", "--task-type", "github", "--task-id", "cap-cli", "--record", "--json")
    d = json.loads(out)
    assert d["required"] == ["devops.github"]
    ev = [e for e in events.read_all("cap-cli") if e["event"] == "capability_decision"]
    assert len(ev) == 1 and ev[0]["capabilities"]["required"] == ["devops.github"]


def test_matrix_human_and_json(capsys):
    rc, out = _run(capsys, "matrix")
    assert rc == 0 and "claude-code" in out and "unknown is never inferred" in out
    rc, out = _run(capsys, "matrix", "--json")
    m = json.loads(out)
    assert m["columns"][:2] == ["devops.shell", "devops.git"]
    assert m["rows"]["claude-code"]["serena"]["state"] == "supported"
    assert m["rows"]["codex"]["skills.load"]["state"] == "unknown"     # not fabricated
    assert m["rows"]["codex"]["rea"] == {"state": "unknown", "source": "explicit"}


def test_check_json_covers_every_provider(capsys):
    rc, out = _run(capsys, "check", "--json")
    d = json.loads(out)
    assert rc == 0 and "claude-code" in d and all("health" in r for r in d.values())


def test_invalid_registry_exit_code(capsys, monkeypatch):
    from agentos import capability_registry as R
    monkeypatch.setattr(R, "load", lambda cfg: (_ for _ in ()).throw(R.RegistryError(["boom"])))
    rc, out = _run(capsys, "list")
    assert rc == 1 and "boom" in out


def test_wrapper_runs_capabilities_from_any_directory(tmp_path):
    r = subprocess.run([str(REPO_ROOT / "bin" / "agentos"), "capabilities", "match", "code.references"],
                       cwd=tmp_path, capture_output=True, text=True)
    assert r.returncode == 0 and "code.references -> serena" in r.stdout
