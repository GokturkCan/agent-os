"""Opt-in tool-result pruner prototype (R3.2G). Deterministic first; the SystemOne backend only where judgment adds value.

Pattern from tamaratran/jev-pruner (small output passes untouched; errors and structured output protected; chunked; a chunk
stays if any line is needed), adapted: no hook, no global install, the ORIGINAL output is always stored (content-addressed,
via contextgate.Store) and the pruned view names its sha256 for exact recovery.

  output -> below `min_tokens`, or structured as a whole (JSON/YAML/XML/diff)  -> unchanged
         -> deterministic: strip ANSI, drop progress-bar / spinner lines, collapse runs of near-identical lines
         -> protected lines (errors, warnings, failures, paths, exit codes, summaries, CLI lines) + 2 lines of context
         -> the first and last unprotected chunk are always kept (outputs start with context and end with outcomes)
         -> other unprotected chunks: SystemOne keep/drop when a backend is given (any escalation keeps the chunk);
            without a backend they are dropped with a marker
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import systemone as S
from .contextgate import Store, is_structured, tokens, protected_lines

KEEP_CHUNK, DROP_CHUNK = "keep_chunk", "drop_chunk"
PROMPT = "Does any line in this chunk of tool output still need to be available for the current goal?"
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
PROGRESS = re.compile(r"(\d{1,3}(\.\d+)?%|\[[#=>\-. ]{5,}\]|[⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏]|\b\d+(\.\d+)?\s?[kMG]?B/s\b|^\s*(Downloading|Fetching|Resolving|Receiving objects|Compressing objects)\b)", re.I)
PROTECT = re.compile(
    r"\b(error|errors|exception|traceback|fatal|fail(ed|ure|ing)?|warn(ing)?|denied|refused|panic|assert(ion)?|"
    r"passed|skipped|summary|total|exit (code|status))\b|\bE[0-9]{3,5}\b|"
    r"(^|\s)(/|~/|\./)[\w.@%+-]+(/[\w.@%+-]+)+|\b[\w.-]+\.(py|ts|js|go|rs|java|yaml|yml|json|toml|sh|c|cpp|h):\d+|"
    r"^\s*(\$|>)\s+\S|^\s+File \".*\", line \d+|hata|başarısız|uyarı", re.I)
CHUNK = 40
CONTEXT = 2


@dataclass
class Pruned:
    view: str
    sha256: str
    stats: dict = field(default_factory=dict)


def _protected(line: str) -> bool:
    return bool(PROTECT.search(line) or protected_lines(line))


def _norm(line: str) -> str:
    return re.sub(r"\d+", "#", line.strip())


def prune(output: str, store: Store, *, goal: str = "", backend=None, min_tokens: int = 1500) -> Pruned:
    sha = store.put(output)
    before = tokens(output)
    if before < min_tokens or is_structured(output):
        return Pruned(output, sha, {"tokens_before": before, "tokens_after": before, "reduction": 0.0,
                                    "path": "passthrough", "model_calls": 0})
    lines = [ANSI.sub("", l).rstrip() for l in output.replace("\r\n", "\n").split("\n")]
    # progress/spinner lines and carriage-return redraws are noise unless they carry a protected token
    lines = [part for l in lines for part in (l.split("\r") if _protected(l) else [l.split("\r")[-1]])]
    lines = [l for l in lines if not (PROGRESS.search(l) and not _protected(l))]
    collapsed, i = [], 0
    while i < len(lines):                                 # runs of >= 4 near-identical unprotected lines
        j = i
        while j + 1 < len(lines) and _norm(lines[j + 1]) == _norm(lines[i]) and not _protected(lines[j + 1]):
            j += 1
        if j - i >= 3 and not _protected(lines[i]):
            collapsed += [lines[i], f"[toolpruner: {j - i} similar lines collapsed]"]
        else:
            collapsed += lines[i:j + 1]
        i = j + 1
    lines = collapsed
    keep = set()
    for k, l in enumerate(lines):
        if _protected(l):
            keep.update(range(max(0, k - CONTEXT), min(len(lines), k + CONTEXT + 1)))
    chunks, cur = [], []
    for k in range(len(lines)):
        if k in keep:
            if cur:
                chunks.append(cur)
                cur = []
        else:
            cur.append(k)
    if cur:
        chunks.append(cur)
    drop, calls = set(), 0
    for ci, ch in enumerate(chunks):
        for start in range(0, len(ch), CHUNK):
            part = ch[start:start + CHUNK]
            edge = (ci == 0 and start == 0) or (ci == len(chunks) - 1 and start + CHUNK >= len(ch))
            if backend is not None and not edge:            # head and tail chunks are pinned: outputs end with outcomes
                calls += 1
                req = S.SystemOneRequest(task_type="tool_output_pruning", eligible_options=(KEEP_CHUNK, DROP_CHUNK),
                                         questions=(S.Question("chunk", "choose", PROMPT),),
                                         state={"current_goal": goal, "chunk_head": "\n".join(lines[x] for x in part)[:600]})
                resp = S.system_one(req, backend)
                if not resp.escalate and resp.answer("chunk").choice == DROP_CHUNK:
                    drop.update(part)
            elif backend is None and not edge:
                drop.update(part)
    out, k = [], 0
    while k < len(lines):
        if k in drop:
            j = k
            while j + 1 < len(lines) and j + 1 in drop:
                j += 1
            out.append(f"[toolpruner: {j - k + 1} lines omitted; original sha256={sha}]")
            k = j + 1
        else:
            out.append(lines[k])
            k += 1
    view = "\n".join(out)
    if view != output:
        view += f"\n[toolpruner: original sha256={sha}]"
    after = tokens(view)
    return Pruned(view, sha, {"tokens_before": before, "tokens_after": after, "reduction": round(1 - after / before, 4),
                              "path": "model" if backend is not None else "deterministic", "model_calls": calls})
