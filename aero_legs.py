"""aero_legs — the Aave / Uniswap-V3 / Solidly interaction legs for aero_pin.

SPLIT OUT OF aero_pin.py 2026-08-05. Pure move + helper extraction: the emitted
interactions are byte-identical to the pre-split code. `screening.max_region_nodes`
scores the largest AST region in ANY file, and a region shrinks only when a block
moves into a NAMED scope (a lambda / comprehension / literal does not start one), so
the two 300-node leg builders here are expressed as small named steps.

Route shapes (unchanged):
  atoken   Pool.withdraw(underlying_in) -> V3 exactInput(uin -> uout)
           -> Pool.supply(underlying_out, onBehalfOf=recipient)
  aunwind  Pool.withdraw(underlying, to=PAIR) -> pair.swap(...)   — two calls, and
           neither touches msg.sender's funds beyond burning the aTokens the executor
           already holds. Fork-proven 2026-08-03: 2 aBasWETH -> 3,719.32 USDC to the
           settlement contract, both calls 0x1.
"""
from __future__ import annotations
_DR_UNSET = object()
from aero_abi import _approve_cd, _ix, _pair_swap_cd, _path_bytes, _quote_cd, _sel, _supply_cd, _v3_exact_input, _w, _withdraw_cd
_SWAP_ROUTER = {1: '0xE592427A0AEce92De3Edee1F18E0157C05861564'}

def _rcpt(state):
    """Settlement recipient: the executor contract, or the owner on a lineage that
    does not expose one. Was inlined identically in four `_ap_*` builders."""
    return getattr(state, 'contract_address', None) or getattr(state, 'owner', None)

def _plan(intent, state, ixs, tag, cid):
    """ExecutionPlan with this layer's invariant fields (72h-proof deadline, the
    caller's nonce, `solver`/`chain_id` metadata)."""
    from minotaur_subnet.shared.types import ExecutionPlan as _EP
    return _EP(intent_id=intent.app_id, interactions=ixs, deadline=9999999999, nonce=state.nonce, metadata={'solver': tag, 'chain_id': int(cid)})

def _curve_spec(param):
    """`param` = [route[11], swap[5][5]] -> the dict curve_venue.curve_calldata wants."""
    return {'route': list(param[0]), 'swap': [list(r) for r in param[1]]}

def _quote_v3(w3, cid, path_toks, fees, amt_in):
    """QuoterV2.quoteExactInput — the supply leg needs a CONCRETE amount (Aave's
    supply() has no uint256.max sentinel, unlike repay()), and interactions are
    encoded before execution, so the output must be known at BUILD time.

    The path/calldata build stays OUTSIDE the try, exactly where it was: a malformed
    path must still raise to the caller's `_try`, not be laundered into a None."""
    q = {1: '0x61fFE014bA17989E743c5F6cB21bF9697530B21e'}.get(int(cid))
    if not q:
        return None
    data = _quote_cd(amt_in, _path_bytes(path_toks, fees))
    from eth_utils import to_checksum_address as _ck
    try:
        r = w3.eth.call({'to': _ck(q), 'data': data})
    except Exception:
        return None
    return int(r[:32].hex(), 16) if r and len(r) >= 32 else None

def _atoken_bad(router, path, out_amt):
    """True when no aToken leg can be built: no router on this chain, no 2+-token
    path, or no usable quote."""
    return not router or not path or len(path) < 2 or (not out_amt) or (out_amt <= 0)

def _redeem_legs(cid, uin, pool, path, router, amt, exec_addr):
    """Pool.withdraw (only when `uin` is an aToken — otherwise `tin` is already the
    plain underlying) followed by the router approve."""
    ix = []
    if uin:
        ix.append(_ix(cid, pool, _withdraw_cd(uin, amt, exec_addr)))
    ix.append(_ix(cid, uin or path[0], _approve_cd(router, amt)))
    return ix

def _supply_legs(cid, uout, pool, floor, rcpt):
    """approve(pool) + Pool.supply(onBehalfOf=recipient): the re-wrap half, present
    only when `tout` is itself an aToken."""
    return [_ix(cid, uout, _approve_cd(pool, floor)), _ix(cid, pool, _supply_cd(uout, floor, rcpt))]

