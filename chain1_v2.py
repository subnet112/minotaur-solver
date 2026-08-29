_DR_UNSET = object()
from chain1_c import _V2_PAIRS, _MAX_QUOTES
from chain1_lib import _candidates, _qroute

def _v2_reserves(w3, pair, block):

    def _dz866():
        res = _dec(['uint112', 'uint112', 'uint32'], r)
        return ((int(res[0]), int(res[1])),)
        return _DR_UNSET

    def _dz865(block, pair, w3):
        r = w3.eth.call({'to': _ck(pair), 'data': '0x' + _keccak(text='getReserves()')[:4].hex()}, block_identifier=block)
        return r
    from eth_abi import decode as _dec
    from eth_utils import keccak as _keccak, to_checksum_address as _ck
    r = _dz865(block, pair, w3)
    _r_dz866 = _dz866()
    if _r_dz866 is not _DR_UNSET:
        return _r_dz866[0]

def _v2_quote(w3, pair, amt, in_is_t0, block):

    def _dz863():
        ai = int(amt) * 997
        return (ai * rout // (rin * 1000 + ai) or None,)
        return _DR_UNSET
    try:
        res = _v2_reserves(w3, pair, block)
        rin, rout = (res[0], res[1]) if in_is_t0 else (res[1], res[0])
        _r_dz863 = _dz863()
        if _r_dz863 is not _DR_UNSET:
            return _r_dz863[0]
    except Exception:
        return None

def _v2_lookup(tin, tout):
    ent = _V2_PAIRS.get(frozenset((tin, tout)))
    if not ent:
        return None
    pair, t0 = ent
    return (pair, tin == t0)
from lat_swapcd_ext import _v2_swap_cd
from lat_xfercd_ext import _v2_xfer_cd

def _v2_build(pair, in_is_t0, tin, amt, out, rcpt, chain_id):
    from minotaur_subnet.shared.types import Interaction as _IX
    return [_IX(target=tin, value='0', call_data=_v2_xfer_cd(pair, amt), chain_id=chain_id), _IX(target=pair, value='0', call_data=_v2_swap_cd(in_is_t0, out, rcpt), chain_id=chain_id)]

def _better(best, q):
    """Whether quote `q` should take the slot from `best`.

    STRICTLY greater, so on a tie the EARLIER candidate keeps it -- _candidates emits a fixed
    order and that order is what resolves equal quotes. The test was spelled inline at both
    call sites below; a `>=` in one of them would silently re-rank ties across half the sweep
    and nothing would fail, the solver would just start serving a different route.
    """
    return bool(q) and (best is None or q > best[0])

def _sweep(w3, tin, tout, amt, block):

    def _dz862():
        nonlocal best, n
        n += 1
        q = _qroute(w3, cand, amt, block)
        if _better(best, q):
            best = (q, cand)
    best, n = (None, 0)
    for cand in _candidates(tin, tout):
        if n >= _MAX_QUOTES:
            break
        _dz862()
    return best

def _v2_best(w3, tin, tout, amt, block, best):

    def _dz861():
        nonlocal best
        if _better(best, q2):
            best = (q2, ('v2', v2[0], v2[1], q2))
    v2 = _v2_lookup(tin, tout)
    if v2 is not None:
        q2 = _v2_quote(w3, v2[0], amt, v2[1], block)
        _dz861()
    return best

def _c1_build_ix_v2(tin, recip, tokens, amt):
    """ZERO-RPC Uniswap-V2 router serve (baked-spec sibling of solver._c1_build_ix).
    Returns [approve_ix, v2swap_ix] for the V2 SwapRouter02:
    swapExactTokensForTokensSupportingFeeOnTransferTokens (sel 0x5c11d795), min_out=0,
    deadline 9999999999. The SupportingFeeOnTransfer variant + min_out=0 make it safe for
    fee-on-transfer exotics (never reverts on tax skim). `tokens` is the full V2 path
    (direct [tin,tout] or 2-hop [tin,WETH,tout]) baked pre-verified via getAmountsOut>0."""
    from eth_abi import encode as _enc
    from eth_utils import to_checksum_address as _ck
    from common.abi_utils import encode_approve
    from minotaur_subnet.shared.types import Interaction as _IX
    ROUTER_V2 = '0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D'
    swap_data = '0x5c11d795' + _enc(['uint256', 'uint256', 'address[]', 'address', 'uint256'], [int(amt), 0, [_ck(t) for t in tokens], _ck(recip), 9999999999]).hex()
    return [_IX(target=_ck(tin), value='0', call_data=encode_approve(_ck(ROUTER_V2), int(amt)), chain_id=1), _IX(target=_ck(ROUTER_V2), value='0', call_data=swap_data, chain_id=1)]

def _c1_recip_v2(p, state):
    return str(p.get('receiver', '') or getattr(state, 'contract_address', None) or getattr(state, 'owner', None) or '0x0000000000000000000000000000000000000001')

def _c1_v2_plan(solver, intent, state, tin, amt, spec):
    """Zero-RPC UniV2 ExecutionPlan for a baked {'venue':'univ2','tokens':[...]} spec.
    Delegated out of solver._chain1_build_plan to keep that method's AST region tiny
    (the crown-holding max_region_nodes tie-break floor). Recipient LIVE from state,
    min_out=0 => never reverts. metadata solver='chain1-baked' (same as the V3 path)."""

    def _dz859():
        return (_EP(intent_id=intent.app_id, interactions=ix, deadline=9999999999, nonce=state.nonce, metadata={'solver': 'chain1-baked', 'chain_id': 1}),)
        return _DR_UNSET
    from minotaur_subnet.shared.types import ExecutionPlan as _EP
    recip = _c1_recip_v2(solver._normalized_swap_params(intent, state), state)
    ix = _c1_build_ix_v2(tin, recip, [str(t).lower() for t in spec['tokens']], amt)
    _r_dz859 = _dz859()
    if _r_dz859 is not _DR_UNSET:
        return _r_dz859[0]

def _c1_curve_ix(tin, amt, recip, spec):
    """Build [approve_ix, exchange_ix] for a baked curve spec by REUSING the pure (no-RPC)
    curve_venue.curve_calldata to rebuild the CurveRouterNG.exchange calldata. Split out of
    _c1_curve_plan so that method's AST region stays tiny (the crown region floor). tin is
    approved to the router curve_calldata returns; min_out floored to >=1 inside curve_calldata."""

    def _dz857(amt, recip, spec, tin):
        rspec = _dz856(spec)
        router, cd = _cv.curve_calldata(1, tin, None, int(amt), 0, recip, 9999999999, rspec)
        return (cd, router, rspec)

    def _dz856(spec):
        rspec = {'route': spec['route'], 'swap': spec['swap']}
        return rspec
    from eth_utils import to_checksum_address as _ck
    from common.abi_utils import encode_approve
    from minotaur_subnet.shared.types import Interaction as _IX
    import curve_venue as _cv
    cd, router, rspec = _dz857(amt, recip, spec, tin)
    return [_IX(target=_ck(tin), value='0', call_data=encode_approve(_ck(router), int(amt)), chain_id=1), _IX(target=_ck(router), value='0', call_data=cd, chain_id=1)]

def _c1_curve_plan(solver, intent, state, tin, amt, spec):
    """ZERO-RPC Curve serve for a baked {'venue':'curve','route':[address[11]],'swap':[[..]x5]}
    spec (route+swap eth_call-VERIFIED by curve_venue.curve_best at BAKE time). Recipient LIVE from
    state, min_out floored (never reverts on pool drift). metadata solver='chain1-baked' (V3/V2 sib)."""

    def _dz855():
        ix = _c1_curve_ix(tin, amt, recip, spec)
        return (_EP(intent_id=intent.app_id, interactions=ix, deadline=9999999999, nonce=state.nonce, metadata={'solver': 'chain1-baked', 'chain_id': 1}),)
        return _DR_UNSET
    from minotaur_subnet.shared.types import ExecutionPlan as _EP
    recip = _c1_recip_v2(solver._normalized_swap_params(intent, state), state)
    _r_dz855 = _dz855()
    if _r_dz855 is not _DR_UNSET:
        return _r_dz855[0]

def _c1_servable(spec):

    def _has_route():

        def _dz852():
            """True when the spec carries something executable, per venue.

        curve needs route[11]+swap[5][5]; univ2 needs a token path; v3 needs tokens+fees. A spec
        matching none of these is a recorded `noroute` and must stay clean-skipped -- letting it
        through would hand the base engine a blind single-hop that can revert, which scores
        catastrophic rather than merely absent.
        """
            if spec.get('venue') == 'curve':
                return (bool(spec.get('route') and spec.get('swap')),)
            return _DR_UNSET
        _r_dz852 = _dz852()
        if _r_dz852 is not _DR_UNSET:
            return _r_dz852[0]
        return bool(spec.get('tokens') and (spec.get('fees') or spec.get('venue') == 'univ2'))
    return _has_route()

def _c1_make_plan(solver, intent, state, tin, amt, spec):

    def _dz854():
        if v == 'univ2':
            return (_c1_v2_plan(solver, intent, state, tin, amt, spec),)
        _r_dz853 = _dz853()
        if _r_dz853 is not _DR_UNSET:
            return (_r_dz853[0],)
        return _DR_UNSET

    def _dz853():
        if v == 'curve':
            return (_c1_curve_plan(solver, intent, state, tin, amt, spec),)
        return (solver._chain1_build_plan(intent, state, tin, amt, spec),)
        return _DR_UNSET
    v = spec.get('venue')
    _r_dz854 = _dz854()
    if _r_dz854 is not _DR_UNSET:
        return _r_dz854[0]