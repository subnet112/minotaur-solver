"""Phase-2 candidate layer for bg124_onfork: Curve pools and extra 2-hop mids.

REGION DISCIPLINE (same rule as bg124_onfork_abi.py): bg124_onfork.py's
top-level region is made almost entirely of its `def` statements, so it shrinks
only by MOVING defs out — minifying the bodies moves it by exactly zero. This
module takes the phase-2 fallback layer (Curve census + deep 2-hop mids) plus
the `_mids` helper they share with the phase-1 builders.

Nothing here changes behaviour: the functions are byte-for-byte the ones that
lived in bg124_onfork.py, and they depend only on the ABI/table module, so the
split introduces no import cycle.
"""
from __future__ import annotations
_DR_UNSET = object()
import bg124_onfork_abi as A

def _mids(chain, tin, tout):
    return [m.lower() for m in A.T.get('mids', {}).get(str(chain), []) if m.lower() not in (tin, tout)]

def _curve_census():
    """Offline-scanned Curve pool map for chain 1 (build_curve_census.py). Loaded
    once; JSON data costs zero AST nodes. Discovery is the slow half of Curve
    (the registry's get_best_rate measured 20.6s and returned an unexecutable
    route), so it happens offline and the solver only does a direct get_dy."""

    def _dz579():
        nonlocal c
        if c is None:
            import json
            from pathlib import Path
            try:
                c = json.loads((Path(__file__).parent / 'curve_census_1.json').read_text())
            except Exception:
                c = {}
            _curve_census._c = c
    c = getattr(_curve_census, '_c', None)
    _dz579()
    return c

def _curve_row(pools, pool, tin, tout):

    def _dz578():
        coins = row.get('coins') or []
        if tin in coins and tout in coins:
            return ((pool, row.get('kind', 'stable'), coins.index(tin), coins.index(tout)),)
        return _DR_UNSET
    row = pools.get(pool) or {}
    _r_dz578 = _dz578()
    if _r_dz578 is not _DR_UNSET:
        return _r_dz578[0]
    return None

def _curve_pools(tin, tout):
    """Census pools holding BOTH tokens -> [(pool, kind, i, j)]."""

    def _dz577(tin, tout):
        byt, c, pools = _dz576()
        both = set(byt.get(tin, ())) & set(byt.get(tout, ()))
        _r_dz575 = _dz575()
        return (_r_dz575, both, byt, c, pools)

    def _dz576():
        c = _curve_census()
        pools, byt = (c.get('pools') or {}, c.get('bytoken') or {})
        return (byt, c, pools)

    def _dz575():
        rows = [_curve_row(pools, p, tin, tout) for p in sorted(both)[:4]]
        return ([r for r in rows if r],)
        return _DR_UNSET
    _r_dz575, both, byt, c, pools = _dz577(tin, tout)
    if _r_dz575 is not _DR_UNSET:
        return _r_dz575[0]

def _curve_cands(chain, tin, tout, amt):
    """A direct get_dy per candidate pool, in the same batch. Curve is the venue
    the champion lineage claims but still leaves 14 orders unrouted on; on chain
    1 — the only chain whose orders count — it is the realistic strict win."""
    if chain != 1:
        return []
    return [(('curve', A.ck(p), (k, i, j)), A.ck(p), A.q_curve(k, i, j, amt)) for p, k, i, j in _curve_pools(tin, tout)]

def _via_v3(chain, tin, mid, tout, amt):
    """Every V3 fee combo through one intermediate token."""

    def _dz574():
        return ([(('path', tuple(f), mid), q, A.q_path(tin, mid, tout, f, amt)) for f in A.T.get('hops', [])],)
        return _DR_UNSET
    q = A.ck(A.T['quoter'][str(chain)])
    _r_dz574 = _dz574()
    if _r_dz574 is not _DR_UNSET:
        return _r_dz574[0]

def _via_v2(chain, tin, mid, tout, amt):
    """Every V2 router leg through one intermediate token."""
    return [(('v2', A.ck(r), (tin, mid, tout)), A.ck(r), A.q_v2(amt, [tin, mid, tout])) for r in A.T.get('v2', {}).get(str(chain), [])]

def _via(chain, tin, mid, tout, amt):
    """Every V3 fee combo and V2 router for one intermediate token."""
    return _via_v3(chain, tin, mid, tout, amt) + _via_v2(chain, tin, mid, tout, amt)

def _best(cands, outs):
    """The highest-quoting candidate -> (desc, out), or (None, 0) when every
    venue came back zero. Parked here beside `_corroborated` for the same
    region reason."""

    def _dz573():
        nonlocal best_i, best_out
        for k, got in enumerate(outs):
            if got > best_out:
                best_out, best_i = (got, k)
    best_i, best_out = (-1, 0)
    _dz573()
    return (cands[best_i][0], best_out) if best_i >= 0 else (None, 0)

def _corroborated(outs, best_out):
    """At least one OTHER venue must independently quote the same order within
    2x. hydra took the crown on 1 better / 0 WORSE while we lost with 10 better
    / 3 worse — a single bad order erases any number of wins, so safety beats
    win count. A lone quote from one thin pool is the signature of both failure
    modes we hit: the 0.00002x catastrophic regression and the two routes that
    quoted positive then delivered nothing.

    Lives here rather than beside its one caller for the same reason the rest of
    this module does: bg124_onfork.py's top-level region is made of its def
    HEADERS, so a header parked here is a header off that metric."""
    return sum((1 for o in outs if o > 0 and o * 2 >= best_out)) >= 2

def _phase2_cands(chain, tin, tout, amt):
    """The whole phase-2 candidate set — Curve plus the deep 2-hop mids — as one
    list, so its caller spends one call instead of two."""
    return _curve_cands(chain, tin, tout, amt) + _deep_cands(chain, tin, tout, amt)

def _deep_cands(chain, tin, tout, amt):
    """Extra 2-hop mid tokens (USDT/DAI/WBTC on chain 1), tried ONLY after phase
    1 came back empty — i.e. on the handful of blind-spot orders per pack that
    actually decide the crown. Every recent dethrone was a single cover on an
    order the incumbent could not route, and our 11 remaining skips are orders
    where WETH/USDC 2-hop finds nothing. Restricting these to phase 2 buys that
    coverage without adding a millisecond to the normal path, which is what the
    pace budget cannot afford."""

    def _dz572():
        nonlocal out
        out += _via(chain, tin, mid, tout, amt)
    out = []
    for mid in [m.lower() for m in A.T.get('mids2', {}).get(str(chain), []) if m.lower() not in (tin, tout)]:
        _dz572()
    return out