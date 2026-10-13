"""CapabilityRegistry — typed truth about what workers/tools/skills CAN do.

Declarative data lives in config/capability_registry.yaml (agent-stack stays the
config authority; no database or service). This module only parses and
validates it. Runtime state (installed/available/healthy/authenticated) comes
from agentos/capability_probes.py, and eligibility/selection from
agentos/capability_policy.py — the four concepts are never collapsed:

  registered (in this file) != installed != available != healthy != eligible

The registry answers "CAN"; config/capabilities.yaml (protected) still answers
"MAY" — launch-time permission enforcement is unchanged by anything here.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .config import REPO_ROOT

REGISTRY_FILE = Path("config") / "capability_registry.yaml"

# Hierarchical, stable ids: at least two lowercase dot-separated segments.
CAPABILITY_ID = re.compile(r"[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+")
PROVIDER_ID = re.compile(r"[a-z0-9][a-z0-9-]{1,63}")

KINDS = ("worker", "mcp", "cli", "skill", "service")
# Lifecycle/adoption: a decision, not an install state.
ADOPTION = ("adopted", "benchmark", "future", "catalog", "disabled")
# Ordered vocabularies: earlier == preferred when ranking. `unknown` is always
# last and never fabricated into a better class.
LOCALITY = ("local", "self_hosted", "hybrid", "cloud", "unknown")
COST = ("free", "existing_subscription", "metered", "expensive", "unknown")
LATENCY = ("local_fast", "local_slow", "network", "high_latency", "unknown")
RISK = ("low", "medium", "high", "unknown")
HOSTS = ("mac", "msi", "cloud", "any")
AUTH = ("none", "optional", "required")
INTEGRATION = ("supported", "unsupported", "unknown")
PROBE_TYPES = ("executable", "claude_plugin", "path", "env_auth", "config_health", "service", "declared")

# Stable reason codes for explanations/telemetry (agentos/capability_policy.py).
REJECTION_REASONS = ("capability-missing", "unknown-capability", "provider-unavailable",
                     "availability-unknown", "provider-unhealthy", "health-unknown", "auth-missing",
                     "auth-unknown", "host-mismatch", "policy-blocked", "integration-unsupported",
                     "integration-unknown", "no-eligible-provider")
SELECTION_REASONS = ("only-eligible-candidate", "capability-preferred", "verified-state-preferred",
                     "cost-preferred", "local-preferred", "latency-preferred", "preference-order",
                     "id-tiebreak", "semantic-navigation-required", "browser-deterministic",
                     "reverse-engineering-required", "native-capability")

PROVIDER_FIELDS = {"id", "kind", "adoption", "capabilities", "locality", "cost", "latency", "risk",
                   "hosts", "auth", "requires", "integrations", "preference", "config_ref", "probe",
                   "reason", "notes", "source", "meta"}
POLICY_FIELDS = {"runtime_adoption", "allow_unknown_availability", "allow_unknown_health",
                 "allow_unknown_auth", "capability_preferences", "capability_reasons", "task_types",
                 "parity_columns"}


class RegistryError(Exception):
    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


@dataclass(frozen=True)
class Capability:
    id: str
    description: str


@dataclass(frozen=True)
class Provider:
    id: str
    kind: str
    adoption: str
    capabilities: tuple[str, ...]
    locality: str = "unknown"
    cost: str = "unknown"
    latency: str = "unknown"
    risk: str = "unknown"
    hosts: tuple[str, ...] = ("any",)
    auth: str = "none"
    requires: tuple[str, ...] = ()          # executor-native capabilities needed to use this
    integrations: tuple[tuple[str, str], ...] = ()   # executors only: (provider_id, state)
    preference: int = 100                   # lower == preferred (late tie-break only)
    config_ref: str | None = None           # e.g. workers.claude_code, mcp.serena, skills.superpowers
    probe: tuple[dict, ...] = ()
    reason: str | None = None
    notes: str = ""
    source: str = ""
    meta: tuple[tuple[str, object], ...] = ()

    @property
    def is_executor(self) -> bool:
        return self.kind == "worker"

    @property
    def worker_name(self) -> str | None:
        """workers.yaml key for an executor (via config_ref), else None."""
        if self.config_ref and self.config_ref.startswith("workers."):
            return self.config_ref.split(".", 1)[1]
        return None

    def integration(self, tool_id: str) -> str | None:
        return dict(self.integrations).get(tool_id)


@dataclass(frozen=True)
class Policy:
    runtime_adoption: tuple[str, ...] = ("adopted",)
    allow_unknown_availability: bool = False
    allow_unknown_health: bool = True
    allow_unknown_auth: bool = True
    capability_preferences: tuple[tuple[str, tuple[str, ...]], ...] = ()
    capability_reasons: tuple[tuple[str, str], ...] = ()
    task_types: tuple[tuple[str, tuple[str, ...]], ...] = ()
    parity_columns: tuple[str, ...] = ()

    def preferences_for(self, cap: str) -> tuple[str, ...]:
        return dict(self.capability_preferences).get(cap, ())

    def reason_for(self, cap: str) -> str | None:
        return dict(self.capability_reasons).get(cap)

    def capabilities_for_task_type(self, task_type: str | None) -> tuple[str, ...]:
        return dict(self.task_types).get(task_type or "", ())


@dataclass
class Registry:
    capabilities: dict[str, Capability] = field(default_factory=dict)
    providers: dict[str, Provider] = field(default_factory=dict)
    policy: Policy = field(default_factory=Policy)

    def register(self, provider: Provider) -> None:
        """Programmatic registration with the same per-record checks as the file."""
        errors = _check_provider(provider, self.capabilities)
        if provider.id in self.providers:
            errors.append(f"providers.{provider.id}: duplicate id")
        if errors:
            raise RegistryError(errors)
        self.providers[provider.id] = provider

    def get(self, provider_id: str) -> Provider:
        try:
            return self.providers[provider_id]
        except KeyError:
            raise KeyError(f"unknown provider {provider_id!r}") from None

    def providers_for(self, capability: str) -> list[Provider]:
        return [p for p in self.providers.values() if capability in p.capabilities]

    def executors(self) -> list[Provider]:
        return [p for p in self.providers.values() if p.is_executor]

    def is_known_capability(self, capability: str) -> bool:
        return capability in self.capabilities


# ------------------------------------------------------------------ parsing
class _UniqueKeyLoader(yaml.SafeLoader):
    """SafeLoader that rejects duplicate mapping keys (YAML silently keeps the last)."""


def _construct_mapping(loader, node, deep=False):
    seen = set()
    for key_node, _ in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in seen:
            raise yaml.constructor.ConstructorError(
                None, None, f"duplicate key {key!r}", key_node.start_mark)
        seen.add(key)
    return yaml.SafeLoader.construct_mapping(loader, node, deep)


_UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping)


def _tuple(v) -> tuple:
    if v is None:
        return ()
    return tuple(v) if isinstance(v, (list, tuple)) else (v,)


def _check_enum(errors, where, name, value, allowed):
    if value not in allowed:
        errors.append(f"{where}: invalid {name} {value!r} (allowed: {', '.join(allowed)})")


def _check_provider(p: Provider, catalog: dict[str, Capability]) -> list[str]:
    errors: list[str] = []
    w = f"providers.{p.id}"
    if not isinstance(p.id, str) or not PROVIDER_ID.fullmatch(p.id):
        errors.append(f"{w}: malformed provider id {p.id!r} (lowercase kebab-case)")
    _check_enum(errors, w, "kind", p.kind, KINDS)
    _check_enum(errors, w, "adoption", p.adoption, ADOPTION)
    _check_enum(errors, w, "locality", p.locality, LOCALITY)
    _check_enum(errors, w, "cost", p.cost, COST)
    _check_enum(errors, w, "latency", p.latency, LATENCY)
    _check_enum(errors, w, "risk", p.risk, RISK)
    _check_enum(errors, w, "auth", p.auth, AUTH)
    for h in p.hosts:
        _check_enum(errors, w, "host", h, HOSTS)
    if not p.capabilities:
        errors.append(f"{w}: declares no capabilities")
    if len(set(p.capabilities)) != len(p.capabilities):
        errors.append(f"{w}: duplicate capability in declaration")
    for c in (*p.capabilities, *p.requires):
        if not isinstance(c, str) or not CAPABILITY_ID.fullmatch(c):
            errors.append(f"{w}: malformed capability id {c!r}")
        elif c not in catalog:
            errors.append(f"{w}: unknown capability {c!r} (add it to the catalog first)")
    if not isinstance(p.preference, int) or isinstance(p.preference, bool):
        errors.append(f"{w}: preference must be an integer")
    # Contradictions.
    if p.adoption == "disabled" and not p.reason:
        errors.append(f"{w}: disabled entries need a reason")
    if p.locality == "local" and "cloud" in p.hosts:
        errors.append(f"{w}: locality=local contradicts host=cloud")
    if "any" in p.hosts and len(p.hosts) > 1:
        errors.append(f"{w}: host 'any' must be the only host")
    if p.is_executor and p.requires:
        errors.append(f"{w}: executors cannot `require` executor capabilities")
    if not p.is_executor and p.integrations:
        errors.append(f"{w}: only executors declare integrations")
    for tool, state in p.integrations:
        _check_enum(errors, f"{w}.integrations.{tool}", "state", state, INTEGRATION)
    for spec in p.probe:
        t = spec.get("type") if isinstance(spec, dict) else None
        if t not in PROBE_TYPES:
            errors.append(f"{w}: invalid probe type {t!r}")
        elif t == "env_auth" and p.auth == "none":
            errors.append(f"{w}: env_auth probe contradicts auth=none")
        elif t in ("executable", "claude_plugin") and not spec.get("target"):
            errors.append(f"{w}: {t} probe needs a target")
        elif t == "path" and not spec.get("paths"):
            errors.append(f"{w}: path probe needs paths")
        elif t == "env_auth" and not spec.get("env"):
            errors.append(f"{w}: env_auth probe needs env names")
        elif t == "config_health" and not spec.get("ref"):
            errors.append(f"{w}: config_health probe needs ref")
    return errors


def _provider_from(raw: dict) -> Provider:
    return Provider(
        id=raw.get("id"), kind=raw.get("kind"), adoption=raw.get("adoption"),
        capabilities=_tuple(raw.get("capabilities")),
        locality=raw.get("locality", "unknown"), cost=raw.get("cost", "unknown"),
        latency=raw.get("latency", "unknown"), risk=raw.get("risk", "unknown"),
        hosts=_tuple(raw.get("hosts", ["any"])), auth=raw.get("auth", "none"),
        requires=_tuple(raw.get("requires")),
        integrations=tuple(sorted((raw.get("integrations") or {}).items())),
        preference=raw.get("preference", 100), config_ref=raw.get("config_ref"),
        probe=_tuple(raw.get("probe")), reason=raw.get("reason"),
        notes=(raw.get("notes") or "").strip(), source=raw.get("source") or "",
        meta=tuple(sorted((raw.get("meta") or {}).items())))


def parse(data: dict, cfg=None) -> tuple[Registry, list[str]]:
    """Build a Registry from decoded YAML. Returns (registry, errors); never raises
    on content errors. `cfg` (agentos.config.Config) enables cross-file checks."""
    errors: list[str] = []
    if not isinstance(data, dict):
        return Registry(), ["registry: top level must be a mapping"]
    if data.get("version") != 1:
        errors.append(f"registry: unsupported version {data.get('version')!r}")
    unknown_top = set(data) - {"version", "capabilities", "providers", "policy"}
    if unknown_top:
        errors.append(f"registry: unknown top-level keys {sorted(unknown_top)}")

    reg = Registry()
    for cid, desc in (data.get("capabilities") or {}).items():
        if not isinstance(cid, str) or not CAPABILITY_ID.fullmatch(cid):
            errors.append(f"capabilities: malformed capability id {cid!r}")
            continue
        if not desc:
            errors.append(f"capabilities.{cid}: needs a description")
        reg.capabilities[cid] = Capability(cid, str(desc or ""))

    for i, raw in enumerate(data.get("providers") or []):
        if not isinstance(raw, dict) or "id" not in raw:
            errors.append(f"providers[{i}]: needs an id")
            continue
        extra = set(raw) - PROVIDER_FIELDS
        if extra:
            errors.append(f"providers.{raw['id']}: unknown fields {sorted(extra)}")
        p = _provider_from(raw)
        errs = _check_provider(p, reg.capabilities)
        if p.id in reg.providers:
            errs.append(f"providers.{p.id}: duplicate id")
        errors.extend(errs)
        if not errs:
            reg.providers[p.id] = p

    # Executor integrations must reference registered non-executor providers.
    for p in reg.executors():
        for tool, _ in p.integrations:
            t = reg.providers.get(tool)
            if t is None:
                errors.append(f"providers.{p.id}.integrations: unknown provider {tool!r}")
            elif t.is_executor:
                errors.append(f"providers.{p.id}.integrations: {tool!r} is an executor")

    raw_pol = data.get("policy") or {}
    extra = set(raw_pol) - POLICY_FIELDS
    if extra:
        errors.append(f"policy: unknown fields {sorted(extra)}")
    for a in _tuple(raw_pol.get("runtime_adoption", ["adopted"])):
        _check_enum(errors, "policy.runtime_adoption", "adoption", a, ADOPTION)
    prefs = {}
    for cap, ids in (raw_pol.get("capability_preferences") or {}).items():
        if cap not in reg.capabilities:
            errors.append(f"policy.capability_preferences: unknown capability {cap!r}")
        for pid in _tuple(ids):
            p = reg.providers.get(pid)
            if p is None:
                errors.append(f"policy.capability_preferences.{cap}: unknown provider {pid!r}")
            elif cap not in p.capabilities:
                errors.append(f"policy.capability_preferences.{cap}: {pid} does not declare {cap}")
        prefs[cap] = _tuple(ids)
    reasons = {}
    for cap, code in (raw_pol.get("capability_reasons") or {}).items():
        if cap not in reg.capabilities:
            errors.append(f"policy.capability_reasons: unknown capability {cap!r}")
        if code not in SELECTION_REASONS:
            errors.append(f"policy.capability_reasons.{cap}: unknown reason code {code!r}")
        reasons[cap] = code
    ttypes = {}
    for tt, caps in (raw_pol.get("task_types") or {}).items():
        for c in _tuple(caps):
            if c not in reg.capabilities:
                errors.append(f"policy.task_types.{tt}: unknown capability {c!r}")
        ttypes[tt] = _tuple(caps)
    for col in _tuple(raw_pol.get("parity_columns")):
        if col not in reg.capabilities and col not in reg.providers:
            errors.append(f"policy.parity_columns: {col!r} is neither a capability nor a provider")
    for k in ("allow_unknown_availability", "allow_unknown_health", "allow_unknown_auth"):
        if k in raw_pol and not isinstance(raw_pol[k], bool):
            errors.append(f"policy.{k}: must be a boolean")
    reg.policy = Policy(
        runtime_adoption=_tuple(raw_pol.get("runtime_adoption", ["adopted"])),
        allow_unknown_availability=bool(raw_pol.get("allow_unknown_availability", False)),
        allow_unknown_health=bool(raw_pol.get("allow_unknown_health", True)),
        allow_unknown_auth=bool(raw_pol.get("allow_unknown_auth", True)),
        capability_preferences=tuple(sorted(prefs.items())),
        capability_reasons=tuple(sorted(reasons.items())),
        task_types=tuple(sorted(ttypes.items())),
        parity_columns=_tuple(raw_pol.get("parity_columns")))

    if cfg is not None:
        errors.extend(_check_config_refs(reg, cfg))
    return reg, errors


_REF_SECTIONS = {"workers": ("workers", "workers"), "mcp": ("mcp", "tools"), "skills": ("skills", "sources")}


def _check_config_refs(reg: Registry, cfg) -> list[str]:
    errors = []
    for p in reg.providers.values():
        refs = [p.config_ref] + [s.get("ref") for s in p.probe if s.get("type") == "config_health"]
        for ref in filter(None, refs):
            section, _, name = ref.partition(".")
            if section not in _REF_SECTIONS:
                errors.append(f"providers.{p.id}: config ref {ref!r} must start with workers./mcp./skills.")
                continue
            file_key, sub = _REF_SECTIONS[section]
            if name not in (cfg.data.get(file_key) or {}).get(sub, {}):
                errors.append(f"providers.{p.id}: config ref {ref!r} not found in config/{file_key}.yaml")
        if p.is_executor and not p.worker_name:
            errors.append(f"providers.{p.id}: executors need config_ref workers.<name>")
    return errors


def registry_path(root: str | os.PathLike | None = None) -> Path:
    return Path(root or REPO_ROOT) / REGISTRY_FILE


def load_raw(root=None) -> dict:
    with open(registry_path(root), encoding="utf-8") as fh:
        return yaml.load(fh, Loader=_UniqueKeyLoader) or {}


def validate(cfg) -> list[str]:
    """Errors for the canonical registry file of `cfg.root` (empty == valid)."""
    try:
        data = load_raw(cfg.root)
    except FileNotFoundError:
        return [f"registry: {REGISTRY_FILE} missing"]
    except yaml.YAMLError as exc:
        return [f"registry: {str(exc).splitlines()[0]}"]
    return parse(data, cfg)[1]


def load(cfg=None, root=None) -> Registry:
    """Load and validate; raises RegistryError listing every problem."""
    root = root or (cfg.root if cfg is not None else None)
    try:
        data = load_raw(root)
    except yaml.YAMLError as exc:
        raise RegistryError([f"registry: {str(exc).splitlines()[0]}"]) from None
    reg, errors = parse(data, cfg)
    if errors:
        raise RegistryError(errors)
    return reg
