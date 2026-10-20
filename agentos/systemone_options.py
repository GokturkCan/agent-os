"""Authoritative, compact descriptions of SystemOne's eligible options (R3.2C).

A backend that is shown bare worker ids has nothing to decide on (R3.2B: it followed a fixed label
preference). This module builds the missing context from the SAME config the deterministic policy
already uses - never from model output, never invented:

  roles      config/workers.yaml  `roles`               (what the worker is documented to be for)
  access     config/providers.yaml `access`             (harness = existing subscription, api = API key)
  cost       capability registry `cost` (when registered)
  locality   capability registry / provider `locality`
  latency    capability registry / provider `latency_class`
  interactive config/workers.yaml `interactive: false`  (background-only workers)
  missing    capability registry: which REQUIRED capabilities this worker can neither provide natively
             nor through a tool it is declared to support (same logic as the capability plane)

Free-text fields (notes, paths) are deliberately excluded. The result is advisory context only:
`SystemOneRequest.eligible_options` alone defines what is legal, an id that is not a configured worker
gets no metadata, and agentos/systemone_adapter.py validates and size-caps whatever is sent.
"""
from __future__ import annotations

import functools

from . import capability_policy, capability_registry

# Instruction shown with the worker question when option metadata is present.
QUESTION_PROMPT = ("Which worker best fits this task, given its need, required capabilities, risk and cost "
                   "profile? Prefer a worker that is not missing a required capability.")
MAX_ROLES = 6


@functools.lru_cache(maxsize=8)
def _registry_cached(root: str, mtime_ns: int):
    reg, errors = capability_registry.parse(capability_registry.load_raw(root))
    return None if errors else reg


def _registry(cfg):
    """The validated capability registry for cfg's root, or None (metadata then omits registry facts)."""
    try:
        root = str(cfg.root)
        return _registry_cached(root, capability_registry.registry_path(root).stat().st_mtime_ns)
    except Exception:
        return None


def missing_capabilities(reg, executor, required) -> list[str]:
    """Required capabilities `executor` can provide neither natively nor via a supported tool."""
    missing = []
    for cap in sorted(set(required)):
        if cap in executor.capabilities:
            continue
        tools = [t for t in reg.providers_for(cap) if not t.is_executor
                 and t.adoption in reg.policy.runtime_adoption
                 and capability_policy.integration_state(executor, t) == "supported"]
        if not tools:
            missing.append(cap)
    return missing


def build(cfg, options, required_capabilities=()) -> dict:
    """option id -> compact metadata, for the offered options that are configured workers."""
    workers, providers = cfg.workers["workers"], cfg.providers["providers"]
    reg = _registry(cfg)
    by_worker = {p.worker_name: p for p in reg.executors()} if reg else {}
    out = {}
    for opt in options:
        w = workers.get(opt)
        if not isinstance(w, dict):
            continue
        prov = providers.get(w.get("provider")) or {}
        ex = by_worker.get(opt)
        info = {}
        if w.get("roles"):
            info["roles"] = [str(r) for r in w["roles"]][:MAX_ROLES]
        if prov.get("access"):
            info["access"] = str(prov["access"])
        if ex is not None and ex.cost != "unknown":
            info["cost"] = ex.cost
        locality = ex.locality if ex is not None and ex.locality != "unknown" else prov.get("locality")
        if locality:
            info["locality"] = str(locality)
        latency = ex.latency if ex is not None and ex.latency != "unknown" else prov.get("latency_class")
        if latency:
            info["latency"] = str(latency)
        if w.get("interactive") is False:
            info["interactive"] = False
        if ex is not None and required_capabilities:
            info["missing"] = missing_capabilities(reg, ex, required_capabilities)[:8]
        if info:
            out[opt] = info
    return out
