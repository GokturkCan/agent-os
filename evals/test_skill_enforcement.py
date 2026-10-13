"""agent-os-orchestrate must make direct Hermes mutation explicitly illegal and
dispatch mandatory. Contract-text guards: Hermes tool use is not interceptable
from this repo, so these catch regressions in the skill, wrapper and intent gate."""
import re
import subprocess

from agentos import hermes_bridge as hb
from agentos.config import REPO_ROOT
from agentos.intent import decide

SKILL = "agent-os-orchestrate"
ACCEPTANCE = ("Fix the bug in this repository so the existing test passes. Make the smallest "
              "correct code change, run the tests to verify it, and do not modify the test.")
TEXT = (REPO_ROOT / "skills" / SKILL / "SKILL.md").read_text()


def _section(title):
    m = re.search(rf"^## {re.escape(title)}.*?\n(.*?)(?=^## |\Z)", TEXT, re.S | re.M)
    assert m, f"missing section {title}"
    return m.group(1)


CONTRACT = _section("MUTATION CONTRACT")
MUST_NOT = CONTRACT.split("MUST NOT")[1].split("Hermes MUST run")[0]


def test_contract_requires_agentos_dispatch():
    assert "Hermes -> agent-os-orchestrate -> `agentos dispatch` -> worker -> verifier" in CONTRACT
    assert re.search(r"Hermes MUST run `agentos dispatch`", CONTRACT)
    assert "--verify" in CONTRACT and "authoritative" in CONTRACT


def test_contract_forbids_direct_patch():
    assert "use the `patch` tool" in MUST_NOT


def test_contract_forbids_direct_write_file():
    assert "use the `write_file` tool" in MUST_NOT


def test_contract_forbids_terminal_implementation_and_fallback():
    assert "implement the change via terminal commands" in MUST_NOT
    assert "never fall\nback to editing the repository yourself" in CONTRACT


def test_read_only_inspection_remains_allowed():
    may = CONTRACT.split("Hermes MAY")[1].split("Hermes MUST NOT")[0]
    for phrase in ("read-only", "git status", "git log", "read files"):
        assert phrase in may


def test_description_states_dispatch_only():
    desc = re.search(r"^description: (.*)$", TEXT, re.M).group(1)
    assert "agentos dispatch" in desc and "patch" in desc and "write_file" in desc


def test_contract_precedes_dispatch_instructions():
    assert TEXT.index("MUTATION CONTRACT") < TEXT.index("## Required path")


def test_acceptance_prompt_is_forced_to_skill(cfg):
    d = decide(cfg, ACCEPTANCE)
    assert d.force is True and d.skill == SKILL


def test_skill_is_not_a_direct_worker_skill():
    assert SKILL not in hb.DIRECT_WORKER_SKILLS
