"""`agentos capabilities ...` — read-only inspection of the capability plane.

  list    [--kind K] [--adoption A] [--json]       registered providers
  show    <id> [--probe] [--json]                  one provider (+ probe state)
  match   <capability...> [constraints] [--json]   eligibility, selection, fallbacks
  matrix  [--probe] [--json]                       executor parity matrix
  check   [--deep] [--json]                        probe availability/health/auth

Nothing here executes a worker or makes a network request. `--deep` runs
local `--version` health checks. Exit codes: 0 ok, 1 invalid registry,
2 match is blocked.
"""
from __future__ import annotations

import json

from . import capability_policy as CP
from . import capability_probes as P
from . import capability_registry as R


def add_parser(sub) -> None:
    cp = sub.add_parser("capabilities", help="inspect the capability registry / selection policy")
    csub = cp.add_subparsers(dest="cap_cmd", required=True)
    ls = csub.add_parser("list")
    ls.add_argument("--kind", choices=R.KINDS)
    ls.add_argument("--adoption", choices=R.ADOPTION)
    ls.add_argument("--json", action="store_true")
    sh = csub.add_parser("show")
    sh.add_argument("id")
    sh.add_argument("--probe", action="store_true")
    sh.add_argument("--json", action="store_true")
    m = csub.add_parser("match")
    m.add_argument("capability", nargs="*")
    m.add_argument("--task-type")
    m.add_argument("--task-id")
    m.add_argument("--host", action="append", default=[], choices=R.HOSTS)
    m.add_argument("--locality", action="append", default=[], choices=R.LOCALITY)
    m.add_argument("--max-cost", choices=R.COST)
    m.add_argument("--max-risk", choices=R.RISK)
    m.add_argument("--deny", action="append", default=[])
    m.add_argument("--strict", action="store_true", help="reject unknown health/auth")
    m.add_argument("--unavailable", action="append", default=[], metavar="ID", help="what-if: treat as absent")
    m.add_argument("--unhealthy", action="append", default=[], metavar="ID")
    m.add_argument("--no-auth", action="append", default=[], metavar="ID", help="what-if: auth missing")
    m.add_argument("--deep", action="store_true")
    m.add_argument("--record", action="store_true", help="emit a capability_decision event")
    m.add_argument("--json", action="store_true")
    mx = csub.add_parser("matrix")
    mx.add_argument("--probe", action="store_true")
    mx.add_argument("--json", action="store_true")
    ck = csub.add_parser("check")
    ck.add_argument("--deep", action="store_true")
    ck.add_argument("--json", action="store_true")


def _out(obj, as_json: bool, lines: list[str]) -> None:
    print(json.dumps(obj, indent=2, default=str) if as_json else "\n".join(lines))


def _provider_dict(p: R.Provider) -> dict:
    return {"id": p.id, "kind": p.kind, "adoption": p.adoption, "capabilities": list(p.capabilities),
            "locality": p.locality, "cost": p.cost, "latency": p.latency, "risk": p.risk,
            "hosts": list(p.hosts), "auth": p.auth, "requires": list(p.requires),
            "integrations": dict(p.integrations), "preference": p.preference, "config_ref": p.config_ref,
            "probe": [dict(s) for s in p.probe], "notes": p.notes, "source": p.source}


