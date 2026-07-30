"""viking_gaslift — gas-Pareto overlay: serve the SAME v2-style route without
the router. When the base plan is exactly [approve(tin->router), router.swap]
with a classic-v2 or solidly/Aero route, rebuild it as [transfer(tin->pool0),
pool0.swap(..) -> pool1 .. -> receiver]: the identical pools in the identical
order deliver the identical output (router math == pair math at one block),
minus the approve + allowance + router-dispatch gas. Every fact is re-derived
on-chain (factory, pool, token0, quoted amounts) and ANY doubt defers to the
base plan — the overlay can lower gas or do nothing, never change output.

Helpers keep each named region small (factorization discipline); all calldata
is my own encoding (no foreign calldata)."""
import logging
logger = logging.getLogger('solver')
_APPROVE = '0x095ea7b3'
_V2_SWAP = '0x38ed1739'
_AERO_SWAP = '0xcac88ea9'
_FAC = {}
_POOL = {}
_TOKS = {}

def _cd(ix):
    d = getattr(ix, 'call_data', '') or ''
    return d if d.startswith('0x') else '0x' + d

def _call(w3, to, data):
    from eth_utils import to_checksum_address as _ck
    try:
        return bytes(w3.eth.call({'to': _ck(to), 'data': data}))
    except Exception:
        return None

def _dec1(raw):
    """Last-32-bytes address from an eth_call return, checksummed, or None."""
    from eth_utils import to_checksum_address as _ck
    if not raw or len(raw) < 32 or int.from_bytes(raw[-20:], 'big') == 0:
        return None
    return _ck('0x' + raw[-20:].hex())

def _parse_v2(cd):
    """(amt_in, [path], to) from a classic swapExactTokensForTokens, or None."""
    from eth_abi import decode as _dc
    try:
        a = _dc(['uint256', 'uint256', 'address[]', 'address', 'uint256'], bytes.fromhex(cd[10:]))
        return (int(a[0]), [x.lower() for x in a[2]], a[3]) if len(a[2]) >= 2 else None
    except Exception:
        return None

def _parse_aero(cd):
    """(amt_in, [(frm,to,stable,factory)], to) from an Aero-style swap, or None."""
    from eth_abi import decode as _dc
    try:
        a = _dc(['uint256', 'uint256', '(address,address,bool,address)[]', 'address', 'uint256'], bytes.fromhex(cd[10:]))
        rs = [(r[0].lower(), r[1].lower(), bool(r[2]), r[3]) for r in a[2]]
        return (int(a[0]), rs, a[3]) if rs else None
    except Exception:
        return None

def _factory(w3, router):
    if router not in _FAC:
        _FAC[router] = _dec1(_call(w3, router, '0xc45a0155'))
    return _FAC[router]

def _pool_v2(w3, fac, a, b):
    from eth_abi import encode as _enc
    from eth_utils import to_checksum_address as _ck
    key = (fac, a, b, None)
    if key not in _POOL:
        _POOL[key] = _dec1(_call(w3, fac, '0xe6a43905' + _enc(['address', 'address'], [_ck(a), _ck(b)]).hex()))
    return _POOL[key]

def _pool_aero(w3, router, r):
    """Solidly-style pool via the route's own factory (getPool(a,b,stable));
    a zero factory in the route falls back to the router's defaultFactory()."""

    def _fac_of():
        from eth_utils import keccak as _kk
        if int(r[3], 16) != 0:
            return r[3]
        if router not in _FAC:
            _FAC[router] = _dec1(_call(w3, router, '0x' + _kk(b'defaultFactory()')[:4].hex()))
        return _FAC[router]

    def _get_pool(fac):
        from eth_abi import encode as _enc
        from eth_utils import keccak as _kk, to_checksum_address as _ck
        key = (fac, r[0], r[1], r[2])
        if key not in _POOL:
            sel = _kk(b'getPool(address,address,bool)')[:4]
            _POOL[key] = _dec1(_call(w3, fac, '0x' + (sel + _enc(['address', 'address', 'bool'], [_ck(r[0]), _ck(r[1]), r[2]])).hex()))
        return _POOL[key]
    fac = _fac_of()
    return _get_pool(fac) if fac else None

def _toks(w3, pool):
    if pool not in _TOKS:
        t0 = _dec1(_call(w3, pool, '0x0dfe1681'))
        t1 = _dec1(_call(w3, pool, '0xd21220a7'))
        _TOKS[pool] = (t0.lower(), t1.lower()) if t0 and t1 else None
    return _TOKS[pool]

def _amounts(w3, router, sel, amt, route, n):
    """Quoted hop amounts via the router's own getAmountsOut (the exact math
    its swap would enforce at this block), re-encoded from the parsed route."""

    def _v2q():
        from eth_utils import to_checksum_address as _ck
        return (b'getAmountsOut(uint256,address[])', ['uint256', 'address[]'], [int(amt), [_ck(t) for t in route]])

    def _aeroq():
        from eth_utils import to_checksum_address as _ck
        return (b'getAmountsOut(uint256,(address,address,bool,address)[])', ['uint256', '(address,address,bool,address)[]'], [int(amt), [(_ck(r[0]), _ck(r[1]), r[2], _ck(r[3])) for r in route]])

    def _req():
        from eth_abi import encode as _enc
        from eth_utils import keccak as _kk
        sig, types, args = _v2q() if sel == _V2_SWAP else _aeroq()
        return _call(w3, router, '0x' + (_kk(sig)[:4] + _enc(types, args)).hex())

    def _dec(raw):
        from eth_abi import decode as _dc
        try:
            outs = list(_dc(['uint256[]'], raw)[0])
        except Exception:
            return None
        return outs if len(outs) == n + 1 and all((int(x) > 0 for x in outs)) else None
    raw = _req()
    return _dec(raw) if raw is not None else None

