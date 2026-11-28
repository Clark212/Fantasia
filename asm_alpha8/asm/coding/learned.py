"""DEV16 learned candidate ranking for the repair workflow.

DEV15's real-bug runs hit the 150 s budget on 34 of 83 bugs: the right edit was often in ASM's repair space but too far
down a fixed, hand-ordered candidate list. A `CandidateRanker` reorders candidates by a model's estimate of
P(this candidate is the fix | features), learned from VERIFIED (buggy, fixed) pairs.

Design constraints, all enforced here:
- Opt-in: `RepairWorkflow(ranker=None)` (the default) is DEV15 exactly. The pre-registered DEV16 study decides whether a
  ranker may become the default.
- Phases are kept: the ranker reorders WITHIN a phase (DEV14 templates, then DEV15 families); it never moves a phase-2
  candidate ahead of phase 1, so a DEV14-repairable fault keeps its DEV14 search space first.
- Ranking changes only the ORDER of candidates. Acceptance still requires the tests, the contract, and verification.
- A ranker refuses to load a model file whose seal does not verify (`LearnedModel.load`).
"""
from __future__ import annotations

from pathlib import Path

from ..learning.engine import LearnedModel


def candidate_features(meta: dict, ctx: dict) -> dict:
    """Features of one candidate. `meta` comes from faultloc._meta; `ctx` describes the suspect and the search."""
    kind, fam = meta.get("kind", "?"), meta.get("family", "?")
    f = {"family": fam, "kind": kind, "edit": f"{kind}:{meta.get('original', '')}->{meta.get('option', '')}"[:60],
         "kind_option": f"{kind}->{meta.get('option', '')}"[:40],
         "line_score": meta.get("line_score", 0.0), "line_rank": min(meta.get("line_rank", 99), 20),
         "top_line": meta.get("line_rank", 99) == 1, "suspect_rank": ctx.get("suspect_rank", 0),
         "suspect_score": ctx.get("suspect_score", 0.0), "phase": ctx.get("phase", 1),
         "position_fraction": round(ctx.get("position", 0) / max(1, ctx.get("n_candidates", 1)), 4)}
    if fam == "pair":
        f["pair_same_line"] = bool(meta.get("same_line"))
        f["line_score2"] = meta.get("line_score2", 0.0)
    if meta.get("line") in ctx.get("traceback_lines", ()):
        f["on_traceback_line"] = True
    for e in ctx.get("exceptions", ())[:3]:
        f[f"exc={e}"] = True
        if fam == "try_except" and e in meta.get("option", ""):
            f["catches_raised_exception"] = True
    return f


class CandidateRanker:
    def __init__(self, model: LearnedModel):
        self.model = model

    @classmethod
    def load(cls, path: str | Path) -> "CandidateRanker":
        return cls(LearnedModel.load(path))

    @property
    def provenance(self) -> dict:
        prov = getattr(self.model, "provenance", {}) or {}
        return {"name": getattr(self.model, "name", type(self.model).__name__),
                **{k: prov.get(k) for k in ("dataset_sha256", "rows", "groups", "kind")}}

    def rerank(self, cands: list, ctx: dict) -> list:
        """Stable reorder by descending score; candidates without metadata keep their place after scored ones."""
        n = len(cands)
        scored = []
        for i, c in enumerate(cands):
            meta = getattr(c, "meta", None)
            s = self.model.score(candidate_features(meta, dict(ctx, position=i, n_candidates=n))) if meta else float("-inf")
            scored.append((-s, i, c))
        scored.sort(key=lambda t: (t[0], t[1]))
        return [c for _, _, c in scored]
