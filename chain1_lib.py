# chain-1 dynamic tier: quoting + v3 building helpers
from chain1_c import _WETH, _USDT, _QUOTER, _ROUTER, _FEES, _HUBS, _CHAMP_FEE

def _pack(tokens, fees):
    b = b''
    for i, t in enumerate(tokens):
        b += bytes.fromhex(t[2:])
        if i < len(fees):
            b += int(fees[i]).to_bytes(3, 'big')
    return b

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
    out = [((tin, tout), (f,)) for f in _FEES]
    for hub in _HUBS:
        if hub in (tin, tout):
            continue
        for fa in _FEES:
            for fb in _FEES:
                out.append(((tin, hub, tout), (fa, fb)))
    return out

def _qdata(route, amt):
    from eth_abi import encode as _enc
    from eth_utils import keccak as _keccak
    tokens, fees = route
    sel = _keccak(text='quoteExactInput(bytes,uint256)')[:4]
    return '0x' + (sel + _enc(['bytes', 'uint256'], [_pack(tokens, fees), int(amt)])).hex()

def _qroute(w3, route, amt, block):
    try:
        from eth_abi import decode as _dec
        from eth_utils import to_checksum_address as _ck
        r = w3.eth.call({'to': _ck(_QUOTER), 'data': _qdata(route, amt)}, block_identifier=block)
        return _dec(['uint256', 'uint160[]', 'uint32[]', 'uint256'], r)[0] or None
    except Exception:
        return None

def _swap_leg(route, amt, rcpt):
    from eth_abi import encode as _enc
    from eth_utils import keccak as _keccak, to_checksum_address as _ck
    tokens, fees = route
    sel = _keccak(text='exactInput((bytes,address,uint256,uint256,uint256))')[:4]
    return '0x' + (sel + _enc(['(bytes,address,uint256,uint256,uint256)'], [(_pack(tokens, fees), _ck(rcpt), 9999999999, int(amt), 0)])).hex()

def _needs_reset_approve(tin):
    """Whether `tin` must be approved to 0 before being approved to the real amount.

    USDT's approve() reverts outright when it would move a NON-ZERO allowance to another
    non-zero value -- it is not ERC-20 compliant on that path. Every other token in the
    corpus overwrites its allowance happily, so the extra interaction is spent only where it
    is load-bearing.

    The failure mode this guards is quiet and expensive: the approve reverts, the whole plan
    reverts with it, and the row scores as a delivery failure rather than as anything that
    points at an allowance. Naming the condition keeps the reason attached to the test, which
    a bare `tin == _USDT` beside a zero-amount approve does not.
    """
    return tin == _USDT


def _approves(tin, amt, chain_id):
    from eth_utils import to_checksum_address as _ck
    from common.abi_utils import encode_approve
    from minotaur_subnet.shared.types import Interaction as _IX
    ixs = []
    if _needs_reset_approve(tin):
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

def _params(s, intent, state):
    p = s._normalized_swap_params(intent, state)
    tin = str(p.get('input_token', '') or '').lower()
    tout = str(p.get('output_token', '') or '').lower()
    amt, mo = _amounts(p)
    if len(tin) != 42 or len(tout) != 42 or amt <= 0 or tin == tout:
        return None
    return (tin, tout, amt, mo)
