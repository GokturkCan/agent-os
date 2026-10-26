"""Run 2 / R2.1, R2.2, R2.6 — CapabilityRegistry schema, validation and Wave A inventory."""
import copy

import pytest
import yaml

from agentos import capability_registry as R
from agentos import config as C


@pytest.fixture(scope="module")
def raw():
    return R.load_raw()


@pytest.fixture(scope="module")
def reg(cfg):
    return R.load(cfg)


def _errors(raw, mutate, cfg=None):
    data = copy.deepcopy(raw)
    mutate(data)
    return R.parse(data, cfg)[1]


def _provider(data, pid):
    return next(p for p in data["providers"] if p["id"] == pid)


# ------------------------------------------------------------ canonical file
def test_canonical_registry_is_valid(cfg):
    assert R.validate(cfg) == []
    assert C.validate(cfg) == []                     # wired into `agentos validate` / health


WAVE_A = {"claude-code", "codex", "opencode", "serena", "repomix", "context7", "github-mcp",
          "playwright", "rea", "omni-macos", "superpowers", "spec-kit", "karpathy-skills", "ponytail",
          "anti-slop", "last30days", "scientific-agent-skills", "kepano-obsidian-skills", "archify",
          "design-md", "21st-dev", "refero-styles"}


def test_wave_a_inventory_registered_and_adopted(reg):
    assert WAVE_A <= set(reg.providers)
    # 2026-10-24 rollout: records that are not installed/sourced were corrected (registration != adoption).
    CATALOG_ONLY = {"spec-kit", "karpathy-skills"}
    FUTURE = {"anti-slop", "last30days", "scientific-agent-skills", "archify", "design-md", "21st-dev",
              "refero-styles", "omni-macos"}
    assert all(reg.get(p).adoption == "adopted" for p in WAVE_A - {"opencode"} - CATALOG_ONLY - FUTURE)
    assert all(reg.get(p).adoption == "catalog" for p in CATALOG_ONLY)
    assert all(reg.get(p).adoption == "future" for p in FUTURE)
    # OpenCode stays registered but disabled: its launch cannot enforce a capability profile.
    assert reg.get("opencode").adoption == "disabled" and "fail closed" in reg.get("opencode").reason
    # Beyond Wave A: Run 1's github CLI, one future browser fallback, and the 2026-10-24 rollout records.
    assert set(reg.providers) - WAVE_A == {"gh-cli", "browser-use", "markitdown", "orchestra-research",
                                           "openspec", "superclaude", "omniroute", "clawdbot",
                                           "taste-skill", "frontend-design", "ui-ux-pro-max"}   # Wave C1 (inert)
    assert reg.get("openspec").adoption == "benchmark"
    assert all(reg.get(p).adoption == "disabled" and reg.get(p).reason for p in ("superclaude", "omniroute", "clawdbot"))
    assert reg.get("browser-use").adoption == "future"
    assert {p.id for p in reg.executors()} == {"claude-code", "codex", "opencode"}


@pytest.mark.parametrize("pid,caps", [
    ("serena", {"code.semantic_navigation", "code.symbol_lookup", "code.references", "code.refactor",
                "code.diagnostics"}),
    ("repomix", {"code.snapshot"}),
    ("context7", {"web.docs_lookup"}),
    ("github-mcp", {"devops.github"}),
    ("playwright", {"web.interact", "web.browser_test"}),
    ("rea", {"reverse_engineering.binary_analysis", "reverse_engineering.decompile",
             "reverse_engineering.static_analysis", "reverse_engineering.electron_analysis",
             "reverse_engineering.dotnet_analysis", "reverse_engineering.runtime_analysis",
             "reverse_engineering.evidence_trace"}),
    ("omni-macos", {"files.semantic_search", "knowledge.multimodal_search"}),
    ("21st-dev", {"ui.component_registry"}),
    ("design-md", {"ui.design_system"}),
    ("anti-slop", {"ui.quality_filter"}),
])
def test_known_roles(reg, pid, caps):
    assert caps <= set(reg.get(pid).capabilities)


def test_skills_are_metadata_not_executables(reg):
    for pid in ("superpowers", "spec-kit", "karpathy-skills", "ponytail", "anti-slop"):
        p = reg.get(pid)
        assert p.kind == "skill" and not p.is_executor and p.worker_name is None


def test_capability_lookup(reg):
    assert [p.id for p in reg.providers_for("web.docs_lookup")] == ["context7"]
    assert {p.id for p in reg.providers_for("devops.github")} == {"github-mcp", "gh-cli"}
    assert reg.providers_for("web.crawl") == []          # catalogued, no provider yet
    assert reg.is_known_capability("code.references") and not reg.is_known_capability("code.telepathy")
    with pytest.raises(KeyError):
        reg.get("nope")


def test_metadata_classes_present(reg):
    s = reg.get("serena")
    assert (s.locality, s.cost, s.latency, s.hosts, s.auth) == ("local", "free", "local_fast", ("mac",), "none")
    cc = reg.get("claude-code")
    assert (cc.locality, cc.cost, cc.auth, cc.worker_name) == ("cloud", "existing_subscription", "required",
                                                              "claude_code")
    assert reg.get("context7").auth == "optional"
    assert reg.get("opencode").cost == "unknown"          # unknown stays unknown


def test_unknown_integrations_are_not_fabricated(reg):
    codex = reg.get("codex")
    assert codex.integration("serena") == "unsupported"
    assert codex.integration("rea") == "unknown"
    assert codex.integration("superpowers") is None       # not declared -> resolved as unknown later


