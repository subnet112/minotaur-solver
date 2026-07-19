"""v3_arb3 — route DISCOVERY for the v3_arb cover (direct single-hop + 2-hop
via hubs), split out so every region stays <=110 AST nodes. Leaf: depends only
on v3_arb2 primitives. Call graph: v3_arb (top) -> v3_arb3 -> v3_arb2."""
from v3_arb2 import _FEES, _quote, _bases


def _direct_best(w3, chain, tin, tout, amt):
    """Best direct single-hop tin->tout over fee tiers: (out, fee) or None.
    (Engine discovery misses some direct fee tiers, e.g. q_5298681e 8739e18.)"""
    best = None
    for fee in _FEES:
        o = _quote(w3, chain, tin, tout, fee, amt)
        if o > 0 and (best is None or o > best[0]):
            best = (o, fee)
    return best


def _leg2_best(w3, chain, base, tout, l1):
    """Best second leg base->tout over fee tiers: (out, f2) or None."""
    best = None
    for f2 in _FEES:
        l2 = _quote(w3, chain, base, tout, f2, l1)
        if l2 > 0 and (best is None or l2 > best[0]):
            best = (l2, f2)
    return best


def _via_base(w3, chain, tin, base, tout, amt):
    """Best route through one intermediate base: (out, f1, f2) or None."""
    best = None
    for f1 in _FEES:
        l1 = _quote(w3, chain, tin, base, f1, amt)
        if l1 <= 0:
            continue
        r = _leg2_best(w3, chain, base, tout, l1)
        if r is not None and (best is None or r[0] > best[0]):
            best = (r[0], f1, r[1])
    return best


def _hub_best(w3, chain, tin, tout, amt):
    """Best 2-hop via any hub: (out, base, f1, f2) or None."""
    best = None
    for base in _bases(chain):
        if base == tin or base == tout:
            continue
        r = _via_base(w3, chain, tin, base, tout, amt)
        if r is not None and (best is None or r[0] > best[0]):
            best = (r[0], base, r[1], r[2])
    return best


def _best_2hop(w3, chain, tin, tout, amt):
    """Best V3 route: direct single-hop OR 2-hop via a hub. Returns
    (out, base, f1, f2) or None; base is None for a direct single-hop."""
    d = _direct_best(w3, chain, tin, tout, amt)
    best = (d[0], None, d[1], None) if d is not None else None
    hub = _hub_best(w3, chain, tin, tout, amt)
    if hub is not None and (best is None or hub[0] > best[0]):
        best = hub
    return best
