"""Load and validate the canonical config/*.yaml files.

Validation is deterministic and structural: status vocabulary, cross-file
references, and invariants the architecture freezes (e.g. MSI is never
boot-critical, no worker profile holds a never-grantable capability).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_FILES = ("models", "providers", "routing", "workers", "capabilities",
                "resources", "mcp", "skills", "knowledge", "permissions", "systemone")
# Security-relevant routing policy that is not file-protected (routing.yaml is the tunable
# surface for self-improvement candidates) and is therefore enforced by validate() instead.
REQUIRED_RISK_MARKERS = {"credential_change", "permission_change", "external_publish",
                         "destructive_delete", "payment", "production_deploy", "policy_change"}
STATUSES = {"available", "configured", "measured", "candidate", "disabled",
            "deferred", "rejected"}
EXIT_STATES = {"success", "blocked", "no_progress", "unsafe", "timeout",
               "budget_exhausted", "human_handoff"}
# Statuses meaning "exists and may be used" (vs. named-only).
USABLE = {"available", "configured", "measured"}


def expand(path: str | os.PathLike) -> Path:
    return Path(os.path.expanduser(str(path)))


@dataclass
class Config:
    root: Path
    data: dict = field(default_factory=dict)

    def __getattr__(self, name):  # cfg.models, cfg.routing, ...
        try:
            return self.__dict__["data"][name]
        except KeyError as exc:
            raise AttributeError(name) from exc


def load(root: str | os.PathLike | None = None) -> Config:
    root = Path(root) if root else REPO_ROOT
    data = {}
    for name in CONFIG_FILES:
        with open(root / "config" / f"{name}.yaml", encoding="utf-8") as fh:
            data[name] = yaml.safe_load(fh) or {}
    return Config(root=root, data=data)


def activation_allowlists(cfg: "Config") -> tuple[list, list]:
    """(production_backends, fastgate_models) from the PROTECTED config/systemone.yaml `activation`.
    Malformed or missing -> empty lists (fail closed). Shared by validate() and the router's runtime guard."""
    act = (cfg.data.get("systemone") or {}).get("activation")
    act = act if isinstance(act, dict) else {}
    lists = []
    for key in ("production_backends", "fastgate_models"):
        v = act.get(key)
        lists.append([x for x in v if isinstance(x, str)] if isinstance(v, list) else [])
    return lists[0], lists[1]


