"""Live single-hop quote sweep — the champion's `_enumerate_singlehop_quotes`
(king_base.py:3338) without the `_dr*` wrapper scaffolding.

Every quoter eth_call is fired CONCURRENTLY and each returns 0/None rather than
raising: a reverting venue simply can't fill, and a slow one must cost at most
itself, never the whole selection. Sequentially these serialize to ~9 * 2s under
a slow RPC and blow the 12s select budget.

Candidate shape (identical to the lineage, so scoring ports unchanged):
    {"venue": str, "param": int, "out": int, "gas_est": int, "gas_model": int}
"""
from __future__ import annotations
import cr_consts as consts
from cr_abi_util import _call, _selectors, encode_path

def _single_spec(kind):
    """(tuple-sig, venue name, gas offset) for a single-hop quoter family.

    Uniswap types the tier as uint24 `fee`; Aerodrome as int24 `tickSpacing`.
    """
    gas = consts.gas_model()
    if kind == 'uni':
        return ('(address,address,uint256,uint24,uint160)', 'uniswap_v3', gas['offset_uni'])
    return ('(address,address,uint256,int24,uint160)', 'aerodrome_slipstream', gas['offset_aero'])

def _single_payload(sig, tin, tout, amount, param):
    """ABI-encode the exactInputSingle quoter tuple."""
    from eth_abi import encode
    from eth_utils import to_checksum_address as ck
    return encode([sig], [(ck(tin), ck(tout), int(amount), int(param), 0)])

def _single_out(w3, kind, sig, tin, tout, amount, param, chain_id):
    """Fire one exactInputSingle quote -> (out, gas_est). (0, 0) on any failure.

    A venue family absent on this chain (no Aerodrome on Ethereum) has no
    quoter address and simply yields no candidate.
    """
    from eth_abi import decode
    quoter = consts.quoters(chain_id).get(kind)
    if not quoter:
        return (0, 0)
    try:
        raw = _call(w3, quoter, _selectors()[kind] + _single_payload(sig, tin, tout, amount, param))
        out, _sqrt, _ticks, gas_est = decode(['uint256', 'uint160', 'uint32', 'uint256'], raw)
    except Exception:
        return (0, 0)
    return (int(out), int(gas_est))

def _single(w3, kind, tin, tout, amount, param, chain_id=8453):
    """One exactInputSingle quote (uniswap_v3 | aerodrome_slipstream)."""
    sig, venue, offset = _single_spec(kind)
    out, gas_est = _single_out(w3, kind, sig, tin, tout, amount, param, chain_id)
    if out <= 0:
        return None
    return {'venue': venue, 'param': int(param), 'out': out, 'gas_est': gas_est, 'gas_model': offset + gas_est}

def _multihop_out(w3, kind, tokens, params, amount, chain_id):
    """Fire one packed-path exactInput quote -> (out, gas_est). (0, 0) on failure.

    QuoterV2.quoteExactInput returns
    (amountOut, sqrtPriceX96AfterList[], initializedTicksCrossedList[], gasEstimate).
    amountOut leads, so the first word is the output on every chain; the trailing
    gasEstimate needs the full decode. Taking only the first word and modelling
    gas as a flat constant makes every multi-hop look equally expensive, which
    silently disables any gas-aware choice between them (king_base.py:2665 reads
    the real estimate).
    """
    from eth_abi import decode, encode
    quoter = consts.quoters(chain_id).get(kind)
    if not quoter:
        return (0, 0)
    try:
        payload = encode(['bytes', 'uint256'], [encode_path(tokens, params), int(amount)])
        raw = _call(w3, quoter, _selectors()['uni_path'] + payload)
    except Exception:
        return (0, 0)
    if len(raw) < 32:
        return (0, 0)
    return _decode_multihop(raw)

def _decode_multihop(raw):
    """(amountOut, gasEstimate) from a quoteExactInput return; gas 0 if absent."""
    from eth_abi import decode
    try:
        out, _sqrt, _ticks, gas_est = decode(['uint256', 'uint160[]', 'uint32[]', 'uint256'], raw)
        return (int(out), int(gas_est))
    except Exception:
        pass
    try:
        return (int(decode(['uint256'], raw[:32])[0]), 0)
    except Exception:
        return (0, 0)

def _multihop(w3, kind, tokens, params, amount, chain_id=8453):
    """One exactInput (packed-path) quote across a 2-hop route."""
    out, gas_est = _multihop_out(w3, kind, tokens, params, amount, chain_id)
    if out <= 0:
        return None
    base = consts.gas_model()['multihop']
    gas_model = base + gas_est if gas_est else base
    venue = 'uniswap_v3_multihop' if kind == 'uni' else 'aerodrome_slipstream_multihop'
    return {'venue': venue, 'param': tuple(params), 'out': out, 'gas_est': gas_est or base, 'gas_model': gas_model, 'mid': tokens[1]}


def _v2_amounts_out(w3, router, path, amount):
    """Uniswap-V2 getAmountsOut(amountIn, path) -> final output wei (0 on fail)."""
    from eth_abi import decode, encode
    from eth_utils import to_checksum_address as ck
    payload = encode(['uint256', 'address[]'], [int(amount), [ck(t) for t in path]])
    raw = _call(w3, router, _selectors()['uni_v2'] + payload)
    if not raw:
        return 0
    amounts = decode(['uint256[]'], raw)[0]
    return int(amounts[-1]) if amounts else 0


def _v2_gas(mid) -> int:
    """Gas model for a V2 quote — the 2-hop offset when routed through a mid."""
    gm = consts.gas_model()
    return gm['multihop'] if mid else gm['offset_uni']


def _v2_cand(out, path, mid) -> dict:
    """Assemble the candidate dict for a filled V2 quote."""
    cand = {'venue': 'uniswap_v2', 'param': tuple(path), 'out': int(out),
            'gas_est': 0, 'gas_model': _v2_gas(mid)}
    if mid:
        cand['mid'] = mid
    return cand


def _v2(w3, tin, tout, amount, chain_id, mid=None):
    """A Uniswap-V2 quote over [tin, tout] (direct) or [tin, mid, tout] (2-hop)."""
    router = consts.v2_routers(chain_id).get('uniswap_v2')
    if not router:
        return None
    path = [tin, mid, tout] if mid else [tin, tout]
    try:
        out = _v2_amounts_out(w3, router, path, amount)
    except Exception:
        return None
    return _v2_cand(out, path, mid) if out > 0 else None