def run(cfg, a) -> int:
    try:
        reg = R.load(cfg)
    except R.RegistryError as exc:
        print("capability registry invalid:\n  " + "\n  ".join(exc.errors))
        return 1
    ctx = P.ProbeContext(cfg=cfg, deep=getattr(a, "deep", False))

    if a.cap_cmd == "list":
        ps = [p for p in reg.providers.values()
              if (not a.kind or p.kind == a.kind) and (not a.adoption or p.adoption == a.adoption)]
        lines = [f"{'ID':24} {'KIND':8} {'ADOPTION':9} {'LOCALITY':9} {'COST':22} CAPABILITIES"]
        lines += [f"{p.id:24} {p.kind:8} {p.adoption:9} {p.locality:9} {p.cost:22} {', '.join(p.capabilities)}"
                  for p in sorted(ps, key=lambda p: (R.KINDS.index(p.kind), p.id))]
        lines.append(f"\n{len(ps)} registered (registration != availability; see `capabilities check`)")
        _out([_provider_dict(p) for p in ps], a.json, lines)
        return 0

    if a.cap_cmd == "show":
        if a.id not in reg.providers:
            print(f"unknown provider {a.id!r}")
            return 2
        p = reg.get(a.id)
        d = _provider_dict(p)
        lines = [f"{k:13} {v}" for k, v in d.items() if v not in ("", [], {}, None)]
        if a.probe:
            r = P.probe_provider(p, ctx)
            d["probe_result"] = r.to_dict()
            lines += ["", f"installed={r.installed} available={r.available} health={r.health} auth={r.auth}",
                      *[f"  {x}" for x in r.details], *[f"  error: {x}" for x in r.errors]]
        _out(d, a.json, lines)
        return 0

    if a.cap_cmd == "match":
        overrides: dict = {}
        for ids, field_, value in ((a.unavailable, "available", "absent"), (a.unhealthy, "health", "unhealthy"),
                                   (a.no_auth, "auth", "missing")):
            for pid in ids:
                if pid not in reg.providers:
                    print(f"unknown provider {pid!r}")
                    return 2
                overrides.setdefault(pid, {})[field_] = value
        caps = CP.resolve_required(reg, a.capability, a.task_type)
        probes = P.probe_all(reg, ctx, overrides)
        plan = CP.plan(reg, CP.CapabilityRequest(
            required=caps, task_id=a.task_id, task_type=a.task_type, hosts=tuple(a.host),
            localities=tuple(a.locality), max_cost=a.max_cost, max_risk=a.max_risk, deny=tuple(a.deny),
            strict=a.strict), probes, deliverable=CP.worker_deliverable(ctx.cfg))
        if a.record:
            CP.emit_decision(plan, a.task_id)
        _out(plan.to_dict(), a.json, plan.explain())
        return 0 if plan.status == "selected" else 2

    if a.cap_cmd == "matrix":
        probes = P.probe_all(reg, ctx) if a.probe else None
        m = CP.parity_matrix(reg, probes)
        width = max(12, *(len(c) for c in m["columns"])) + 2
        lines = ["executor".ljust(14) + "".join(c.ljust(width) for c in m["columns"])]
        for eid, row in m["rows"].items():
            cells = []
            for c in m["columns"]:
                cell = row[c]
                txt = cell["state"] + (f":{'/'.join(cell['via'])}" if cell.get("via") else "")
                if "available" in cell and cell["state"] == "supported" and cell["available"] != "present":
                    txt += f"({cell['available']})"
                cells.append(txt.ljust(width))
            lines.append(eid.ljust(14) + "".join(cells))
        lines.append("\nnative | via:<tool> | supported | unsupported | unknown — unknown is never "
                     "inferred; `match` answers which executor can satisfy a task")
        _out(m, a.json, lines)
        return 0

    if a.cap_cmd == "check":
        res = P.probe_all(reg, ctx)
        lines = [f"{'ID':24} {'INSTALLED':9} {'AVAILABLE':9} {'HEALTH':9} {'AUTH':12} ADOPTION"]
        for pid, r in res.items():
            lines.append(f"{pid:24} {r.installed:9} {r.available:9} {r.health:9} {r.auth:12} "
                         f"{reg.get(pid).adoption}" + (f"  errors={list(r.errors)}" if r.errors else ""))
        avail = sum(r.available == "present" for r in res.values())
        lines.append(f"\n{len(res)} registered, {avail} available"
                     + ("" if a.deep else " (health from last observed config only; --deep runs local checks)"))
        _out({pid: r.to_dict() for pid, r in res.items()}, a.json, lines)
        return 0
    return 0
