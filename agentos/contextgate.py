"""ContextGate compaction prototype (R3.2G): a DERIVED, verbatim-preserving compact view of a transcript. OPT-IN, OFFLINE.

Pattern from tamaratran/fast-jev-compaction (never rewrite text; only tool results are candidates; KEEP / TRUNCATE / DROP;
recent items pinned), adapted with Agent OS invariants:

* The input is never modified. Every original item text is stored content-addressed (sha256) in a store directory that is
  refused if it lies inside the canonical SecondBrain vault; every truncated or dropped item leaves a marker carrying its
  sha256 so `recover()` returns the exact original.
* User and assistant text, tool calls and the most recent `pin_recent` items are always KEPT verbatim.
* Deterministic protection: lines carrying user constraints, security/approval words, file paths, error messages/codes, exit
  codes, CLI invocations, stack traces, citations/URLs are PROTECTED; a tool result that is structured as a whole
  (JSON/YAML/XML/diff) is KEPT. A protected line always survives verbatim: DROP of such an item becomes TRUNCATE, and
  TRUNCATE keeps the head, every protected line and the last TAIL_LINES lines.
* Only the remaining choice (keep / truncate / drop for an old, unstructured tool result) is asked of the SystemOne backend,
  on a bounded head (<= HEAD_CHARS) of the item; with no backend, or on any escalation, the deterministic default applies
  (KEEP small results, TRUNCATE large ones). A model can therefore shorten context but never delete a protected line.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import systemone as S

KEEP, TRUNCATE, DROP = "keep_verbatim", "truncate_head", "drop_result"
ACTIONS = (KEEP, TRUNCATE, DROP)
HEAD_CHARS = 600
TRUNC_HEAD = 300
TAIL_LINES = 3
SMALL_CHARS = 800
PROMPT = "Does the agent still need this old tool result to continue the task? Keep it, keep only its beginning, or drop it."
SECONDBRAIN = Path(os.path.expanduser("~/SecondBrain")).resolve()

PROTECT = [re.compile(p, re.I) for p in (
    r"\b(error|exception|traceback|fatal|failed|failure|panic|segfault|denied|refused|warn|warning)\b|\b\w+(Error|Exception)\b|"
    r"\bE[0-9]{3,5}\b|exit (code|status) [1-9]",
    r"(^|\s)(/|~/|\./|\.\./)[\w.@%+-]+(/[\w.@%+-]+)+|\b[\w.-]+\.(py|ts|js|tsx|go|rs|java|yaml|yml|json|toml|md|sh|sql|cfg|ini|lock)\b",
    r"^\s*(\$|>|PS>)\s+\S|(^|\s)--?[a-zA-Z][\w-]*(=\S+)?",
    r"^\s+File \".*\", line \d+|^\s+at [\w.$<>]+\(.*\)",
    r"https?://\S+|\bdoi:\S+|\bsource:\s",
    r"\b(approv\w*|permission|credential|secret|password|api[ _-]?key|token|must not|never|do not|don't|required|onay|izin|asla|yapma|zorunlu)\b",
)]
STRUCTURED = (re.compile(r"^\s*[\[{]"), re.compile(r"^(diff --git|--- |\+\+\+ |@@ )", re.M), re.compile(r"^\s*<\?xml|^\s*<\w+[^>]*>"))


def tokens(text: str) -> int:
    return (len(text) + 3) // 4


def protected_lines(text: str) -> list[int]:
    return [i for i, line in enumerate(text.splitlines()) if any(p.search(line) for p in PROTECT)]


def is_structured(text: str) -> bool:
    t = text.strip()
    if not t:
        return False
    if t[0] in "[{":
        try:
            json.loads(t)
            return True
        except ValueError:
            pass
    if STRUCTURED[1].search(t) or STRUCTURED[2].search(t):
        return True
    lines = [l for l in t.splitlines() if l.strip()]
    return len(lines) >= 3 and sum(bool(re.match(r"^\s*[\w.-]+:\s", l) or re.match(r"^\s*- ", l)) for l in lines) / len(lines) > 0.8


@dataclass
class Item:
    id: str
    role: str                 # user | assistant | tool
    kind: str                 # text | tool_call | tool_result
    text: str
    tool: str = ""


@dataclass
class Compaction:
    view: list[dict]
    decisions: list[dict]
    stats: dict = field(default_factory=dict)


class Store:
    """Content-addressed originals. Refuses any location inside the canonical SecondBrain vault."""

    def __init__(self, root: str | os.PathLike):
        self.root = Path(root).resolve()
        if self.root == SECONDBRAIN or SECONDBRAIN in self.root.parents:
            raise ValueError("ContextGate never writes inside the canonical SecondBrain vault")
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, text: str) -> str:
        sha = hashlib.sha256(text.encode()).hexdigest()
        p = self.root / sha
        if not p.exists():
            p.write_bytes(text.encode("utf-8"))
        return sha

    def get(self, sha: str) -> str:
        if not re.fullmatch(r"[0-9a-f]{64}", sha):
            raise ValueError("bad sha")
        raw = (self.root / sha).read_bytes()
        if hashlib.sha256(raw).hexdigest() != sha:
            raise ValueError("stored original failed integrity check")
        return raw.decode("utf-8")


MARKER = re.compile(r"\[contextgate: (truncated|dropped) item (\S+) sha256=([0-9a-f]{64})\]")


def recover(view_text: str, store: Store) -> str:
    m = MARKER.search(view_text)
    return store.get(m.group(3)) if m else view_text


def _truncate(text: str, prot: list[int]) -> str:
    """Head (TRUNC_HEAD chars) + every protected line + the last TAIL_LINES lines (results usually end with their outcome)."""
    lines = text.splitlines()
    head = text[:TRUNC_HEAD]
    head_lines = head.count("\n") + 1
    tail_from = max(head_lines, len(lines) - TAIL_LINES)
    keep = sorted({i for i in prot if head_lines - 1 <= i < tail_from} | set(range(tail_from, len(lines))))
    return head + ("\n" + "\n".join(lines[i] for i in keep) if keep else "")


def _ask(backend, goal: str, item: Item) -> tuple[str | None, str]:
    req = S.SystemOneRequest(task_type="context_compaction", eligible_options=ACTIONS,
                             questions=(S.Question("compact", "choose", PROMPT),),
                             state={"current_goal": goal, "tool": item.tool, "result_head": item.text[:HEAD_CHARS],
                                    "result_chars": len(item.text)})
    resp = S.system_one(req, backend)
    if resp.escalate:
        return None, f"fallback:{resp.reason_code}"
    return resp.answer("compact").choice, "model"


def compact(items: list[Item], store: Store, *, goal: str = "", backend=None, pin_recent: int = 6) -> Compaction:
    view, decisions = [], []
    n = len(items)
    goal = goal or next((it.text for it in reversed(items) if it.role == "user" and it.kind == "text"), "")
    model_calls = 0
    for idx, it in enumerate(items):
        sha = store.put(it.text)
        if it.kind != "tool_result" or idx >= n - pin_recent:
            action, why = KEEP, "pinned" if it.kind == "tool_result" else f"never-compacted:{it.kind}"
        elif is_structured(it.text):
            action, why = KEEP, "structured"
        else:
            prot = protected_lines(it.text)
            default = KEEP if len(it.text) <= SMALL_CHARS else TRUNCATE
            action, why = default, "default"
            if backend is not None and len(it.text) > SMALL_CHARS // 4:
                choice, why = _ask(backend, goal, it)
                model_calls += 1
                action = choice or default
            if action == DROP and prot:
                action, why = TRUNCATE, why + "+protected"
        text = it.text
        if action == TRUNCATE:
            text = _truncate(it.text, protected_lines(it.text)) + f"\n[contextgate: truncated item {it.id} sha256={sha}]"
        elif action == DROP:
            text = f"[contextgate: dropped item {it.id} sha256={sha}]"
        view.append({"id": it.id, "role": it.role, "kind": it.kind, "tool": it.tool, "text": text})
        decisions.append({"id": it.id, "action": action, "why": why, "sha256": sha})
    before = sum(tokens(i.text) for i in items)
    after = sum(tokens(v["text"]) for v in view)
    return Compaction(view, decisions, {"tokens_before": before, "tokens_after": after,
                                        "reduction": round(1 - after / before, 4) if before else 0.0,
                                        "model_calls": model_calls})
