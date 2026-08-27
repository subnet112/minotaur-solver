"""curve_venue.py -- Curve Finance venue for the mino-dynamic solver.

Self-contained and eth_call-ONLY (no external HTTP/APIs at solve time): safe
for the --network=none screener sandbox. Pools are discovered on-chain via the
Curve MetaRegistry (Ethereum) / NG factories (Base) `find_pool_for_coins`, then
quoted and executed through the CurveRouterNG (`get_dy` / `exchange`). The
router dispatches every pool flavour uniformly -- int128-index (stable /
stable-ng) AND uint256-index (twocrypto / tricrypto / -ng) -- and chains up to
5 hops, so a single ABI covers all variants plus a hub 2-hop for pairs with no
direct pool (e.g. USDT->CRV via WETH/crvUSD).

Covers the CRV / stable / BTC-wrapper routes KyberSwap misses. The solver ranks
every venue by eth_call-VERIFIED delivery, so a stale or thin Curve quote is
harmless -- it is simply never served over a deeper venue (worse=0 guarantee).

Public entrypoints:
    curve_best(w3, cid, tin, tout, amt)   -> (out:int, route_spec) | None
    curve_calldata(cid, tin, tout, amt, min_out, recipient, deadline, route_spec)
                                          -> (target_addr, calldata_hex)

Only web3 (passed in), eth_abi, eth_utils and stdlib are imported.
"""
from __future__ import annotations
_DR_UNSET = object()
from eth_abi import encode as _E, decode as _D
from eth_utils import keccak as _K, to_checksum_address as _C
from curve_data import *
_SC: dict = {}

def _sel(sig):
    s = _SC.get(sig)
    if s is None:
        s = _K(text=sig)[:4]
        _SC[sig] = s
    return s

def _call(w3, to, data):
    try:
        return bytes(w3.eth.call({'to': _C(to), 'data': '0x' + data.hex()}))
    except Exception:
        return None

def _addr(r):
    return '0x' + r[-20:].hex() if r is not None and len(r) >= 32 else None

def _find_pool(w3, reg, a, b, k):
    r = _call(w3, reg, _sel('find_pool_for_coins(address,address,uint256)') + _E(['address', 'address', 'uint256'], [_C(a), _C(b), k]))
    p = _addr(r)
    return p if p and int(p, 16) != 0 else None

def _pools_for(w3, cid, a, b):
    """Distinct (pool, pool_type_hint) candidates holding both coins, across the
    chain's registries. hint=0 => probe pool_type; else it is authoritative."""
    out, seen = ([], set())
    for reg, hint in _REGS.get(cid, ()):
        for k in range(2):
            p = _find_pool(w3, reg, a, b, k)
            if p is None:
                break
            if p.lower() not in seen:
                seen.add(p.lower())
                out.append((p, hint))
    return out

def _indices(w3, pool, tin, tout):
    """0-based coin positions of tin/tout via coins(k) -- uniform for stable and
    crypto pools. Returns (i, j, n_coins) or None."""

    def _coin_map():
        pos, n = ({}, 0)
        cs = _sel('coins(uint256)')
        for k in range(4):
            a = _addr(_call(w3, pool, cs + _E(['uint256'], [k])))
            if a is None or int(a, 16) == 0:
                break
            pos[a.lower()] = k
            n = k + 1
        return (pos, n)
    pos, n = _coin_map()
    i, j = (pos.get(tin.lower()), pos.get(tout.lower()))
    return (i, j, n) if i is not None and j is not None else None

def _pt_order(hint, n):
    """pool_type codes to try: registry hint first (authoritative), then the
    n_coins-implied family, then the stable fallback."""
    fam = _PT_3 if n >= 3 else _PT_2
    seq = ([hint] if hint else []) + list(fam) + list(_PT_STABLE)
    out = []
    for pt in seq:
        if pt not in out:
            out.append(pt)
    return out

def _route1(tin, pool, tout):
    return [_C(tin), _C(pool), _C(tout)] + [_C(_Z)] * 8

def _get_dy(w3, cid, route, swap, amt):
    r = _call(w3, _ROUTER[cid], _sel('get_dy(address[11],uint256[5][5],uint256)') + _E(['address[11]', 'uint256[5][5]', 'uint256'], [route, swap, amt]))
    if r is None or len(r) < 32:
        return 0
    try:
        return _D(['uint256'], r)[0]
    except Exception:
        return 0

