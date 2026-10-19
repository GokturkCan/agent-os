"""Compute-node capability registry and authorization ladder (CN-1).

Reuses config/resources.yaml for node identity/reachability (agentos/resources.py probes it). config/compute.yaml
(PROTECTED) holds node enablement + endpoint/auth references, capability types, declared offerings and
human-approved authorizations.

  configured != installed != healthy != benchmarked != authorized != ACTIVE

`evaluate` derives each fact from its own source. Runtime reports from a node (what it advertises, whether
it says it is healthy) can only ever make an offering LESS eligible; they are never an authorization.
Everything fails closed: missing, malformed or contradictory input yields "not eligible" with a reason.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .config import Config

DEFAULT_LIMITS = {"max_deadline_seconds": 3600, "max_params_bytes": 8192, "max_inputs": 16}
_ID = re.compile(r"[a-z0-9][a-z0-9_.-]{0,63}")
_REF = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}")                 # symbolic only: no scheme, host, dots or '@'
_AUTH_REF = re.compile(r"(env|keychain):[A-Za-z0-9_.-]{1,64}")
_OFFERING_KEYS = {"node", "capability", "model", "runtime", "operations", "limits", "hardware", "features",
                  "benchmark"}
_MODEL_KEYS = {"id", "revision", "quantization", "license"}


def section(cfg: Config) -> dict:
    d = (getattr(cfg, "data", {}) or {}).get("compute")
    return d if isinstance(d, dict) else {}


def data_classes(cfg: Config) -> list[str]:
    v = section(cfg).get("data_classes")
    return [x for x in v if isinstance(x, str)] if isinstance(v, list) else []


def limits(cfg: Config) -> dict:
    out = dict(DEFAULT_LIMITS)
    raw = section(cfg).get("job_limits")
    if isinstance(raw, dict):
        for k in out:
            v = raw.get(k)
            if isinstance(v, int) and not isinstance(v, bool) and v > 0:
                out[k] = min(v, DEFAULT_LIMITS[k])        # config may tighten, never loosen, the ceilings
    return out


def offerings(cfg: Config) -> dict:
    v = section(cfg).get("offerings")
    return v if isinstance(v, dict) else {}


def authorizations(cfg: Config) -> list[dict]:
    v = section(cfg).get("authorizations")
    return [a for a in v if isinstance(a, dict)] if isinstance(v, list) else []


def node_compute(cfg: Config, node: str) -> dict:
    """Enablement/endpoint/auth references for a node: ONLY from the protected compute.yaml `nodes:` block.
    (A `compute` block in the tunable resources.yaml is ignored here and rejected by validate().)"""
    n = section(cfg).get("nodes")
    c = n.get(node) if isinstance(n, dict) else None
    return c if isinstance(c, dict) else {}


def node_enabled(cfg: Config, node: str) -> bool:
    return node_compute(cfg, node).get("enabled") is True


# ------------------------------------------------------------------ validation (config.validate)
def validate(cfg: Config) -> list[str]:
    errors: list[str] = []
    sec = section(cfg)
    if not sec:
        return ["compute: config/compute.yaml missing or not a mapping"]
    types = sec.get("capability_types")
    if not isinstance(types, dict) or not types:
        return ["compute.capability_types must be a non-empty mapping"]
    for tid, t in types.items():
        ops = t.get("operations") if isinstance(t, dict) else None
        if not (isinstance(tid, str) and _ID.fullmatch(tid)) or not isinstance(t, dict) or not t.get("modality") \
                or not (isinstance(ops, list) and ops and all(isinstance(o, str) for o in ops)):
            errors.append(f"compute.capability_types.{tid}: needs a modality and a non-empty operations list")
    classes = sec.get("data_classes")
    if not (isinstance(classes, list) and classes and all(isinstance(c, str) for c in classes)
            and len(set(classes)) == len(classes)):
        errors.append("compute.data_classes must be a non-empty list of unique strings")
        classes = []
    lim = sec.get("job_limits")
    if lim is not None:
        for k, ceiling in DEFAULT_LIMITS.items():
            v = (lim or {}).get(k, ceiling) if isinstance(lim, dict) else None
            if isinstance(v, bool) or not isinstance(v, int) or not 0 < v <= ceiling:
                errors.append(f"compute.job_limits.{k} must be an integer in 1..{ceiling}")

    res_nodes = cfg.resources.get("nodes") or {}
    for name, n in res_nodes.items():                                # security-sensitive keys may not live in resources.yaml
        if isinstance(n, dict) and "compute" in n:
            errors.append(f"resources.nodes.{name}.compute: compute enablement/endpoint/auth belong in the "
                          f"protected config/compute.yaml `nodes:` block, not in resources.yaml")
    cnodes = sec.get("nodes")
    if cnodes is None:
        cnodes = {}
    if not isinstance(cnodes, dict):
        errors.append("compute.nodes must be a mapping")
        cnodes = {}
    for name, c in cnodes.items():                                   # node-level compute block
        w = f"compute.nodes.{name}"
        if name not in res_nodes:
            errors.append(f"{w}: node is not declared in resources.yaml")
        if not isinstance(c, dict):
            errors.append(f"{w}: must be a mapping")
            continue
        if not isinstance(c.get("enabled"), bool):
            errors.append(f"{w}.enabled must be a boolean")
        ep = c.get("endpoint_ref")
        if ep is not None and not (isinstance(ep, str) and _REF.fullmatch(ep)):
            errors.append(f"{w}.endpoint_ref must be a symbolic reference, never a URL/address/credential")
        ar = c.get("auth_ref")
        if ar is not None and not (isinstance(ar, str) and _AUTH_REF.fullmatch(ar)):
            errors.append(f"{w}.auth_ref must be 'env:NAME' or 'keychain:NAME' (no inline secrets)")
        if c.get("enabled") is True and (not c.get("endpoint_ref") or not c.get("auth_ref")):
            errors.append(f"{w}: enabled requires endpoint_ref and auth_ref")
        if name == "mac" and c.get("enabled") is True:
            errors.append(f"{w}: the control plane is not a remote compute node")

    offs = sec.get("offerings")
    if not isinstance(offs, dict):
        errors.append("compute.offerings must be a mapping")
        offs = {}
    for oid, o in offs.items():
        errors.extend(_validate_offering(oid, o, types, res_nodes))
    auths = sec.get("authorizations")
    if not isinstance(auths, list):
        errors.append("compute.authorizations must be a list")
        auths = []
    seen = set()
    for i, a in enumerate(auths):
        errors.extend(_validate_authorization(i, a, offs, classes, seen))
    return errors


def _validate_offering(oid, o, types, res_nodes) -> list[str]:
    w = f"compute.offerings.{oid}"
    if not (isinstance(oid, str) and _ID.fullmatch(oid)) or not isinstance(o, dict):
        return [f"{w}: id must be a simple identifier and the entry a mapping"]
    errs = [f"{w}: unknown field {k!r}" for k in o if k not in _OFFERING_KEYS]
    if o.get("node") not in res_nodes or o.get("node") == "mac":
        errs.append(f"{w}.node must be a declared non-control-plane node")
    t = types.get(o.get("capability")) if isinstance(types, dict) else None
    if not isinstance(t, dict):
        errs.append(f"{w}.capability must be a declared capability type")
        t = {}
    ops = o.get("operations")
    if not (isinstance(ops, list) and ops and set(ops) <= set(t.get("operations") or [])):
        errs.append(f"{w}.operations must be a non-empty subset of the capability type's operations")
    m = o.get("model")
    if not (isinstance(m, dict) and set(m) <= _MODEL_KEYS and isinstance(m.get("id"), str) and m.get("id")
            and isinstance(m.get("revision"), str) and m.get("revision")):
        errs.append(f"{w}.model needs a pinned id and revision (allowed keys {sorted(_MODEL_KEYS)})")
    if not (isinstance(o.get("runtime"), str) and o.get("runtime")):
        errs.append(f"{w}.runtime is required")
    b = o.get("benchmark")
    state = b.get("state") if isinstance(b, dict) else None
    if state not in ("unbenchmarked", "benchmarked"):
        errs.append(f"{w}.benchmark.state must be 'unbenchmarked' or 'benchmarked'")
    elif state == "benchmarked" and not (isinstance(b.get("evidence"), list) and b["evidence"]
                                         and all(isinstance(e, str) for e in b["evidence"])):
        errs.append(f"{w}: benchmarked requires evidence files")
    return errs


def _validate_authorization(i, a, offs, classes, seen) -> list[str]:
    w = f"compute.authorizations[{i}]"
    errs = [f"{w}: unknown field {k!r}" for k in a if k not in ("offering", "revision", "max_data_class",
                                                                    "approval_ref")]
    off = offs.get(a.get("offering")) if isinstance(offs, dict) else None
    if not isinstance(off, dict):
        return errs + [f"{w}.offering must name a declared offering"]
    if a["offering"] in seen:
        errs.append(f"{w}: duplicate authorization for {a['offering']!r}")
    seen.add(a["offering"])
    model = off.get("model") if isinstance(off.get("model"), dict) else {}
    if a.get("revision") != model.get("revision") or not a.get("revision"):
        errs.append(f"{w}.revision must equal the offering's pinned model revision")
    if a.get("max_data_class") not in classes:
        errs.append(f"{w}.max_data_class must be one of {classes}")
    if not (isinstance(a.get("approval_ref"), str) and a["approval_ref"].strip()):
        errs.append(f"{w}.approval_ref (human approval) is required")
    if (off.get("benchmark") or {}).get("state") != "benchmarked":
        errs.append(f"{w}: cannot authorize an unbenchmarked offering")
    return errs


# ------------------------------------------------------------------ the ladder
@dataclass(frozen=True)
class Eligibility:
    offering: str
    configured: bool = False
    installed: bool = False
    healthy: bool = False
    benchmarked: bool = False
    authorized: bool = False
    node_enabled: bool = False
    node_reachable: bool = False
    max_data_class: str | None = None
    reasons: tuple = field(default_factory=tuple)

    @property
    def active(self) -> bool:
        return (self.configured and self.installed and self.healthy and self.benchmarked and self.authorized
                and self.node_enabled and self.node_reachable)

    def to_dict(self) -> dict:
        return {**{k: getattr(self, k) for k in ("offering", "configured", "installed", "healthy", "benchmarked",
                                                 "authorized", "node_enabled", "node_reachable",
                                                 "max_data_class")},
                "active": self.active, "reasons": list(self.reasons)}


def authorization_for(cfg: Config, offering_id: str) -> dict | None:
    """The valid authorization for an offering (revision pinned), or None. Config-only; never a node report."""
    off = offerings(cfg).get(offering_id)
    if not isinstance(off, dict) or not isinstance(off.get("model"), dict):
        return None
    for a in authorizations(cfg):
        if a.get("offering") == offering_id and a.get("revision") == off["model"].get("revision") \
                and a.get("max_data_class") in data_classes(cfg) \
                and isinstance(a.get("approval_ref"), str) and a["approval_ref"].strip() \
                and (off.get("benchmark") or {}).get("state") == "benchmarked":
            return a
    return None


def evaluate(cfg: Config, offering_id: str, *, advertised: dict | None = None,
             node_reachable: bool = False, node_healthy: bool = False) -> Eligibility:
    """Where one offering sits on the ladder. `advertised` is the node's untrusted GET /capabilities
    body: {"offerings": {offering_id: {"revision": str, "healthy": bool}}}. It can only confirm
    `installed`/`healthy`; it cannot create an offering, change a revision's authorization or widen data classes."""
    off = offerings(cfg).get(offering_id)
    if not isinstance(off, dict):
        return Eligibility(offering_id, reasons=("not a configured offering",))
    node = off.get("node")
    reasons = []
    enabled = node_enabled(cfg, node)
    if not enabled:
        reasons.append(f"node {node!r} is not enabled for compute")
    if not node_reachable:
        reasons.append(f"node {node!r} not reachable")
    adv = ((advertised or {}).get("offerings") or {}).get(offering_id) if isinstance(advertised, dict) else None
    rev = (off.get("model") or {}).get("revision")
    installed = isinstance(adv, dict) and adv.get("revision") == rev
    if not installed:
        reasons.append("not advertised by the node at the pinned revision")
    healthy = installed and node_healthy and adv.get("healthy") is True
    if installed and not healthy:
        reasons.append("node or offering reports unhealthy")
    benchmarked = (off.get("benchmark") or {}).get("state") == "benchmarked"
    if not benchmarked:
        reasons.append("not benchmarked")
    auth = authorization_for(cfg, offering_id)
    if auth is None:
        reasons.append("no authorization at the pinned revision")
    return Eligibility(offering_id, True, installed, healthy, benchmarked, auth is not None, enabled,
                       node_reachable, (auth or {}).get("max_data_class"), tuple(reasons))