# ------------------------------------------------------------ validation
def test_duplicate_provider_id_rejected(raw):
    errs = _errors(raw, lambda d: d["providers"].append(copy.deepcopy(_provider(d, "serena"))))
    assert "providers.serena: duplicate id" in errs


def test_duplicate_yaml_key_rejected(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "capability_registry.yaml").write_text(
        "version: 1\ncapabilities:\n  code.edit: a\n  code.edit: b\nproviders: []\n")
    with pytest.raises(R.RegistryError, match="duplicate key"):
        R.load(root=tmp_path)


def test_programmatic_duplicate_registration_rejected(reg):
    fresh = R.Registry(capabilities=dict(reg.capabilities))
    fresh.register(reg.get("serena"))
    with pytest.raises(R.RegistryError, match="duplicate id"):
        fresh.register(reg.get("serena"))


@pytest.mark.parametrize("bad", ["Code.Edit", "code", "code..edit", "code.edit-x", "1code.edit", "code.edit."])
def test_malformed_capability_ids_rejected(raw, bad):
    errs = _errors(raw, lambda d: d["capabilities"].update({bad: "x"}))
    assert any("malformed capability id" in e for e in errs)
    errs = _errors(raw, lambda d: _provider(d, "serena")["capabilities"].append(bad))
    assert any("malformed capability id" in e for e in errs)


def test_undeclared_capability_rejected(raw):
    errs = _errors(raw, lambda d: _provider(d, "serena")["capabilities"].append("code.telepathy"))
    assert any("unknown capability 'code.telepathy'" in e for e in errs)


@pytest.mark.parametrize("field,value", [("kind", "robot"), ("adoption", "installed"), ("locality", "moon"),
                                         ("cost", "cheap"), ("latency", "fast"), ("risk", "extreme"),
                                         ("auth", "maybe")])
def test_unknown_enum_values_rejected(raw, field, value):
    errs = _errors(raw, lambda d: _provider(d, "serena").update({field: value}))
    assert any(f"invalid {field} {value!r}" in e for e in errs)


def test_unknown_fields_and_hosts_rejected(raw):
    errs = _errors(raw, lambda d: _provider(d, "serena").update({"installed": True}))
    assert any("unknown fields ['installed']" in e for e in errs)       # install state is never declared
    errs = _errors(raw, lambda d: _provider(d, "serena").update({"hosts": ["pluto"]}))
    assert any("invalid host 'pluto'" in e for e in errs)


@pytest.mark.parametrize("mutate,needle", [
    (lambda d: _provider(d, "serena").update({"adoption": "disabled"}), "disabled entries need a reason"),
    (lambda d: _provider(d, "serena").update({"hosts": ["cloud"]}), "locality=local contradicts host=cloud"),
    (lambda d: _provider(d, "serena").update({"hosts": ["any", "mac"]}), "host 'any' must be the only host"),
    (lambda d: _provider(d, "serena").update({"integrations": {"context7": "supported"}}),
     "only executors declare integrations"),
    (lambda d: _provider(d, "codex").update({"requires": ["devops.shell"]}), "executors cannot `require`"),
    (lambda d: _provider(d, "serena").update({"probe": [{"type": "env_auth", "env": ["X"]}]}),
     "env_auth probe contradicts auth=none"),
    (lambda d: _provider(d, "codex")["integrations"].update({"serena": "probably"}), "invalid state"),
    (lambda d: _provider(d, "codex")["integrations"].update({"ghost": "supported"}), "unknown provider 'ghost'"),
    (lambda d: _provider(d, "codex")["integrations"].update({"claude-code": "supported"}), "is an executor"),
    (lambda d: _provider(d, "serena").update({"probe": [{"type": "ping"}]}), "invalid probe type"),
    (lambda d: d["policy"]["capability_preferences"].update({"web.interact": ["serena"]}),
     "serena does not declare web.interact"),
    (lambda d: d["policy"]["capability_reasons"].update({"web.interact": "vibes"}), "unknown reason code"),
    (lambda d: d["policy"]["task_types"].update({"x": ["code.telepathy"]}), "unknown capability"),
    (lambda d: d["policy"].update({"runtime_adoption": ["installed"]}), "invalid adoption"),
    (lambda d: d.update({"version": 2}), "unsupported version"),
])
def test_contradictory_records_rejected(raw, mutate, needle):
    errs = _errors(raw, mutate)
    assert any(needle in e for e in errs), errs


def test_config_refs_cross_checked(raw, cfg):
    errs = _errors(raw, lambda d: _provider(d, "serena").update({"config_ref": "mcp.nonexistent"}), cfg)
    assert any("not found in config/mcp.yaml" in e for e in errs)
    errs = _errors(raw, lambda d: _provider(d, "codex").pop("config_ref"), cfg)
    assert any("executors need config_ref" in e for e in errs)


def test_invalid_registry_fails_validate_without_crashing(tmp_path, cfg):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "capability_registry.yaml").write_text("version: 1\nproviders: [{id: x}]\n")
    errs = R.validate(C.Config(root=tmp_path, data=cfg.data))
    assert errs and all(isinstance(e, str) for e in errs)
    assert R.validate(C.Config(root=tmp_path / "missing", data=cfg.data)) == [
        "registry: config/capability_registry.yaml missing"]


def test_registry_file_contains_no_runtime_state():
    text = R.registry_path().read_text()
    data = yaml.safe_load(text)
    for p in data["providers"]:
        assert not {"installed", "available", "healthy", "health", "eligible"} & set(p)