def _swap_ix(chain, pool, tin_hop, out_amt, to):
    from eth_abi import encode as _enc
    from eth_utils import to_checksum_address as _ck
    from minotaur_subnet.shared.types import Interaction
    t = _toks(None, pool) if pool in _TOKS else None
    a0, a1 = (0, out_amt) if t and tin_hop == t[0] else (out_amt, 0)
    cd = '0x022c0d9f' + _enc(['uint256', 'uint256', 'address', 'bytes'], [a0, a1, _ck(to), b'']).hex()
    return Interaction(target=_ck(pool), value='0', call_data=cd, chain_id=chain)

def _hops(w3, router, sel, parsed):
    """[(pool, tin_hop, tout_hop)] for the route, verified token0/token1, or None."""

    def _res_v2(route):
        fac = _factory(w3, router)
        if fac is None:
            return (None, None)
        pairs = list(zip(route[:-1], route[1:]))
        return ([_pool_v2(w3, fac, a, b) for a, b in pairs], pairs)

    def _resolve(route):
        if sel == _V2_SWAP:
            return _res_v2(route)
        pairs = [(r[0], r[1]) for r in route]
        return ([_pool_aero(w3, router, r) for r in route], pairs)

    def _verify(pools, pairs):
        hops = []
        for pool, (a, b) in zip(pools, pairs):
            t = _toks(w3, pool) if pool else None
            if t is None or {a, b} != {t[0], t[1]}:
                return None
            hops.append((pool, a, b))
        return hops
    pools, pairs = _resolve(parsed[1])
    return _verify(pools, pairs) if pools else None

def _rebuild(chain, plan, tin, amt, hops, outs, final_to):

    def _fund_ix():
        from eth_abi import encode as _enc
        from eth_utils import to_checksum_address as _ck
        from minotaur_subnet.shared.types import Interaction
        return Interaction(target=_ck(tin), value='0', chain_id=chain, call_data='0xa9059cbb' + _enc(['address', 'uint256'], [_ck(hops[0][0]), int(amt)]).hex())

    def _plan(ix):
        from minotaur_subnet.shared.types import ExecutionPlan
        return ExecutionPlan(intent_id=plan.intent_id, interactions=ix, deadline=plan.deadline, nonce=plan.nonce, metadata=dict(plan.metadata or {}))
    ix = [_fund_ix()]
    for i, (pool, a, b) in enumerate(hops):
        nxt = hops[i + 1][0] if i + 1 < len(hops) else final_to
        ix.append(_swap_ix(chain, pool, a, int(outs[i + 1]), nxt))
    return _plan(ix)

def gas_lift(solver, plan, intent, state):
    """Rewrite an [approve, v2/aero router swap] plan to direct pool swaps;
    return the plan unchanged on ANY doubt."""

    def _shape():
        """(sel, cd, router) when the plan is exactly [approve, v2/aero swap]."""
        ixs = getattr(plan, 'interactions', None)
        if not ixs or len(ixs) != 2 or _cd(ixs[0])[:10] != _APPROVE:
            return None
        sel = _cd(ixs[1])[:10]
        if sel not in (_V2_SWAP, _AERO_SWAP):
            return None
        return (sel, _cd(ixs[1]), getattr(ixs[1], 'target', None))

    def _gate():
        s = _shape()
        if s is None:
            return None
        w3 = solver._get_web3(int(getattr(state, 'chain_id', 0) or 0))
        return (w3,) + s if w3 else None

    def _quote(g, parsed, hops):
        w3, sel, cd, router = g
        outs = _amounts(w3, router, sel, parsed[0], parsed[1], len(hops))
        if outs is None or int(outs[0]) != int(parsed[0]):
            return None
        return (hops, outs, parsed)

    def _route(g):
        """(hops, outs, parsed) fully verified, or None."""
        w3, sel, cd, router = g
        parsed = _parse_v2(cd) if sel == _V2_SWAP else _parse_aero(cd)
        if parsed is None:
            return None
        hops = _hops(w3, router, sel, parsed)
        return _quote(g, parsed, hops) if hops else None

    def _emit(r):
        hops, outs, parsed = r
        chain = int(getattr(state, 'chain_id', 0) or 0)
        new = _rebuild(chain, plan, hops[0][1], parsed[0], hops, outs, parsed[2])
        logger.info('[gaslift] direct-pool rewrite %s hops=%d out=%s', hops[0][1][:8], len(hops), outs[-1])
        return new
    try:
        g = _gate()
        r = _route(g) if g else None
        return _emit(r) if r else plan
    except Exception:
        logger.exception('[gaslift] defer to base plan')
        return plan