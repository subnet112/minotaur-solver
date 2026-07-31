"""Candidate selection — score-optimal pick, raw-output override, and the
gas-aware tie refinement. Split from route_core.py for the AST-region budget.

The primary pick and overrides are ported from the champion's scoring block
(king_base.py:325-335); the gas refinement is our addition (see _gas_refine).
"""
from __future__ import annotations
import cr_consts as consts
GAS_TIE_BAND_BPS = 1

def _score(out: int, gas: int, ref: int) -> float:
    """score = 0.4*(out/ref) - gas_weight*(gas/1e6) (king_base.py:314).

    gas_weight ships 0.0, so this is pure out/ref; kept because the lineage
    reads the same env var and we must move with it if it ever arms.
    """
    weight = consts.gas_model()['gas_weight']
    return 0.4 * (int(out) / ref) - weight * (int(gas) / 1000000.0)

def _score_optimal(usable: list, ref: int) -> dict:
    """max by (round(score, 9), -gas_est) — the lineage's primary pick."""
    return max(usable, key=lambda c: (round(_score(c['out'], c['gas_model'], ref), 9), -int(c['gas_est'])))

def _raw_override(usable: list, best: dict) -> dict:
    """For _RAW_OUTPUT_PAIRS, prefer sheer output past the 4-bps edge (king_base.py:331)."""
    edge = consts.gas_model()['raw_output_edge_bps']
    raw_best = max(usable, key=lambda c: (int(c['out']), -int(c['gas_est'])))
    if int(raw_best['out']) * 10000 > int(best['out']) * (10000 + edge):
        return raw_best
    return best

def _gas_refine(usable: list, best: dict) -> dict:
    """Among candidates within 1 bps of `best`'s output, take the cheapest gas.

    The incumbent runs _GAS_WEIGHT=0.0 (king_base.py:71): it takes the max-output
    route and never looks at gas. The adoption gas rung breaks an all-matched tie
    toward less total metered gas, permitting a <=2 bps output shave; we stay
    strictly inside that, so output remains `matched` while gas drops.
    """
    floor = int(best['out']) * (10000 - GAS_TIE_BAND_BPS)
    band = [c for c in usable if int(c['out']) * 10000 >= floor]
    return min(band, key=lambda c: (int(c['gas_model']), -int(c['out']))) if band else best

def pick_best(usable: list, ref: int, tin: str, tout: str, raw_pairs) -> dict | None:
    """Score-optimal pick, raw-output override, then the gas refinement."""
    if not usable:
        return None
    best = _score_optimal(usable, ref)
    if (tin.lower(), tout.lower()) in (raw_pairs or ()):
        best = _raw_override(usable, best)
    return _gas_refine(usable, best)