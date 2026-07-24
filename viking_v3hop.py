"""viking_v3hop — strict-better route cover (V3 direct + V3 2-hop + V2).

Re-quotes the engine's OWN final route (the floor) and the best of:
  * Uniswap V3 direct single-hop across all fee tiers,
  * Uniswap V3 2-hop via a hub (WETH/USDC/USDT/DAI/WBTC etc.),
  * Uniswap V2 direct or 2-hop-via-hub (memecoin / thin pools the V3 quoter
    returns 0 for — ~29 of the live ETH corpus route ONLY on V2),
and serves the best ONLY when it STRICTLY beats the floor. Quotes are
execution-accurate same-block (QuoterV2 for V3, getAmountsOut for V2 constant
product), so the served amount == on-chain delivery at bench. A non-empty base
we cannot decode DEFERS (no blind override). Empty base => floor 0, so any
positive route fills the blind spot => lift-only, never a regression.

Structure: this module orchestrates + decodes/re-quotes the base route; the
address tables + quoters live in viking_quote, the plan builders in viking_build.
Each named region is kept <=110 AST nodes (factorization discipline); the split
is pure code motion — served calldata is byte-identical to the single-file form.
"""
import logging
import viking_quote as _q
import viking_batch as _qb
import viking_build as _b
import viking_pcs as _pcs
import viking_sim as _sim
logger = logging.getLogger('solver')

def _dec_v3(cd):
    sel = cd[:10]

    def _sng():
        from eth_abi import decode as _d
        body = bytes.fromhex(cd[10:])
        if sel == '0x04e45aaf':
            t = _d(['(address,address,uint24,address,uint256,uint256,uint160)'], body)[0]
            return ('single', t[0], t[1], t[2], t[4])
        t = _d(['(address,address,uint24,address,uint256,uint256,uint256,uint160)'], body)[0]
        return ('single', t[0], t[1], t[2], t[5])

    def _pth():
        from eth_abi import decode as _d
        body = bytes.fromhex(cd[10:])
        if sel == '0xb858183f':
            t = _d(['(bytes,address,uint256,uint256)'], body)[0]
            return ('path', t[0], t[2])
        t = _d(['(bytes,address,uint256,uint256,uint256)'], body)[0]
        return ('path', t[0], t[3])
    try:
        if sel in ('0x04e45aaf', '0x414bf389'):
            return _sng()
        if sel in ('0xb858183f', '0xc04b8d59'):
            return _pth()
    except Exception:
        return None
    return None

def _dec_v2(cd):
    from eth_abi import decode as _d
    if cd[:10] not in ('0x38ed1739', '0x5c11d795', '0xd06ca61f'):
        return None
    try:
        t = _d(['uint256', 'uint256', 'address[]', 'address', 'uint256'], bytes.fromhex(cd[10:]))
        return (list(t[2]), int(t[0]))
    except Exception:
        return None

def _requote_v3(w3, chain, v3):
    if v3[0] == 'single':
        return _q._q_single(w3, chain, v3[1], v3[2], v3[3], v3[4])
    return _q._q_path(w3, chain, v3[1], v3[2])

def _requote_ix(w3, chain, c):
    """Re-quoted delivery of a decoded final-ix calldata: int, or None (undecodable)."""
    v3 = _dec_v3(c)
    if v3 is not None:
        return _requote_v3(w3, chain, v3)
    v2 = _dec_v2(c)
    if v2 is not None:
        return _q._v2_out(w3, chain, v2[0], v2[1])
    return None

def _base_out(w3, chain, plan):
    """Re-quoted delivery of the engine's plan: 0 if empty, int if decodable,
    None if non-empty but undecodable (defer)."""
    ix = getattr(plan, 'interactions', None) if plan else None
    if not ix:
        return 0
    cd = ix[-1].call_data or ''
    c = cd if cd.startswith('0x') else '0x' + cd
    return _requote_ix(w3, chain, c)

def _chain_of(state, snapshot):
    return int(getattr(state, 'chain_id', 0) or (getattr(snapshot, 'chain_id', 0) if snapshot else 0) or 0)

def _swap_triple(solver, intent, state):
    """(tin, tout, amt, params) for this swap, or None if unusable."""
    p = solver._normalized_swap_params(intent, state)
    tin = str(p.get('input_token', '') or '').lower()
    tout = str(p.get('output_token', '') or '').lower()
    amt = int(p.get('input_amount', 0) or 0)
    if not tin or not tout or amt <= 0:
        return None
    return (tin, tout, amt, p)

def _cover_ctx(solver, intent, state, snapshot):
    """(chain, tin, tout, amt, w3, p) for a coverable order, or None to defer."""
    chain = _chain_of(state, snapshot)
    if _q._QUOTERS.get(chain) is None:
        return None
    trip = _swap_triple(solver, intent, state)
    if trip is None:
        return None
    tin, tout, amt, p = trip
    w3 = solver._get_web3(chain)
    if w3 is None:
        return None
    return (chain, tin, tout, amt, w3, p)

def _providers():
    import viking_v4 as _v4
    import viking_curve as _cv
    return (_qb.candidates, _pcs.pcs_candidates, _v4.v4_candidates, _cv.curve_candidates)

def _best_lift(w3, chain, tin, tout, amt, floor):
    """Best strict-better candidate over the union of every venue's candidates
    (Uni V3/V2, Pancake V3, V4 exact-key, Curve) — lift-only (a new venue can
    only raise the best), or None."""
    cands = []
    for fn in _providers():
        cands += fn(w3, chain, tin, tout, amt)
    if not cands:
        return None
    best = max(cands, key=lambda c: c[0])
    return best if best[0] > floor else None

def _floor(w3, chain, base_plan, state, tin, tout, amt, p):
    """Re-quoted base delivery; if undecodable (Universal Router / V4) fall back
    to an execution sim so the override compares against the REAL base output.
    MINOTAUR_NO_SIMFLOOR=1 restores the prior defer-on-undecodable behavior."""
    import os
    f = _base_out(w3, chain, base_plan)
    if f is None and os.environ.get('MINOTAUR_NO_SIMFLOOR', '') != '1':
        f = _sim.sim_floor(w3, base_plan, tin, tout, amt, _b._recipient(state, p))
    return f

def _lift_serve(w3, chain, tin, tout, amt, floor, intent, state, p):
    best = _best_lift(w3, chain, tin, tout, amt, floor)
    if best is None:
        return None
    return _b.serve(intent, state, chain, tin, tout, best, amt, p)

def _serve_cascade(ctx, floor, intent, state):
    """Venue lift first, aToken wrap cover second — both floor-gated."""
    import viking_aave as _av
    chain, tin, tout, amt, w3, p = ctx
    plan = _lift_serve(w3, chain, tin, tout, amt, floor, intent, state, p)
    if plan is not None:
        return plan
    return _av.lift(ctx, floor, intent, state)

def _cover(solver, intent, state, snapshot, base_plan):
    ctx = _cover_ctx(solver, intent, state, snapshot)
    if ctx is None:
        return None
    chain, tin, tout, amt, w3, p = ctx
    floor = _floor(w3, chain, base_plan, state, tin, tout, amt, p)
    if floor is None:
        return None
    return _serve_cascade(ctx, floor, intent, state)

def v3hop_cover(solver, intent, state, snapshot, base_plan):
    """Serve the best V3/V2 route ONLY when it strictly beats the re-quoted base."""
    try:
        return _cover(solver, intent, state, snapshot, base_plan)
    except Exception:
        logger.exception('[v3hop] cover failed; serving base plan')
        return None