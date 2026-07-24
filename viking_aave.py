"""viking_aave — universal Aave aToken cover (withdraw -> swap -> supply).

aToken orders (aBasWETH->aBascbBTC etc) have no DEX pools — the only real route
is Aave withdraw, an underlying swap, and Aave supply (wrap legs exact 1:1),
which the engine never builds (floor 0). aTokens self-identify on-chain via
UNDERLYING_ASSET_ADDRESS()/POOL(), so any present or future aToken order
resolves with zero data updates. The mid swap reuses the standard viking
candidate sweep and serve calldata; when a supply leg follows, the supplied
amount is margined 30bps under the mid quote so plan->sim price drift cannot
revert the chain (champ-zero keys: the margin never flips a win)."""
import viking_build as _b
_ACACHE = {}

def _addr_view(w3, token, sel):
    from eth_utils import to_checksum_address as _ck
    try:
        r = bytes(w3.eth.call({'to': _ck(token), 'data': sel}))
        a = '0x' + r[-20:].hex()
        return a if len(r) == 32 and int(a, 16) else None
    except Exception:
        return None

def _ainfo(w3, chain, token):
    """(underlying, pool) if token is an aToken, else None (cached)."""
    k = (chain, token)
    if k not in _ACACHE:
        u = _addr_view(w3, token, '0xb16a19de')
        _ACACHE[k] = (u, _addr_view(w3, token, '0x7535d246')) if u else None
    v = _ACACHE[k]
    return v if v and v[1] else None

def _resolve(w3, chain, tin, tout):
    """(u_in, u_out, pool_in, pool_out) or None when neither side is an aToken."""
    ai = _ainfo(w3, chain, tin)
    ao = _ainfo(w3, chain, tout)
    if ai is None and ao is None:
        return None
    return (ai[0] if ai else tin, ao[0] if ao else tout, ai[1] if ai else None, ao[1] if ao else None)

def _mid_best(w3, chain, u_in, u_out, amt):
    """Best underlying-pair candidate via the standard viking sweep, or None."""
    import viking_batch as _qb
    import viking_pcs as _pcs
    cands = _qb.candidates(w3, chain, u_in, u_out, amt)
    cands += _pcs.pcs_candidates(w3, chain, u_in, u_out, amt)
    best = max(cands, key=lambda c: c[0]) if cands else None
    return best if best and best[0] > 0 else None

def _spec_quote(w3, chain, r, amt):
    u_in, u_out, pool_in, pool_out = r
    if u_in.lower() == u_out.lower():
        return (amt, r + (None,))
    best = _mid_best(w3, chain, u_in, u_out, amt)
    if best is None:
        return None
    out = best[0] * 997 // 1000 if pool_out else best[0]
    return (out, r + (best,))

def quote(w3, chain, tin, tout, amt):
    """(out, spec) for an aToken order or None; out carries the supply margin."""
    r = _resolve(w3, chain, tin, tout)
    return _spec_quote(w3, chain, r, amt) if r is not None else None

def _aave_ix(chain, pool, sel, types, args):
    from eth_abi import encode as _enc
    from eth_utils import to_checksum_address as _ck
    from minotaur_subnet.shared.types import Interaction
    cd = '0x' + (bytes.fromhex(sel) + _enc(types, args)).hex()
    return Interaction(target=_ck(pool), value='0', call_data=cd, chain_id=chain)

def _in_leg(chain, spec, amt, rcp, app):
    """The Aave withdraw leg (or none) opening the plan."""
    from eth_utils import to_checksum_address as _ck
    u_in, _, pool_in, pool_out, best = spec
    if not pool_in:
        return []
    to = rcp if best is None and (not pool_out) else app
    return [_aave_ix(chain, pool_in, '69328dec', ['address', 'uint256', 'address'], [_ck(u_in), int(amt), _ck(to)])]

def _out_leg(chain, spec, out, rcp):
    """approve + Aave supply legs (or none) closing the plan."""
    from eth_utils import to_checksum_address as _ck
    from common.abi_utils import encode_approve
    from minotaur_subnet.shared.types import Interaction
    u_out, pool_out = (spec[1], spec[3])
    if not pool_out:
        return []
    appr = Interaction(target=_ck(u_out), value='0', call_data=encode_approve(_ck(pool_out), int(out)), chain_id=chain)
    return [appr, _aave_ix(chain, pool_out, '617ba037', ['address', 'uint256', 'address', 'uint16'], [_ck(u_out), int(out), _ck(rcp), 0])]

def _mid_cd(chain, u_in, u_out, kind, det, rcp, amt):
    """(router, calldata) for the mid swap by candidate kind."""
    from viking_quote import _ROUTER02, _V2ROUTER
    if kind == 'v3d':
        return (_ROUTER02[chain], _b._cd_v3d(u_in, u_out, det[0], rcp, amt))
    if kind == 'v3h':
        return (_ROUTER02[chain], _b._cd_v3h(u_in, det[0], u_out, det[1], det[2], rcp, amt))
    return (_V2ROUTER[chain], _b._cd_v2(det, rcp, amt))

def _mid_ix(chain, u_in, u_out, best, rcp, amt):
    """The underlying-swap legs, reusing the standard serve calldata."""
    import viking_pcs_build as _pb
    _, kind, det = best
    if kind == 'pcs':
        return _pb.pcs_ix(chain, det[0], det[1], amt, rcp)
    router, cd = _mid_cd(chain, u_in, u_out, kind, det, rcp, amt)
    return _b._v3_approve_ix(chain, u_in, amt, router, cd)

def _legs(chain, spec, amt, out, rcp, app):
    ix = list(_in_leg(chain, spec, amt, rcp, app))
    if spec[4] is not None:
        mid_rcp = app if spec[3] else rcp
        ix += _mid_ix(chain, spec[0], spec[1], spec[4], mid_rcp, amt)
    return ix + _out_leg(chain, spec, out, rcp)

def serve(intent, state, chain, tin, tout, amt, res, p):
    """The wrap/swap/supply plan for a quoted aToken order."""
    out, spec = res
    rcp = _b._recipient(state, p)
    app = getattr(state, 'contract_address', None) or rcp
    ix = _legs(chain, spec, amt, out, rcp, app)
    return _b._mk_plan(intent, state, chain, ix, 'aave', tin, tout, out)

def lift(ctx, floor, intent, state):
    """Serve the aToken route ONLY when it strictly beats the floor."""
    chain, tin, tout, amt, w3, p = ctx
    q = quote(w3, chain, tin, tout, amt)
    if q is None or q[0] <= floor:
        return None
    return serve(intent, state, chain, tin, tout, amt, q, p)