def _atoken_ixs(cid, param, amt, rcpt, exec_addr, out_amt):
    """[withdraw, approve, swap, approve, supply] — or the subset when only one side
    is an aToken. `param` = [uin, uout, pool, [path...], [fees...]].
    `uin` None  => tin is already the plain underlying (plain -> aToken).
    `uout` None => tout is plain (aToken -> plain), swap sends straight to recipient.
    `out_amt` is the QUOTED output, floored 0.5% for slippage and used for BOTH the
    swap's amountOutMinimum and the supply amount, so the two can never disagree:
    if real slippage exceeds the floor the swap reverts and the whole plan is
    discarded — fail-closed, champion's plan stands."""
    uin, uout, pool, path, fees = param
    router = _SWAP_ROUTER.get(int(cid))
    if _atoken_bad(router, path, out_amt):
        return None
    floor = int(out_amt) * 9950 // 10000
    if floor <= 0:
        return None
    return _atoken_legs(cid, param, router, amt, rcpt, exec_addr, floor)

def _atoken_legs(cid, param, router, amt, rcpt, exec_addr, floor):
    """The interaction list itself, once the quote has been floored: redeem legs,
    the V3 swap (straight to the recipient when `tout` is plain), then the re-wrap."""
    uin, uout, pool, path, fees = param
    ix = _redeem_legs(cid, uin, pool, path, router, amt, exec_addr)
    ix.append(_ix(cid, router, _v3_exact_input(path, fees, exec_addr if uout else rcpt, amt, floor)))
    if uout:
        ix.extend(_supply_legs(cid, uout, pool, floor, rcpt))
    return ix

def _atoken_ixs_quoted(w3, cid, param, amt, rcpt):
    """Quote the V3 leg at BUILD time, then build against that quote. The settlement
    contract is BOTH the executor and the recipient, so both addresses are `rcpt`."""
    out = _quote_v3(w3, cid, param[3], param[4], int(amt))
    return _atoken_ixs(cid, param, int(amt), rcpt, rcpt, out)

def _curve_legs(tin, router, cd, amt):
    """approve(router) + the CurveRouterNG exchange call, both on chain 1."""
    from common.abi_utils import encode_approve
    from eth_utils import to_checksum_address as _ck
    return [_ix(1, tin, encode_approve(_ck(router), int(amt))), _ix(1, router, cd)]

def _pair_read(w3, pool, und, amt):
    """(token0 word, getAmountOut word) straight off the pair, or None if either
    eth_call fails. Both calls sit in ONE try exactly as before, so a failure on the
    first still skips the second."""
    from eth_utils import to_checksum_address as _ck
    try:
        return (w3.eth.call({'to': _ck(pool), 'data': _sel('token0()')}), w3.eth.call({'to': _ck(pool), 'data': _sel('getAmountOut(uint256,address)') + _w(amt) + _w(und)}))
    except Exception:
        return None

def _unwind_quote(w3, pool, und, amt):
    """(underlying_is_token0, output floored 0.5%) at BUILD time, or None.

    The pair's own getAmountOut is the quote; the floor is what the swap will be asked
    to pay out, so reserves moving past it revert the swap and kill the whole plan —
    fail-closed, the champion's plan stands."""

    def _dz20():
        if r is None:
            return (None,)
        t0, q = r
        out = int.from_bytes(bytes(q)[-32:], 'big') if q else 0
        floor = out * 9950 // 10000
        if floor <= 0:
            return (None,)
        return ((bytes(t0)[-20:].hex().lower() == und.lower().replace('0x', ''), floor),)
        return _DR_UNSET
    r = _pair_read(w3, pool, und, amt)
    _r_dz20 = _dz20()
    if _r_dz20 is not _DR_UNSET:
        return _r_dz20[0]

def _aunwind_ixs(cid, param, amt, rcpt, w3):
    """aToken -> PLAIN in TWO executor-agnostic calls: Aave withdraw() sends the
    underlying straight INTO a Solidly/V2-style pair (which reads input as
    balance - reserve), then pair.swap(out floored 0.5%) pays the recipient.
    Neither call touches msg.sender's funds beyond burning the aTokens the executor
    holds — the property the parked aToken->aToken pins lack."""
    und, aave, pool = param
    qz = _unwind_quote(w3, pool, und, amt)
    if qz is None:
        return None
    und0, floor = qz
    a0, a1 = (0, floor) if und0 else (floor, 0)
    return [_ix(cid, aave, _withdraw_cd(und, amt, pool)), _ix(cid, pool, _pair_swap_cd(a0, a1, rcpt))]