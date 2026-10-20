"""Retrieval selection with source attribution and citation verification (R3.5). OFFLINE, deterministic first, OPT-IN.

Selects which candidate passages to put in front of a model and checks that anything the model then cites really exists.

  query + candidate pack -> lexical selection (BM25 over the pack only, EN/TR folding) -> top-k with source id, path, sha256
  optional neural re-order: SystemOne `choose` over the lexical top-N ONLY (it can re-rank, never add a passage or a source;
                            any escalation / error / ineligible answer keeps the lexical order)
  answer citations -> verify_citations(): a citation is SUPPORTED only if its source id is in the selected pack AND its quote is
                      a verbatim (whitespace/case-insensitive) substring of that source. Unknown source, source outside the pack,
                      or a quote the source does not contain is REJECTED with a reason - a fabricated citation is never accepted.

Nothing here reads SecondBrain itself (callers pass candidates), writes anything, calls an API or loads an embedding model.
Embedding selection is deliberately not implemented: no embedding model is installed and none may be downloaded here.
"""
from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field

from . import systemone as S

PROMPT = "Which passage best answers the query? Choose its id."
_TR = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")
STOP = frozenset("the a an of to for and or on in is are was were be do does did what which who how when where why with from by at as it this that "
                 "bir ve ile için bu şu da de mi mı mu mü ne nasıl hangi kim nerede neden".split())


def fold(text: str) -> str:
    return unicodedata.normalize("NFKD", text.translate(_TR)).encode("ascii", "ignore").decode().lower()


def terms(text: str) -> list[str]:
    out = []
    for w in re.findall(r"[a-z0-9]+", fold(text)):
        if w in STOP or len(w) < 2:
            continue
        out.append(w[:5] if len(w) > 5 else w)             # crude stem: shared 5-char prefix (works for EN suffixes and TR agglutination)
    return out


@dataclass(frozen=True)
class Candidate:
    source_id: str
    text: str
    path: str = ""

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.text.encode()).hexdigest()


@dataclass(frozen=True)
class Selected:
    source_id: str
    path: str
    sha256: str
    score: float
    rank: int
    how: str = "lexical"


def bm25(query: str, pool: list[Candidate], k1: float = 1.5, b: float = 0.75) -> list[tuple[float, Candidate]]:
    docs = [Counter(terms(c.text)) for c in pool]
    n = len(pool)
    avg = (sum(sum(d.values()) for d in docs) / n) if n else 0.0
    df = Counter(t for d in docs for t in d)
    q = Counter(terms(query))
    scored = []
    for c, d in zip(pool, docs):
        ln = sum(d.values()) or 1
        s = 0.0
        for t in q:
            if t in d:
                idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
                s += idf * d[t] * (k1 + 1) / (d[t] + k1 * (1 - b + b * ln / (avg or 1)))
        scored.append((round(s, 6), c))
    # stable, deterministic tie-break: score desc, then source id
    return sorted(scored, key=lambda x: (-x[0], x[1].source_id))


def select(query: str, pool: list[Candidate], k: int = 3, *, backend=None, rerank_top: int = 4) -> list[Selected]:
    ids = [c.source_id for c in pool]
    if len(set(ids)) != len(ids):
        raise ValueError("candidate source ids must be unique")
    ranked = [(s, c) for s, c in bm25(query, pool) if s > 0]       # zero overlap is never "relevant"
    how = "lexical"
    if backend is not None and len(ranked) > 1:
        head = ranked[:rerank_top]
        choice = _ask(backend, query, head)
        if choice is not None:
            head = sorted(head, key=lambda x: x[1].source_id != choice)      # chosen first, others keep lexical order
            ranked = head + ranked[rerank_top:]
            how = "neural-rerank"
    return [Selected(c.source_id, c.path, c.sha256, s, i + 1, how) for i, (s, c) in enumerate(ranked[:k])]


def _ask(backend, query: str, head: list[tuple[float, Candidate]]) -> str | None:
    options = tuple(c.source_id for _, c in head)
    # the passage heads travel as bounded state (the adapter redacts and truncates every value)
    req = S.SystemOneRequest(task_type="retrieval_selection", eligible_options=options,
                             questions=(S.Question("passage", "choose", PROMPT),),
                             state={"query": query[:200], **{f"p:{c.source_id}": c.text[:160] for _, c in head}})
    resp = S.system_one(req, backend)
    if resp.escalate:
        return None
    a = resp.answer("passage")
    return a.choice if a is not None and a.choice in options else None


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


@dataclass(frozen=True)
class CitationVerdict:
    source_id: str
    quote: str
    supported: bool
    reason: str                    # supported | unknown_source | source_not_selected | quote_not_in_source | empty_quote


def verify_citations(citations: list[dict], pool: list[Candidate], selected: list[Selected] | None = None) -> list[CitationVerdict]:
    """Each citation: {"source_id", "quote"}. Supported only if the source is in the pool (and in `selected` when given)
    and the quote is a verbatim substring of it. Never raises on model-shaped garbage: it is rejected."""
    by_id = {c.source_id: c for c in pool}
    allowed = {s.source_id for s in selected} if selected is not None else set(by_id)
    out = []
    for ci in citations if isinstance(citations, list) else []:
        sid = ci.get("source_id") if isinstance(ci, dict) else None
        quote = ci.get("quote") if isinstance(ci, dict) else None
        sid_s, quote_s = (sid if isinstance(sid, str) else ""), (quote if isinstance(quote, str) else "")
        if sid_s not in by_id:
            reason = "unknown_source"
        elif sid_s not in allowed:
            reason = "source_not_selected"
        elif not quote_s.strip():
            reason = "empty_quote"
        elif _norm(quote_s) not in _norm(by_id[sid_s].text):
            reason = "quote_not_in_source"
        else:
            reason = "supported"
        out.append(CitationVerdict(sid_s, quote_s[:200], reason == "supported", reason))
    return out