def _leg(w3, cid, pool, hint, tin, tout, amt):
    """Best single hop (out, swap_row) for tin->tout via pool. Picks the first
    pool_type whose router get_dy is non-zero. None if the pool is dead."""

    def _dz74():
        if idx is None:
            return (None,)
        i, j, n = idx
        route = _route1(tin, pool, tout)
        for pt in _pt_order(hint, n):
            row = [i, j, 1, pt, n]
            o = _get_dy(w3, cid, route, [row] + [[0, 0, 0, 0, 0]] * 4, amt)
            if o > 0:
                return ((o, row),)
        return _DR_UNSET
    idx = _indices(w3, pool, tin, tout)
    _r_dz74 = _dz74()
    if _r_dz74 is not _DR_UNSET:
        return _r_dz74[0]
    return None

def _best_leg(w3, cid, cands, tin, tout, amt):
    """Best (out, pool, swap_row) over candidate pools for one hop, or None."""
    best = None
    for pool, hint in cands:
        lg = _leg(w3, cid, pool, hint, tin, tout, amt)
        if lg is not None and (best is None or lg[0] > best[0]):
            best = (lg[0], pool, lg[1])
    return best

def _direct(w3, cid, tin, tout, amt):
    """Best direct single-hop route -> (out, route, swap) or None."""
    bl = _best_leg(w3, cid, _pools_for(w3, cid, tin, tout), tin, tout, amt)
    if bl is None:
        return None
    out, pool, row = bl
    return (out, _route1(tin, pool, tout), [row] + [[0, 0, 0, 0, 0]] * 4)

def _mk2(tin, l1, hub, l2, tout):
    """Assemble the 2-hop CurveRouterNG (route[11], swap[5][5]) from two legs."""
    route = [_C(tin), _C(l1[1]), _C(hub), _C(l2[1]), _C(tout)] + [_C(_Z)] * 6
    swap = [l1[2], l2[2]] + [[0, 0, 0, 0, 0]] * 3
    return (route, swap)

def _twohop(w3, cid, tin, tout, amt):
    """Best tin->hub->tout route -> (out, route, swap) or None."""

    def _dz73():
        nonlocal best
        c = _hop2(w3, cid, tin, tout, amt, hub)
        if c is not None and (best is None or c[0] > best[0]):
            best = c

    def _hop2(w3, cid, tin, tout, amt, hub):
        """One tin->hub->tout candidate -> (out, route, swap) or None."""

        def _finish(l1, l2):
            route, swap = _mk2(tin, l1, hub, l2, tout)
            o = _get_dy(w3, cid, route, swap, amt)
            return (o, route, swap) if o > 0 else None
        l1 = _best_leg(w3, cid, _pools_for(w3, cid, tin, hub), tin, hub, amt)
        if l1 is None:
            return None
        l2 = _best_leg(w3, cid, _pools_for(w3, cid, hub, tout), hub, tout, l1[0])
        if l2 is None:
            return None
        return _finish(l1, l2)
    best = None
    tl = tin.lower()
    ol = tout.lower()
    for hub in _HUBS.get(cid, ()):
        if hub.lower() in (tl, ol):
            continue
        _dz73()
    return best

def curve_best(w3, cid, tin, tout, amt):
    """Best Curve quote via eth_call get_dy. Returns (out:int, route_spec) or
    None, where route_spec = {'route': address[11], 'swap': uint256[5][5]}."""
    try:
        cid = int(cid)
        amt = int(amt)
        if cid not in _ROUTER or amt <= 0 or tin.lower() == tout.lower():
            return None

        def _best_raw():
            best = _direct(w3, cid, tin, tout, amt)
            two = _twohop(w3, cid, tin, tout, amt)
            if two is not None and (best is None or two[0] > best[0]):
                best = two
            return best
        best = _best_raw()
        if best is None:
            return None
        return (best[0], {'route': best[1], 'swap': best[2]})
    except Exception:
        return None

def curve_calldata(cid, tin, tout, amt, min_out, recipient, deadline, route_spec):
    """Executable CurveRouterNG.exchange calldata -> (router_addr, calldata_hex).
    min_out floored to >=1 (anti-revert: the benchmark executes at a different
    block; a tight min_out reverts on pool drift). deadline is unused (the
    Router-NG exchange has no deadline arg); kept for venue-signature parity."""
    route = route_spec['route']
    swap = route_spec['swap']
    sel = _sel('exchange(address[11],uint256[5][5],uint256,uint256,address[5],address)')
    enc = _E(['address[11]', 'uint256[5][5]', 'uint256', 'uint256', 'address[5]', 'address'], [route, swap, int(amt), max(int(min_out), 1), [_C(_Z)] * 5, _C(recipient)])
    return (_C(_ROUTER[int(cid)]), '0x' + (sel + enc).hex())