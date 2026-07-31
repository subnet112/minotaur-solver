"""Route selection — the champion's `_score_aware_singlehop` scoring block
(king_base.py:226-345) with the `_dr*` closures removed.

Given the same candidate set this must pick the SAME candidate the lineage
would, or delivered output diverges and the round scores a regression. The
scoring/override/gas helpers live in ``picks``; this module holds the
candidate filters and the ``select`` entry point.
"""
from __future__ import annotations
from cr_picks import pick_best

def _ref(cands: list, base_out: int) -> int:
    """Score denominator: best available output, never below 1."""
    best_out = max((int(c['out']) for c in cands), default=0)
    return max(best_out, int(base_out or 0), 1)

def usable_candidates(cands: list, min_out: int) -> list:
    """Drop candidates that cannot clear min_out (king_base.py:319)."""
    return [c for c in cands if int(min_out or 0) <= 0 or int(c['out']) >= int(min_out)]

def apply_extra_route_penalty(usable: list) -> list:
    """`extra_route` candidates survive only above the 10-bps edge (king_base.py:322)."""
    core = [c for c in usable if not c.get('extra_route')]
    if not core:
        return usable
    core_best = max((int(c['out']) for c in core))
    keep = [c for c in usable if c.get('extra_route') and int(c['out']) * 10000 > core_best * 10010]
    return core + keep

def select(cands: list, min_out: int, base_out: int, tin: str, tout: str, raw_pairs=()) -> dict | None:
    """Full selection pass: usable -> extra-route gate -> best. None if nothing fills."""
    if not cands:
        return None
    usable = usable_candidates(cands, min_out)
    if not usable:
        return None
    usable = apply_extra_route_penalty(usable)
    return pick_best(usable, _ref(cands, base_out), tin, tout, raw_pairs)