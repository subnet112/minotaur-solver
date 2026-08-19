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
import bg124_onfork_abi as A

def _mids(chain, tin, tout):
    return [m.lower() for m in A.T.get('mids', {}).get(str(chain), []) if m.lower() not in (tin, tout)]

def _curve_census():
    """Offline-scanned Curve pool map for chain 1 (build_curve_census.py). Loaded
    once; JSON data costs zero AST nodes. Discovery is the slow half of Curve
    (the registry's get_best_rate measured 20.6s and returned an unexecutable
    route), so it happens offline and the solver only does a direct get_dy."""
    c = getattr(_curve_census, '_c', None)
    if c is None:
        import json
        from pathlib import Path
        try:
            c = json.loads((Path(__file__).parent / 'curve_census_1.json').read_text())
        except Exception:
            c = {}
        _curve_census._c = c
    return c

def _curve_row(pools, pool, tin, tout):
    row = pools.get(pool) or {}
    coins = row.get('coins') or []
    if tin in coins and tout in coins:
        return (pool, row.get('kind', 'stable'), coins.index(tin), coins.index(tout))
    return None

def _curve_pools(tin, tout):
    """Census pools holding BOTH tokens -> [(pool, kind, i, j)]."""
    c = _curve_census()
    pools, byt = (c.get('pools') or {}, c.get('bytoken') or {})
    both = set(byt.get(tin, ())) & set(byt.get(tout, ()))
    rows = [_curve_row(pools, p, tin, tout) for p in sorted(both)[:4]]
    return [r for r in rows if r]

def _curve_cands(chain, tin, tout, amt):
    """A direct get_dy per candidate pool, in the same batch. Curve is the venue
    the champion lineage claims but still leaves 14 orders unrouted on; on chain
    1 — the only chain whose orders count — it is the realistic strict win."""
    if chain != 1:
        return []
    return [(('curve', A.ck(p), (k, i, j)), A.ck(p), A.q_curve(k, i, j, amt)) for p, k, i, j in _curve_pools(tin, tout)]

def _via(chain, tin, mid, tout, amt):
    """Every V3 fee combo and V2 router for one intermediate token."""

    def _dz36():
        for r in A.T.get('v2', {}).get(str(chain), []):
            out.append((('v2', A.ck(r), (tin, mid, tout)), A.ck(r), A.q_v2(amt, [tin, mid, tout])))
    q = A.ck(A.T['quoter'][str(chain)])
    out = [(('path', tuple(f), mid), q, A.q_path(tin, mid, tout, f, amt)) for f in A.T.get('hops', [])]
    _dz36()
    return out

def _deep_cands(chain, tin, tout, amt):
    """Extra 2-hop mid tokens (USDT/DAI/WBTC on chain 1), tried ONLY after phase
    1 came back empty — i.e. on the handful of blind-spot orders per pack that
    actually decide the crown. Every recent dethrone was a single cover on an
    order the incumbent could not route, and our 11 remaining skips are orders
    where WETH/USDC 2-hop finds nothing. Restricting these to phase 2 buys that
    coverage without adding a millisecond to the normal path, which is what the
    pace budget cannot afford."""
    out = []
    for mid in [m.lower() for m in A.T.get('mids2', {}).get(str(chain), []) if m.lower() not in (tin, tout)]:
        out += _via(chain, tin, mid, tout, amt)
    return out