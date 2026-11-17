"""Read-only repository inspection and reviewable project onboarding proposals."""
from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path

from .knowledge_lifecycle import Lifecycle, safe_text
from .projects import Projects, key, project_id

INSTRUCTION_NAMES = frozenset(
    {"AGENTS.md", "CLAUDE.md", ".cursorrules", "CONTRIBUTING.md"}
)
KNOWLEDGE_HINTS = re.compile(
    r"(?i)(?:readme|roadmap|architecture|decision|handoff|spec|design|research|experiment|notes)"
)
PRIORITY_DOCS = re.compile(
    r"(?i)(?:^docs/(?:current-)?architecture\.md$|docs/roadmap\.md$|docs/knowledge-lifecycle(?:-handoff)?\.md$|docs/project-workflow\.md$)"
)
REJECTED_NAME = re.compile(r"(?i)^rejected")
CACHE_NAME = re.compile(r"(?i)cache")
MD_GLOB = "**/*.md"
SKIP_PREFIXES = (
    ".git/",
    ".pytest_cache/",
    ".remember/",
    "node_modules/",
    ".venv/",
    "dist/",
    "build/",
    "__pycache__/",
    ".cursor/",
)
MAX_FILES = 32
MAX_FILE_BYTES = 256_000
MAX_EXCERPT = 1200
MAX_TOTAL_EXCERPT = 24_000
SCOPE_CAPTURE_LIMIT = 1000
SCOPE_SOURCE_PARTS = 6
SCOPE_SOURCE_CHARS = 320
MAX_ONBOARD_EVIDENCE = 8
AUTHORIZATION_KIND = "agentos:knowledge:onboard:authorized"
PRIORITY_SOURCE_PATHS = (
    "README.md",
    "CLAUDE.md",
    "docs/current-architecture.md",
    "docs/roadmap.md",
    "docs/knowledge-lifecycle-handoff.md",
    "docs/knowledge-lifecycle.md",
    "docs/project-workflow.md",
)
ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}")


def _sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(repo: Path, *args: str, check: bool = True) -> str:
    r = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if check and r.returncode != 0:
        raise ValueError(f"git {' '.join(args)} failed")
    return (r.stdout or r.stderr or "").strip()


def _safe_repo(path: str | Path) -> Path:
    repo = Path(path).expanduser().resolve()
    if any(p.is_symlink() for p in [repo, *list(repo.parents)[:12]] if p != repo.anchor):
        raise ValueError("repository symlink path refused")
    if not repo.is_dir():
        raise ValueError("repository path missing")
    if _git(repo, "rev-parse", "--is-inside-work-tree", check=False) != "true":
        raise ValueError("not a git repository")
    real = repo.resolve()
    if any(p.is_symlink() for p in real.parents):
        raise ValueError("repository parent symlink refused")
    return real


def _classify(rel: str) -> str:
    name = Path(rel).name
    if name in INSTRUCTION_NAMES:
        return "instruction"
    if KNOWLEDGE_HINTS.search(rel):
        return "knowledge"
    return "reference"


def _excerpt(text: str) -> str:
    text = text.replace("\r\n", "\n").strip()
    if len(text) <= MAX_EXCERPT:
        return text
    return text[: MAX_EXCERPT - 3] + "..."


def _excluded_markdown(rel: str) -> bool:
    if any(rel.startswith(prefix) for prefix in SKIP_PREFIXES):
        return True
    name = Path(rel).name
    if REJECTED_NAME.match(name) or CACHE_NAME.search(name):
        return True
    if any(part in {"tmp", "temp", "cache"} for part in Path(rel).parts):
        return True
    return False


def _onboarding_source_rank(rel: str) -> tuple[int, str]:
    if rel == "README.md":
        return (0, rel)
    if rel in INSTRUCTION_NAMES:
        return (1, rel)
    if rel in PRIORITY_SOURCE_PATHS[2:]:
        return (2, rel)
    if PRIORITY_DOCS.match(rel):
        return (2, rel)
    if rel.startswith("docs/") and KNOWLEDGE_HINTS.search(rel):
        return (3, rel)
    if KNOWLEDGE_HINTS.search(rel):
        return (4, rel)
    if rel.startswith("docs/"):
        return (5, rel)
    if rel in {"CHANGELOG.md", "CURRENT_STATE.md", "SECURITY.md"}:
        return (6, rel)
    if rel.startswith("audit/"):
        return (7, rel)
    return (8, rel)


def _rank_onboarding_sources(sources: list[dict]) -> list[dict]:
    eligible = [s for s in sources if not _excluded_markdown(s.get("path", ""))]
    return sorted(eligible, key=lambda s: _onboarding_source_rank(s["path"]))


