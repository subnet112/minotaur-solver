"""Pool-math helpers (exact-integer V3 tick math + best-route search) factored
out of solver.py. Behavior-identical; small regions."""
from __future__ import annotations
_DR_UNSET = object()
_Q96 = 1 << 96

def _v3_out_zfo(sp, liq, aaf, max_impact):
    den = liq * _Q96 + aaf * sp
    if den <= 0:
        return None
    delta = aaf * sp * sp // den
    if delta > max_impact:
        return None
    return liq * delta // _Q96

def _v3_out_nzfo(sp, liq, aaf, max_impact):
    delta = aaf * _Q96 // liq
    if delta > max_impact:
        return None
    new_sp = sp + delta
    if new_sp <= 0:
        return None
    return liq * _Q96 * delta // (sp * new_sp)

def _v3_out(sqrt_price_x96, liquidity, amount_in, zero_for_one, fee_ppm):
    if liquidity <= 0 or amount_in <= 0 or sqrt_price_x96 <= 0:
        return 0
    aaf = amount_in * (1000000 - fee_ppm) // 1000000
    if aaf <= 0:
        return 0
    max_impact = sqrt_price_x96 // 100
    if zero_for_one:
        out = _v3_out_zfo(sqrt_price_x96, liquidity, aaf, max_impact)
    else:
        out = _v3_out_nzfo(sqrt_price_x96, liquidity, aaf, max_impact)
    if out is None:
        return 0
    return max(0, out)

def _pool_out(pool, x, y, amt):
    """(out, fee) for `pool` on x->y, or None when it isn't that pair."""

    def _dz21():
        if t0 == x and t1 == y:
            zfo = True
        elif t0 == y and t1 == x:
            zfo = False
        else:
            return (None,)
        fee = int(pool.get('fee', 3000) or 3000)
        out = _v3_out(int(pool.get('sqrtPriceX96', 0) or 0), int(pool.get('liquidity', 0) or 0), amt, zfo, fee)
        return ((out, fee),)
        return _DR_UNSET
    t0 = str(pool.get('token0', '') or '').lower()
    t1 = str(pool.get('token1', '') or '').lower()
    _r_dz21 = _dz21()
    if _r_dz21 is not _DR_UNSET:
        return _r_dz21[0]

def _best_direct(pool_states, tin, tout, amt):
    """Return (output, pool_addr, pool_state, fee) for the best single pool, or None."""
    x, y = (tin.lower(), tout.lower())
    best = None
    for addr, pool in pool_states.items():
        r = _pool_out(pool, x, y, amt)
        if r is None:
            continue
        out, fee = r
        if out > 0 and (best is None or out > best[0]):
            best = (out, addr, pool, fee)
    return best

def _hop(d):
    return {'pool_addr': d[1], 'pool_state': d[2], 'fee': d[3]}

def _route_2hop(pool_states, tin, tout, amt, mid):
    """(output, desc, hops) for tin->mid->tout, or None."""

    def _dz20():
        if m == tin.lower() or m == tout.lower():
            return (None,)
        h1 = _best_direct(pool_states, tin, mid, amt)
        if not h1:
            return (None,)
        h2 = _best_direct(pool_states, mid, tout, h1[0])
        if not h2:
            return (None,)
        return ((h2[0], f'2hop:{mid[:8]}', [_hop(h1), _hop(h2)]),)
        return _DR_UNSET
    m = str(mid).lower()
    _r_dz20 = _dz20()
    if _r_dz20 is not _DR_UNSET:
        return _r_dz20[0]

def _best_route(pool_states, tin, tout, amt, mids):
    """Correct replacement for pool_math.find_best_route -> (output, desc, hops) or None."""
    result = None
    d = _best_direct(pool_states, tin, tout, amt)
    if d:
        result = (d[0], 'direct', [_hop(d)])
    for mid in mids or []:
        r = _route_2hop(pool_states, tin, tout, amt, mid)
        if r is None:
            continue
        if result is None or r[0] > result[0]:
            result = r
    return result