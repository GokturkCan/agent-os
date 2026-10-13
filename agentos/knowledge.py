"""SecondBrain write gate on top of claude-obsidian's transaction engine.

    capture (raw, content-addressed, create-only)
      -> propose  (bundle with expected hashes, engine `inspect` -> approval hash)
      -> approve  (independent reviewer + human approval ref, hash-pinned)
      -> apply    (engine CAS: fails if any target changed since proposal)
      -> lint

Workers can only reach `capture`-staging (inbox) and `propose`. `apply`
refuses without a matching approval record. agent-stack never writes into
wiki/ itself — the engine does, with journal + backups for recovery.
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from .config import Config, expand


class GateError(Exception):
    pass


def _sha(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except FileNotFoundError:
        return None


def _version_key(p: str):
    m = re.search(r"/(\d+)\.(\d+)\.(\d+)/scripts/", p)
    return tuple(int(x) for x in m.groups()) if m else (0, 0, 0)


def engine_cli(cfg: Config) -> Path:
    env = os.environ.get("AGENTOS_OBSIDIAN_CLI")
    if env:
        return Path(env)
    hits = sorted(glob.glob(str(expand(cfg.knowledge["vault"]["engine_cli_glob"]))), key=_version_key)
    if not hits:
        raise GateError("claude-obsidian engine not found")
    return Path(hits[-1])


class Vault:
    def __init__(self, cfg: Config, root: Path | str | None = None,
                 state_dir: Path | str | None = None):
        self.cfg = cfg
        self.root = Path(root or os.environ.get("AGENTOS_VAULT") or expand(cfg.knowledge["vault"]["root"]))
        wp = cfg.knowledge["write_path"]
        base = Path(state_dir) if state_dir else None
        self.proposal_dir = base / "proposals" if base else expand(wp["proposal_dir"])
        self.approval_dir = base / "approvals" if base else expand(wp["approval_record_dir"])
        self.cli = engine_cli(cfg)

    # ------------------------------------------------------ engine io
    def _engine(self, *args: str, check: bool = True) -> dict:
        r = subprocess.run(["python3", str(self.cli), *args], capture_output=True, text=True,
                           cwd=self.root)
        try:
            out = json.loads(r.stdout) if r.stdout.strip() else {}
        except json.JSONDecodeError:
            out = {"raw_stdout": r.stdout}
        out["_returncode"] = r.returncode
        if check and r.returncode != 0:
            raise GateError(f"engine {args[0]} {args[1] if len(args) > 1 else ''} failed "
                            f"rc={r.returncode}: {r.stderr.strip()[-800:] or r.stdout[-800:]}")
        return out

    def doctor(self) -> dict:
        return self._engine("doctor", check=False)

    def lint(self) -> dict:
        return self._engine("lint", "--vault", str(self.root), "--format", "json", check=False)

    def sha(self, rel: str) -> str | None:
        return _sha(self.root / rel)

    def read(self, rel: str) -> str:
        return (self.root / rel).read_text()

    # --------------------------------------------------------- capture
    def capture(self, sources: list[str]) -> dict:
        """Copy staged inbox files into immutable .raw/captured/<sha256>.<ext>.
        Create-only: an existing identical capture is a no-op."""
        plan = self._engine("capture", "apply", "--vault", str(self.root), *sources)
        items = [i for i in plan.get("items", []) if i.get("would_change")]
        if not items:
            return {"status": "noop", "items": plan.get("items", [])}
        # Pin the reviewed plan's identity so apply regenerates exactly it.
        res = self._engine("capture", "apply", "--vault", str(self.root), *sources, "--apply",
                           "--operation-id", plan["operation"]["operation_id"],
                           "--generated-at", plan["generated_at"],
                           "--approved-plan-sha256", plan["approved_plan_sha256"])
        res["plan_items"] = plan.get("items", [])
        return res

    # --------------------------------------------------------- propose
    def propose(self, operation_id: str, operation_type: str, writes: list[dict],
                proposer: str, source_manifest_updates: dict | None = None,
                address_requests: list | None = None) -> dict:
        for w in writes:
            if not (w["path"].startswith("wiki/")):
                raise GateError(f"proposals may only target wiki/: {w['path']}")
        bundle = {
            "schema": "claude-obsidian.transaction.v1",
            "operation_id": operation_id,
            "operation_type": operation_type,
            "address_requests": address_requests or [],
            "source_manifest_updates": source_manifest_updates or {},
            # Expected hashes pin the exact pre-state the proposal was made against.
            "expected_hashes": {w["path"]: self.sha(w["path"]) for w in writes},
            "writes": writes,
        }
        if source_manifest_updates:
            bundle["expected_hashes"][".raw/.manifest.json"] = self.sha(".raw/.manifest.json")
        self.proposal_dir.mkdir(parents=True, exist_ok=True)
        path = self.proposal_dir / f"{operation_id}.json"
        if path.exists():
            raise GateError(f"proposal {operation_id} already exists")
        path.write_text(json.dumps(bundle, indent=2))
        plan = self._engine("transaction", "inspect", "--vault", str(self.root), str(path))
        if not plan.get("valid"):
            raise GateError(f"engine rejected bundle: {plan}")
        meta = {"operation_id": operation_id, "proposer": proposer, "bundle": str(path),
                "approval_sha256": plan["approval_sha256"], "changed_paths": plan["changed_paths"],
                "proposed_at": datetime.now(timezone.utc).isoformat()}
        (self.proposal_dir / f"{operation_id}.meta.json").write_text(json.dumps(meta, indent=2))
        return meta

    # --------------------------------------------------------- approve
    def approve(self, operation_id: str, reviewer: str, approval_sha256: str,
                human_approval_ref: str) -> dict:
        meta = json.loads((self.proposal_dir / f"{operation_id}.meta.json").read_text())
        if reviewer == meta["proposer"]:
            raise GateError("reviewer must be independent of the proposer")
        if approval_sha256 != meta["approval_sha256"]:
            raise GateError("approval hash does not match the inspected proposal")
        if not human_approval_ref:
            raise GateError("canonical writes need a human approval reference in V1")
        rec = {"operation_id": operation_id, "reviewer": reviewer, "proposer": meta["proposer"],
               "approval_sha256": approval_sha256, "human_approval_ref": human_approval_ref,
               "approved_at": datetime.now(timezone.utc).isoformat()}
        self.approval_dir.mkdir(parents=True, exist_ok=True)
        (self.approval_dir / f"knowledge-{operation_id}.json").write_text(json.dumps(rec, indent=2))
        return rec

    # ----------------------------------------------------------- apply
    def apply(self, operation_id: str) -> dict:
        ap = self.approval_dir / f"knowledge-{operation_id}.json"
        if not ap.exists():
            raise GateError(f"no approval record for {operation_id}; canonical write refused")
        rec = json.loads(ap.read_text())
        meta = json.loads((self.proposal_dir / f"{operation_id}.meta.json").read_text())
        if rec["approval_sha256"] != meta["approval_sha256"]:
            raise GateError("approval record does not match proposal")
        res = self._engine("transaction", "apply", "--vault", str(self.root),
                           "--approved-plan-sha256", rec["approval_sha256"], meta["bundle"],
                           check=False)
        if res["_returncode"] != 0 or res.get("status") != "complete":
            raise GateError(f"engine refused apply (no write performed or rolled back): "
                            f"{json.dumps({k: v for k, v in res.items() if k != 'writes'})[:800]}")
        res["lint"] = self.lint().get("summary")
        return res


# ------------------------------------------------------ bundle helpers
def utc_today() -> str:
    """The engine audits dates against the UTC calendar day."""
    return datetime.now(timezone.utc).date().isoformat()


def stable_source_id(origin_kind: str, locator: str, content_sha256: str | None) -> str:
    """Mirror of claude_obsidian.ledgers.stable_source_id for file/manual origins
    (the engine re-validates it on inspect, so a mismatch can never land)."""
    digest = hashlib.sha256(
        f"{origin_kind.casefold()}\0{locator}\0{(content_sha256 or '').casefold()}".encode()).hexdigest()
    return f"src-{digest[:20]}"


def ingest_source_writes(vault: Vault, raw_sha: str, raw_rel: str, title: str, body_md: str,
                         claims: dict[str, str], authority: str, today: str | None = None,
                         content_kind: str = "document") -> dict:
    """Build writes for a new source page + ledger entries (provenance kept:
    page -> source_id -> raw sha256 -> .raw path)."""
    today = today or utc_today()
    source_id = stable_source_id("file", raw_rel, raw_sha)
    page = f"wiki/sources/{title}.md"
    claim_ids = list(claims)
    fm = "\n".join([
        "---", "type: source", f'title: "{title}"', f"created: {today}", f"updated: {today}",
        "status: seed", "tags:", "  - source", f'source_id: "{source_id}"', f'sha256: "{raw_sha}"',
        f"authority: {authority}", "review_state: unreviewed", "key_claims:",
        *[f"  - {c}" for c in claim_ids], "---", ""])
    content = f"{fm}\n# {title}\n\nEvidence: `{raw_rel}` (SHA-256 `{raw_sha}`).\n\n{body_md.strip()}\n"

    sl = json.loads(vault.read("wiki/meta/ledgers/source-ledger.json"))
    sl["sources"][source_id] = {
        "origin": {"kind": "file", "locator": raw_rel}, "content_kind": content_kind,
        "title": title, "authority": authority, "content_sha256": raw_sha, "ingested_at": today,
        "retrieved_at": None, "refresh_due": None, "review_status": "unreviewed",
        "independence_key": None, "pages": [page], "supersedes": None}
    cl = json.loads(vault.read("wiki/meta/ledgers/claim-ledger.json"))
    for cid, text in claims.items():
        cl["claims"][cid] = {
            "text": text, "risk": "normal", "assessment": "unsupported", "confidence": "unknown",
            "location": {"path": page, "anchor": title}, "reviewed_at": None,
            "notes": "Single source; pending independent corroboration.", "supersedes": None,
            "evidence": [{"source_id": source_id, "relation": "supports", "locator": None}]}
    log = vault.read("wiki/log.md").rstrip() + f"\n\n## {today} — ingest {title}\n\n- Created [[{title}]] ({source_id}) from `{raw_rel}`.\n"
    index = vault.read("wiki/index.md").rstrip() + f"\n- [[{title}]] — {authority} source.\n"
    writes = [
        {"path": page, "mode": "create", "content": content},
        {"path": "wiki/meta/ledgers/source-ledger.json", "mode": "replace",
         "content": json.dumps(sl, indent=2, sort_keys=False) + "\n"},
        {"path": "wiki/meta/ledgers/claim-ledger.json", "mode": "replace",
         "content": json.dumps(cl, indent=2, sort_keys=False) + "\n"},
        {"path": "wiki/log.md", "mode": "replace", "content": log},
        {"path": "wiki/index.md", "mode": "replace", "content": index},
    ]
    manifest = {raw_sha: {"ingested_at": f"{today}T00:00:00Z", "pages_created": [page],
                          "source_id": source_id}}
    return {"writes": writes, "source_id": source_id, "page": page,
            "source_manifest_updates": manifest,
            "address_requests": [{"path": page, "prefix": "c"}]}