def _append_source(repo: Path, sources: list[dict], rel: str) -> None:
    if _excluded_markdown(rel) or any(s["path"] == rel for s in sources):
        return
    path = repo / rel
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
        return
    text = path.read_text(encoding="utf-8", errors="replace")
    sources.append(
        {
            "path": rel,
            "sha256": _sha_file(path),
            "bytes": path.stat().st_size,
            "classification": _classify(rel),
            "title": _title_from_md(text, Path(rel).stem),
            "excerpt": _excerpt(text),
            "provenance": "VERIFIED FROM GIT",
        }
    )


def _ensure_priority_sources(repo: Path, sources: list[dict]) -> list[dict]:
    for rel in PRIORITY_SOURCE_PATHS:
        _append_source(repo, sources, rel)
    return sources


def _truncate_at_sentence(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    chunk = text[:limit]
    for sep in (". ", ".\n", "? ", "! "):
        pos = chunk.rfind(sep)
        if pos >= max(80, limit // 3):
            return chunk[: pos + 1].strip()
    return chunk.rstrip() + "..."


def _scope_paragraph(text: str, limit: int = SCOPE_SOURCE_CHARS) -> str:
    lines = text.replace("\r\n", "\n").strip().split("\n")
    block: list[str] = []
    started = False
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if started and block:
                break
            continue
        if stripped.startswith("#"):
            if block:
                break
            started = True
            continue
        started = True
        block.append(stripped)
        if len(" ".join(block)) >= limit:
            break
    if not block:
        return ""
    return _truncate_at_sentence(" ".join(block), limit)


def _compose_scope(inspection: dict, name: str, limit: int = SCOPE_CAPTURE_LIMIT) -> str:
    chunks: list[str] = []
    used = 0
    for source in _rank_onboarding_sources(inspection.get("sources", []))[:SCOPE_SOURCE_PARTS]:
        paragraph = _scope_paragraph(source.get("excerpt") or "")
        if not paragraph:
            continue
        block = f"{paragraph} (from `{source['path']}`)"
        sep = 2 if chunks else 0
        if used + sep + len(block) > limit:
            break
        chunks.append(block)
        used += sep + len(block)
    if not chunks:
        return f"Repository onboarding for {name}."
    return "\n\n".join(chunks)


def _onboarding_evidence(inspection: dict, repo: str) -> list[dict]:
    evidence = []
    ranked = _rank_onboarding_sources(inspection.get("sources", []))
    priority = {p for p in PRIORITY_SOURCE_PATHS}
    chosen: list[dict] = []
    for source in ranked:
        if source["path"] in priority:
            chosen.append(source)
    for source in ranked:
        if source not in chosen:
            chosen.append(source)
        if len(chosen) >= MAX_ONBOARD_EVIDENCE:
            break
    for source in chosen[:MAX_ONBOARD_EVIDENCE]:
        if not (source.get("excerpt") or "").strip() and source.get("bytes", 0) == 0:
            continue
        evidence.append(
            {
                "kind": "artifact",
                "locator": str(Path(repo) / source["path"]),
                "sha256": source["sha256"],
            }
        )
    return evidence


def _bounded_join(parts: list[str], limit: int) -> str:
    chunks: list[str] = []
    used = 0
    for part in parts:
        text = part.strip()
        if not text:
            continue
        sep = 1 if chunks else 0
        if used + sep + len(text) <= limit:
            chunks.append(text)
            used += sep + len(text)
            continue
        room = limit - used - sep - 3
        if room >= 80:
            chunks.append(text[:room] + "...")
        break
    return "\n".join(chunks)


def _primary_readme(sources: list[dict]) -> dict | None:
    readmes = [s for s in sources if Path(s["path"]).name.lower() == "readme.md"]
    root = next((s for s in readmes if s["path"] == "README.md"), None)
    if root:
        return root
    preferred = [s for s in readmes if not any(s["path"].startswith(p) for p in SKIP_PREFIXES)]
    return preferred[0] if preferred else (readmes[0] if readmes else None)


def _title_from_md(text: str, fallback: str) -> str:
    for line in text.splitlines()[:40]:
        m = re.match(r"^#\s+(.+)", line.strip())
        if m:
            return safe_text(m.group(1).strip(), 120)
    return safe_text(fallback, 120)


def inspect_repository(path: str | Path, *, projects: Projects | None = None) -> dict:
    repo = _safe_repo(path)
    head = None
    dirty = None
    try:
        head = _git(repo, "rev-parse", "HEAD")
    except ValueError:
        head = None
    try:
        dirty = bool(_git(repo, "status", "--porcelain"))
    except ValueError:
        dirty = None
    sources = []
    total = 0
    for candidate in sorted(repo.glob(MD_GLOB)):
        if len(sources) >= MAX_FILES:
            break
        if candidate.is_symlink() or any(p.is_symlink() for p in [candidate, *candidate.parents] if p != repo.parent):
            raise ValueError("repository symlink path refused")
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if not resolved.is_relative_to(repo):
            continue
        if not resolved.is_file() or resolved.stat().st_size > MAX_FILE_BYTES:
            continue
        rel = resolved.relative_to(repo).as_posix()
        if rel.startswith(".git/") or _excluded_markdown(rel):
            continue
        try:
            text = resolved.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        excerpt = _excerpt(text)
        total += len(excerpt)
        if total > MAX_TOTAL_EXCERPT:
            break
        sources.append(
            {
                "path": rel,
                "sha256": _sha_file(resolved),
                "bytes": resolved.stat().st_size,
                "classification": _classify(rel),
                "title": _title_from_md(text, Path(rel).stem),
                "excerpt": excerpt,
                "provenance": "VERIFIED FROM GIT",
            }
        )
    sources = _ensure_priority_sources(repo, sources)
    readme = _primary_readme(sources)
    title = readme["title"] if readme else repo.name
    if readme and "pytest cache" in title.lower():
        title = repo.name
    name = safe_text(title, 80)
    pid = project_id(name)
    identity = {"id": pid, "name": name, "repository": str(repo)}
    match = {"status": "missing", "candidates": []}
    if projects:
        match = projects.resolve(name)
        if match["status"] != "matched":
            aliases = {key(x["name"]) for x in match.get("candidates", [])}
            if key(name) in aliases or any(key(name) == key(a) for c in match.get("candidates", []) for a in [c.get("name", "")]):
                match = {**match, "status": "ambiguous"}
    related = []
    if projects:
        for q in sources[:6]:
            hits = projects.resolve(q["title"])
            if hits["status"] == "matched":
                related.append(
                    {"query": q["title"], "project_id": hits["project"]["id"], "path": hits["project"]["provenance"]["path"]}
                )
    return {
        "schema": "agentos.project-inspection.v1",
        "repository": str(repo),
        "git": {
            "head": head,
            "dirty": dirty,
            "provenance": "VERIFIED FROM GIT" if head else "UNKNOWN",
        },
        "identity_candidate": identity,
        "canonical_match": match,
        "sources": sources,
        "instructions": [s for s in sources if s["classification"] == "instruction"],
        "knowledge_documents": [s for s in sources if s["classification"] != "instruction"],
        "related_secondbrain": related,
        "warnings": ([] if head else ["missing git commit history"])
        + (["uncommitted changes present"] if dirty else [])
        + (["ambiguous or existing project name"] if match.get("status") == "ambiguous" else []),
    }


def onboarding_capture_payload(
    inspection: dict,
    *,
    aliases: list | None = None,
    scope: str | None = None,
    authorization_locator: str | None = None,
) -> dict:
    repo = inspection["repository"]
    name = inspection["identity_candidate"]["name"]
    if scope:
        scope_text = safe_text(scope, SCOPE_CAPTURE_LIMIT)
    else:
        scope_text = safe_text(_compose_scope(inspection, name), SCOPE_CAPTURE_LIMIT)
    evidence = []
    if authorization_locator:
        evidence.append({"kind": "user_statement", "locator": authorization_locator})
    evidence.extend(_onboarding_evidence(inspection, repo))
    if not evidence or not any(item.get("kind") == "artifact" for item in evidence):
        raise ValueError("no Markdown sources to ground onboarding")
    return {
        "authorized": True,
        "kind": "project",
        "project": None,
        "summary": safe_text(f"Onboard project {name} from repository documentation.", 500),
        "evidence": evidence,
        "origin": {"actor": "hermes", "kind": "repository_onboarding", "locator": repo},
        "confidence": "uncertain",
        "project_spec": {
            "name": name,
            "scope": scope_text,
            "aliases": aliases or [],
            "status": "seed",
            "repositories": [repo],
            "paths": [],
        },
    }


def propose_onboarding(life: Lifecycle, path: str | Path, *, authorized: bool = False, **kw) -> dict:
    if authorized is not True:
        raise ValueError("explicit --authorized required to stage onboarding proposal")
    inspection = inspect_repository(path, projects=life.projects)
    match = inspection["canonical_match"]
    if match.get("status") == "matched":
        raise ValueError("project already registered in canonical notes")
    repo = inspection["repository"]
    auth_locator = f"{AUTHORIZATION_KIND}:{repo}"
    payload = onboarding_capture_payload(inspection, authorization_locator=auth_locator, **kw)
    proposal = life.capture(**payload)
    return {"inspection": inspection, "proposal": proposal}