def validate(cfg: Config) -> list[str]:
    """Return a list of human-readable errors (empty == valid)."""
    errors: list[str] = []

    def check_status(section: str, name: str, entry: dict):
        status = entry.get("status")
        if status not in STATUSES:
            errors.append(f"{section}.{name}: invalid status {status!r}")
        if status == "disabled" and not entry.get("reason"):
            errors.append(f"{section}.{name}: disabled entries need a reason")

    for name, m in cfg.models.get("models", {}).items():
        check_status("models", name, m)
        if m.get("status") == "measured" and not m.get("evidence"):
            errors.append(f"models.{name}: measured requires evidence")
        ev = m.get("evidence")
        for e in ([ev] if isinstance(ev, str) else ev or []):
            if not (cfg.root / e).exists():
                errors.append(f"models.{name}: evidence file missing: {e}")

    providers = cfg.providers.get("providers", {})
    for name, p in providers.items():
        check_status("providers", name, p)
        if p.get("enabled") and p.get("status") not in USABLE:
            errors.append(f"providers.{name}: enabled but status={p.get('status')}")

    workers = cfg.workers.get("workers", {})
    profiles = cfg.capabilities.get("profiles", {})
    never = set(cfg.capabilities.get("never_grantable", []))
    known_caps = set(cfg.capabilities.get("capabilities", {}))
    for name, w in workers.items():
        check_status("workers", name, w)
        for prof in w.get("allowed_profiles", []):
            if prof not in profiles:
                errors.append(f"workers.{name}: unknown profile {prof}")
        if w.get("default_profile") and w["default_profile"] not in w.get("allowed_profiles", []):
            errors.append(f"workers.{name}: default_profile not in allowed_profiles")
        if w.get("provider") and w["provider"] not in providers:
            errors.append(f"workers.{name}: unknown provider {w['provider']}")
    for pname, prof in profiles.items():
        for g in prof.get("grants", []):
            if g in never:
                errors.append(f"capabilities.{pname}: grants never-grantable {g}")
            elif g not in known_caps:
                errors.append(f"capabilities.{pname}: unknown capability {g}")
        if prof.get("fs_role") not in cfg.permissions.get("roles", {}):
            errors.append(f"capabilities.{pname}: unknown fs_role {prof.get('fs_role')}")

    routing = cfg.routing
    stages_known = set(cfg.models.get("tiers", {}))
    for cname, tc in routing.get("task_classes", {}).items():
        for st in tc.get("stages", []):
            if st not in stages_known:
                errors.append(f"routing.{cname}: unknown stage {st}")
        for prov in tc.get("cloud_chain", []):
            if prov not in providers:
                errors.append(f"routing.{cname}: unknown provider {prov}")
        for wk in tc.get("workers", []):
            if wk not in workers:
                errors.append(f"routing.{cname}: unknown worker {wk}")
    if set(routing.get("exit_states", [])) != EXIT_STATES:
        errors.append("routing.exit_states must equal the canonical exit-state set")
    from . import systemone   # deferred: keeps config import light
    from . import systemone_adapter
    defined = systemone_adapter.definitions(cfg)
    for bname, conf in defined.items():
        errors.extend(systemone_adapter.validate_definition(bname, conf))
        if bname in systemone.BACKENDS:
            errors.append(f"systemone.backends.{bname}: name collides with a built-in backend")
    backend = (routing.get("systemone") or {}).get("backend", "null")
    if backend not in systemone.BACKENDS and backend not in defined:
        errors.append(f"routing.systemone.backend {backend!r} is not a registered or configured backend "
                      f"({sorted(systemone.BACKENDS)} + {sorted(defined)})")
    # Activation boundary. routing.yaml / models.yaml are the tunable (unprotected) surface, so a
    # self-improvement candidate could otherwise activate a model-backed backend or fastgate model with a
    # one-line edit. Activating either needs a name in config/systemone.yaml `activation` (a PROTECTED file).
    allowed_backends, allowed_models = activation_allowlists(cfg)
    if backend not in systemone.BACKENDS and backend in defined and backend not in allowed_backends:
        errors.append(f"routing.systemone.backend {backend!r} is a benchmark-only adapter backend; activating it "
                      f"requires listing it in config/systemone.yaml activation.production_backends (protected)")
    fg_model = (cfg.models.get("tiers", {}).get("fastgate") or {}).get("model")
    if fg_model and fg_model not in allowed_models:
        errors.append(f"models.tiers.fastgate.model {fg_model!r} is set but not listed in "
                      f"config/systemone.yaml activation.fastgate_models (protected)")
    if fg_model and (cfg.models.get("models", {}).get(fg_model) or {}).get("status") not in USABLE:
        errors.append(f"models.tiers.fastgate.model {fg_model!r} does not have a usable status")
    risk = routing.get("risk") or {}
    if risk.get("high_requires_human_approval") is not True:
        errors.append("routing.risk.high_requires_human_approval must be true")
    lost = REQUIRED_RISK_MARKERS - set(risk.get("high_risk_task_markers") or [])
    if lost:
        errors.append(f"routing.risk.high_risk_task_markers missing required markers: {sorted(lost)}")
    tools = cfg.mcp.get("tools", {})
    for need, rule in routing.get("tool_routing", {}).items():
        for t in [rule["prefer"], *rule.get("fallback", [])]:
            if t not in tools:
                errors.append(f"routing.tool_routing.{need}: unknown tool {t}")
    for name, t in tools.items():
        check_status("mcp", name, t)
    for prof, names in cfg.mcp.get("exposure", {}).items():
        for n in names:
            if n not in tools:
                errors.append(f"mcp.exposure.{prof}: unknown tool {n}")

    nodes = cfg.resources.get("nodes", {})
    if nodes.get("msi", {}).get("boot_critical") is not False:
        errors.append("resources: MSI must never be boot_critical")
    if nodes.get("mac", {}).get("boot_critical") is not True:
        errors.append("resources: Mac must be the boot-critical control plane")

    for name, s in cfg.skills.get("sources", {}).items():
        check_status("skills", name, s)

    from . import capability_registry   # imports this module; deferred to avoid a cycle
    errors.extend(capability_registry.validate(cfg))
    return errors
