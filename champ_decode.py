"""Decode the champion's ExecutionPlan and re-quote its route to get the exact
output it will deliver — so pick-max can override ONLY when our route provably
beats it. Strict: if ANY interaction is unrecognized, or the plan isn't a clean
single-swap we can fully decode, return None (=> defer to champion, never override
on an estimate we can't trust). champ_out is an EXACT on-fork quote (same block as
the sim), so comparing it to our exact quote is apples-to-apples.
"""
from __future__ import annotations
from eth_abi import decode as _dec
import router_cover as _rc
APPROVE = '095ea7b3'
S_V3_SINGLE_V1 = '414bf389'
S_V3_SINGLE_02 = '04e45aaf'
S_V3_PATH_V1 = 'c04b8d59'
S_V3_PATH_02 = 'b858183f'
S_V2 = '38ed1739'
S_V2_FOT = '5c11d795'
SWAPS = {S_V3_SINGLE_V1, S_V3_SINGLE_02, S_V3_PATH_V1, S_V3_PATH_02, S_V2, S_V2_FOT}
_SENTINEL = 1 << 255

def _sel(cd):
    return (cd[2:10] if cd.startswith('0x') else cd[:8]).lower()

def _body(cd):
    return bytes.fromhex(cd[10:] if cd.startswith('0x') else cd[8:])

def _split_v3_path(path: bytes):
    """tokenIn(20) [fee(3) token(20)]* -> (tokens, fees)."""
    tokens = ['0x' + path[0:20].hex()]
    fees, i = ([], 20)
    while i + 23 <= len(path):
        fees.append(int.from_bytes(path[i:i + 3], 'big'))
        tokens.append('0x' + path[i + 3:i + 23].hex())
        i += 23
    return (tokens, fees)

def _dec_v3_single_v1(body):
    tin, tout, fee, _r, _dl, amt, _m, _s = _dec(['address', 'address', 'uint24', 'address', 'uint256', 'uint256', 'uint256', 'uint160'], body)
    toks = ['0x' + tin, '0x' + tout] if not str(tin).startswith('0x') else [tin, tout]
    return (toks, [int(fee)], int(amt), 'v3')

def _dec_v3_single_02(body):
    tin, tout, fee, _r, amt, _m, _s = _dec(['address', 'address', 'uint24', 'address', 'uint256', 'uint256', 'uint160'], body)
    return ([tin, tout], [int(fee)], int(amt), 'v3')

def _dec_v3_path_v1(body):
    path, _r, _dl, amt, _m = _dec(['bytes', 'address', 'uint256', 'uint256', 'uint256'], body)
    toks, fees = _split_v3_path(path)
    return (toks, fees, int(amt), 'v3')

def _dec_v3_path_02(body):
    path, _r, amt, _m = _dec(['bytes', 'address', 'uint256', 'uint256'], body)
    toks, fees = _split_v3_path(path)
    return (toks, fees, int(amt), 'v3')

def _dec_v2(body):
    amt, _m, path, _to, _dl = _dec(['uint256', 'uint256', 'address[]', 'address', 'uint256'], body)
    return ([str(a) for a in path], [], int(amt), 'v2')

def _decode_swap(sel, body, input_amount):
    """Return (tokens, fees, amount_in, kind) or None. kind in {v3,v2}."""
    fn = _dec_v3_single_v1 if sel == S_V3_SINGLE_V1 else _dec_v3_single_02 if sel == S_V3_SINGLE_02 else _dec_v3_path_v1 if sel == S_V3_PATH_V1 else _dec_v3_path_02 if sel == S_V3_PATH_02 else _dec_v2 if sel in (S_V2, S_V2_FOT) else None
    if fn is None:
        return None
    try:
        return fn(body)
    except Exception:
        return None

def _collect_swaps(plan):
    """Swap legs of a plan as [(selector, body, target)], or None if any leg is not
    a recognised approve/swap (an unknown leg means we cannot trust an estimate)."""
    swaps = []
    for it in getattr(plan, 'interactions', None) or []:
        cd = getattr(it, 'call_data', '') or ''
        s = _sel(cd)
        if s == APPROVE:
            continue
        if s not in SWAPS:
            return None
        swaps.append((s, _body(cd), getattr(it, 'target', '')))
    return swaps

def _quote_decoded(dec, target, input_amount, chain_id, rpc):
    """Exact quote for a decoded route. Returns int (0 = the route is DEAD, which is
    meaningful: champion delivers 0 => our cover cannot drop it) or None if the shape
    is unsupported."""
    tokens, fees, amt, kind = dec
    if amt <= 0 or amt >= _SENTINEL:
        amt = int(input_amount)
    tokens = [t.lower() for t in tokens]
    cfg = _rc.CHAINS.get(int(chain_id))
    if not cfg:
        return None
    if kind == 'v3':
        if len(fees) == 1:
            return int(_rc.q_v3_single(rpc, cfg, tokens[0], tokens[-1], amt, fees[0]) or 0)
        return int(_rc.q_v3_path(rpc, cfg, tokens, fees, amt) or 0)
    if kind == 'v2':
        return int(_rc.q_v2(rpc, target, tokens, amt) or 0)
    return None

def champ_out(plan, input_amount, chain_id, rpc):
    """Exact output the champion's plan delivers, or None if not fully decodable."""
    try:
        swaps = _collect_swaps(plan)
        if not swaps or len(swaps) != 1:
            return None
        sel, body, target = swaps[0]
        dec = _decode_swap(sel, body, input_amount)
        if not dec:
            return None
        return _quote_decoded(dec, target, input_amount, chain_id, rpc)
    except Exception:
        return None