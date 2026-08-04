# chain-1 dynamic tier: quoting + v3 building helpers
from chain1_c import _WETH, _USDT, _QUOTER, _ROUTER, _FEES, _HUBS, _CHAMP_FEE

def _pack(tokens, fees):
    """V3 path bytes: token[,fee,token]... Accumulated into a list and joined once rather
    than by repeated `+=`, which reallocates the whole buffer on every leg."""
    parts = []
    for i, t in enumerate(tokens):
        parts.append(bytes.fromhex(str(t).removeprefix('0x')))
        if i < len(fees):
            parts.append(int(fees[i]).to_bytes(3, 'big'))
    return b''.join(parts)

def _champ_route(tin, tout):
    fs = frozenset((tin, tout))
    if fs in _CHAMP_FEE:
        return ((tin, tout), (_CHAMP_FEE[fs],))
    if _WETH not in (tin, tout):
        f1 = _CHAMP_FEE.get(frozenset((tin, _WETH)), 3000)
        f2 = _CHAMP_FEE.get(frozenset((_WETH, tout)), 3000)
        return ((tin, _WETH, tout), (f1, f2))
    return ((tin, tout), (3000,))

def _candidates(tin, tout):
    """Every direct and single-hub route, in a FIXED order.

    Order is load-bearing, not cosmetic: downstream selection keeps the first candidate at
    the best quote, so two routes that quote equal are resolved by position here. product()
    varies its rightmost operand fastest, which is exactly what the nested `for fa: for fb:`
    did, so the sequence is unchanged -- see the exhaustive order check in the delta proof.
    """
    from itertools import product
    out = [((tin, tout), (f,)) for f in _FEES]
    out.extend(((tin, hub, tout), (fa, fb))
               for hub, fa, fb in product(_HUBS, _FEES, _FEES)
               if hub not in (tin, tout))
    return out

def _abi_call(sig, types, values):
    """Calldata: the 4-byte selector of `sig`, then `values` ABI-encoded as `types`.

    _qdata and _swap_leg each open-coded this same keccak-slice / encode / hex sequence with
    their own local imports. Keeping the signature string next to its type list in ONE place
    is the point: when those two drift apart the call does not raise, it builds a well-formed
    request against the wrong selector and comes back as a revert at bench.
    """
    from eth_abi import encode as _enc
    from eth_utils import keccak as _keccak
    return '0x' + (_keccak(text=sig)[:4] + _enc(types, values)).hex()

def _qdata(route, amt):
    tokens, fees = route
    return _abi_call('quoteExactInput(bytes,uint256)',
                     ['bytes', 'uint256'], [_pack(tokens, fees), int(amt)])

def _qroute(w3, route, amt, block):
    try:
        from eth_abi import decode as _dec
        from eth_utils import to_checksum_address as _ck
        r = w3.eth.call({'to': _ck(_QUOTER), 'data': _qdata(route, amt)}, block_identifier=block)
        return _dec(['uint256', 'uint160[]', 'uint32[]', 'uint256'], r)[0] or None
    except Exception:
        return None

def _swap_leg(route, amt, rcpt):
    from eth_utils import to_checksum_address as _ck
    tokens, fees = route
    return _abi_call('exactInput((bytes,address,uint256,uint256,uint256))',
                     ['(bytes,address,uint256,uint256,uint256)'],
                     [(_pack(tokens, fees), _ck(rcpt), 9999999999, int(amt), 0)])

def _approves(tin, amt, chain_id):
    from eth_utils import to_checksum_address as _ck
    from common.abi_utils import encode_approve
    from minotaur_subnet.shared.types import Interaction as _IX
    ixs = []
    if tin == _USDT:
        ixs.append(_IX(target=tin, value='0', call_data=encode_approve(_ck(_ROUTER), 0), chain_id=chain_id))
    ixs.append(_IX(target=tin, value='0', call_data=encode_approve(_ck(_ROUTER), int(amt)), chain_id=chain_id))
    return ixs

def _build(route, tin, amt, rcpt, chain_id):
    from minotaur_subnet.shared.types import Interaction as _IX
    leg = _swap_leg(route, amt, rcpt)
    return _approves(tin, amt, chain_id) + [_IX(target=_ROUTER, value='0', call_data=leg, chain_id=chain_id)]

def _amounts(p):
    amt = int(p.get('input_amount', 0) or 0)
    mo = int(p.get('min_output_amount', 0) or 0)
    return amt, mo

_ADDR_LEN = 42          # '0x' + 40 hex characters


def _token(p, field):
    """One token address off the normalised params: never None, always lower-cased.

    The two call sites differed only in the key, and both had to repeat the default-then-`or`
    dance because `_normalized_swap_params` can return the key present-but-None.
    """
    return str(p.get(field, '') or '').lower()


def _routable(tin, tout, amt):
    """Whether the dynamic tier can attempt this order at all.

    Was one four-clause condition in which the two length checks read as noise around the two
    that carry meaning. They are not noise: a short or empty address does NOT raise downstream,
    it packs a malformed V3 path whose quote reverts, so the row is silently lost instead of
    cleanly skipped. Naming the predicate keeps that reason attached to the check.
    """
    return (len(tin) == _ADDR_LEN and len(tout) == _ADDR_LEN
            and amt > 0 and tin != tout)


def _params(s, intent, state):
    p = s._normalized_swap_params(intent, state)
    tin, tout = _token(p, 'input_token'), _token(p, 'output_token')
    amt, mo = _amounts(p)
    if not _routable(tin, tout, amt):
        return None
    return (tin, tout, amt, mo)
