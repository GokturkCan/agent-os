"""Task-scoped delivery of a vendored skill into ONE worker's own worktree.

A skill whose lock entry (scripts/runtime/skills.lock.json) carries a `delivery` block is never copied into
~/.claude, ~/.codex, OpenCode, Hermes or ~/agent-stack/skills. Only when the deterministic capability plan selects it
for a dispatched task is it provisioned into `<worktree>/.claude/skills/<name>`, after its locked hashes verify, and
removed again when the worker returns; the skill's working files are moved into the task's evidence directory.
No git configuration is touched (shared `info/exclude` would leak into the target repository). Skills without a `delivery` block (Ponytail, Orchestra index, ambient host
skills) are untouched by this module: `deliverable()` is True for them, so existing plans do not change.

Fail closed: a selected skill that cannot be delivered verified is never skipped silently.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
LOCK = Path("scripts") / "runtime" / "skills.lock.json"
MAX_EVIDENCE_FILES = 200
MAX_EVIDENCE_FILE_BYTES = 25 * 1024 * 1024


class SkillDeliveryError(Exception):
    pass


def _lock(repo: Path) -> dict:
    return json.loads((repo / LOCK).read_text())


def entry(repo: Path | None, skill_id: str) -> dict | None:
    e = _lock(repo or REPO).get(skill_id)
    return e if e and "delivery" in e else None


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def verify(repo: Path, skill_id: str) -> list[str]:
    """Problems with the vendored tree of `skill_id` (empty list = verified)."""
    e = entry(repo, skill_id)
    if e is None:
        return [f"{skill_id}: no lock entry with a delivery block"]
    errs = []
    for rel, digest in {**e["sha256"], **e.get("license_file", {})}.items():
        p = repo / rel
        if not p.is_file():
            errs.append(f"missing {rel}")
        elif _sha(p) != digest:
            errs.append(f"hash mismatch {rel}")
    errs += [f"must not exist: {rel}" for rel in e.get("must_not_exist", []) if (repo / rel).exists()]
    src = repo / e["delivery"]["src"]
    errs += [f"symlink in vendored tree {f.relative_to(repo)}" for f in src.rglob("*") if f.is_symlink()]
    errs += [f"unlisted file {f.relative_to(repo)}" for f in src.rglob("*")
             if f.is_file() and not f.is_symlink() and str(f.relative_to(repo)) not in e["sha256"]]
    return errs


def deliverable(cfg, provider, repo: Path | None = None) -> bool:
    """Predicate used by capability_policy.worker_deliverable for kind `skill` providers."""
    repo = repo or REPO
    if provider.kind != "skill" or entry(repo, provider.id) is None:
        return True            # ambient / loading-path skills: behaviour unchanged
    return not verify(repo, provider.id)


def skill_name(src: Path) -> str:
    head = (src / "SKILL.md").read_text().split("---")[1]
    name = (yaml.safe_load(head) or {}).get("name", "")
    if not isinstance(name, str) or not name.replace("-", "").replace("_", "").isalnum():
        raise SkillDeliveryError(f"unsafe skill name in {src}/SKILL.md")
    return name


def _clear_link_components(wt: Path, parts) -> None:
    """The worktree is worker-controlled. A symlink on `parts` is removed as a LINK (never its target, never
    followed); a non-directory where a directory is required is refused. Missing components end the walk."""
    cur = wt
    for part in parts:
        cur = cur / part
        if os.path.islink(cur):
            os.unlink(cur)
        elif not os.path.lexists(cur):
            return
        elif not cur.is_dir():
            raise SkillDeliveryError(f"{cur.relative_to(wt)} exists and is not a directory")


def _copy_regular(src: Path, dst: Path) -> bool:
    """Copy `src` to `dst` only if it is a regular file, without following a final symlink and without blocking on
    FIFOs/devices (O_NONBLOCK, fstat check). Returns False when skipped."""
    try:
        fd = os.open(src, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError:
        return False
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            return False
        dst.parent.mkdir(parents=True, exist_ok=True)
        with os.fdopen(fd, "rb", closefd=False) as r, open(dst, "wb") as w:
            shutil.copyfileobj(r, w)
        return True
    finally:
        os.close(fd)


def provision(repo: Path | None, wt: Path, skill_id: str) -> dict:
    """Verify, then copy the locked tree into the worktree. Never touches git config or any path outside `wt`."""
    repo = repo or REPO
    errs = verify(repo, skill_id)
    if errs:
        raise SkillDeliveryError(f"{skill_id} failed verification: {'; '.join(errs[:3])}")
    e = entry(repo, skill_id)
    src = repo / e["delivery"]["src"]
    try:
        wt = Path(os.path.realpath(wt))
        name = skill_name(src)
        _clear_link_components(wt, (".claude", "skills", name))
        dest = wt / ".claude" / "skills" / name
        if dest.is_dir():
            shutil.rmtree(dest)
        for rel in e["delivery"].get("worktree_ignore", []):      # stale working files from an earlier attempt
            _clear_link_components(wt, Path(rel).parts)
            if (wt / rel).is_dir():
                shutil.rmtree(wt / rel, ignore_errors=True)
        shutil.copytree(src, dest, symlinks=True)
        if not os.path.realpath(dest).startswith(str(wt) + os.sep):
            raise SkillDeliveryError(f"{skill_id}: destination escapes the worktree")
        root = e["delivery"]["src"].rstrip("/") + "/"
        for rel, digest in e["sha256"].items():
            if _sha(dest / rel[len(root):]) != digest:
                shutil.rmtree(dest, ignore_errors=True)
                raise SkillDeliveryError(f"{skill_id}: copy differs from lock at {rel}")
    except OSError as exc:
        raise SkillDeliveryError(f"{skill_id}: could not provision ({type(exc).__name__})") from exc
    return {"skill": skill_id, "name": name, "dest": str(dest), "files": len(e["sha256"]), "verified": True,
            "commit": e["commit"]}


def instruction(deliveries: list[dict]) -> str:
    lines = [f"Use the `{d['name']}` skill (installed in this project) for the design direction of this task; "
             "do not use it for non-UI work." for d in deliveries]
    return "\n".join(lines) + "\n\n" if lines else ""


def finish(wt: Path, delivery: dict, evidence_dir: Path, repo: Path | None = None) -> dict:
    """After the worker returns (any outcome): persist the skill's working files as evidence under `evidence_dir`
    (task state, outside the worktree), then remove the skill copy and those files from the worktree so they can
    never be committed. Runs in the host dispatcher over a WORKER-CONTROLLED directory, so it never follows a
    symlink, copies only regular files, skips FIFOs/devices, and caps count and size. Filesystem-only evidence of
    what the skill's scripts left behind, not proof of quality."""
    wt = Path(os.path.realpath(wt))
    e = entry(repo, delivery["skill"]) or {}
    artifacts, skipped = [], []
    for rel in e.get("delivery", {}).get("worktree_ignore", []):
        base = wt / rel
        if os.path.islink(base):                       # planted link: drop the link only
            os.unlink(base)
            skipped.append({"path": rel.rstrip("/"), "reason": "symlink"})
            continue
        if base.is_dir():
            for root, dirs, files in os.walk(base, followlinks=False):
                for d in [d for d in dirs if os.path.islink(os.path.join(root, d))]:
                    skipped.append({"path": str((Path(root) / d).relative_to(wt)), "reason": "symlink"})
                dirs[:] = [d for d in dirs if not os.path.islink(os.path.join(root, d))]
                for fn in sorted(files):
                    f = Path(root) / fn
                    try:
                        st = os.lstat(f)
                    except OSError:
                        continue
                    relp = str(f.relative_to(wt))
                    if not stat.S_ISREG(st.st_mode):
                        skipped.append({"path": relp, "reason": "not a regular file"})
                    elif st.st_size > MAX_EVIDENCE_FILE_BYTES or len(artifacts) >= MAX_EVIDENCE_FILES:
                        skipped.append({"path": relp, "reason": "size or count cap"})
                    else:
                        out = evidence_dir / relp
                        if _copy_regular(f, out):
                            artifacts.append({"path": relp, "bytes": st.st_size, "sha256": _sha(out)})
                        else:
                            skipped.append({"path": relp, "reason": "not copied"})
            shutil.rmtree(base, ignore_errors=True)
    _clear_link_components(wt, (".claude", "skills", delivery["name"]))
    skill_dir = wt / ".claude" / "skills" / delivery["name"]
    if skill_dir.is_dir():
        shutil.rmtree(skill_dir, ignore_errors=True)
    for parent in (wt / ".claude" / "skills", wt / ".claude"):        # leave no empty scaffolding behind
        if not os.path.islink(parent):
            try:
                parent.rmdir()
            except OSError:
                pass
    return {**{k: delivery[k] for k in ("skill", "name", "commit", "files", "verified")},
            "evidence_dir": str(evidence_dir), "artifacts": artifacts, "skipped": skipped}
