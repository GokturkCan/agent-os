"""Read-only project identity derived from canonical wiki notes, never a second registry."""
from __future__ import annotations

import hashlib
import re
import unicodedata
from pathlib import Path

import yaml


def sha(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def frontmatter(text: str) -> dict:
    text=text.replace("\r\n","\n")
    if not text.startswith("---\n"):
        return {}
    parts = text.split("\n---", 1)
    if len(parts) != 2:
        return {}
    value = yaml.safe_load(parts[0][4:])
    return value if isinstance(value, dict) else {}


def key(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def project_id(name: str) -> str:
    return "prj-" + hashlib.sha256(key(name).encode()).hexdigest()[:20]


class Projects:
    def __init__(self, root: Path):
        self.root = root.resolve()

    def pages(self):
        wiki = self.root / "wiki"
        for path in sorted(wiki.rglob("*.md")):
            # Symlinked files/directories must never expand the readable vault boundary.
            if any(p.is_symlink() for p in [path, *path.parents] if p != self.root.parent):
                continue
            if not path.resolve().is_relative_to(wiki) or path.stat().st_size > 512_000:
                continue
            try:
                text = path.read_bytes().decode("utf-8")
                fm = frontmatter(text)
            except (OSError, UnicodeError, yaml.YAMLError):
                continue
            yield path.relative_to(self.root).as_posix(), fm, text

    def list(self) -> list[dict]:
        out = []
        for rel, fm, text in self.pages():
            if not (rel.startswith("wiki/projects/") or fm.get("entity_kind") == "project"
                    or fm.get("type") == "project"):
                continue
            name = str(fm.get("canonical_name") or fm.get("title") or Path(rel).stem)
            pid = str(fm.get("project_id") or fm.get("source_id") or project_id(rel))
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}", pid):
                continue
            def strings(field):
                value = fm.get(field, [])
                return [str(x) for x in value] if isinstance(value, list) else []
            out.append(dict(id=pid, name=name, aliases=strings("aliases"), scope=str(fm.get("scope", "")),
                            status=str(fm.get("status", "unknown")), repositories=strings("repositories"),
                            paths=strings("paths"), references=strings("references"),
                            research_questions=strings("research_questions"), decisions=strings("decisions"),
                            experiments=strings("experiments"), open_questions=strings("open_questions"),
                            provenance={"path": rel, "sha256": hashlib.sha256(text.encode()).hexdigest(),
                                        "source_id": fm.get("source_id")}))
        return out

    def resolve(self, query: str) -> dict:
        matches = [p for p in self.list() if key(query) in
                   {key(x) for x in [p["id"], p["name"], *p["aliases"], *p["repositories"], *p["paths"]]}]
        if len(matches) == 1:
            return {"status": "matched", "project": matches[0], "candidates": []}
        return {"status": "ambiguous" if matches else "missing", "project": None,
                "candidates": [{"id": p["id"], "name": p["name"], "path": p["provenance"]["path"]}
                               for p in matches]}
