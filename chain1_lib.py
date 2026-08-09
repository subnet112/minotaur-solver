from chain1_c import _WETH, _USDT, _QUOTER, _ROUTER, _FEES, _HUBS, _CHAMP_FEE
from chain1_appr_ext import _needs_reset_approve
from chain1_dleg_ext import _direct_legs
from chain1_appr2_ext import _approves
from chain1_abytes_ext import _addr_bytes

def _pack(tokens, fees):
    b = b''
    for i, t in enumerate(tokens):
        b += _addr_bytes(t)
        if i < len(fees):
            b += int(fees[i]).to_bytes(3, 'big')
    return b

def _champ_fee(a, b):
    return _CHAMP_FEE.get(frozenset((a, b)), 3000)

def _champ_route(tin, tout):
    fs = frozenset((tin, tout))
    if fs in _CHAMP_FEE:
        return ((tin, tout), (_CHAMP_FEE[fs],))
    if _WETH not in (tin, tout):
        return ((tin, _WETH, tout), (_champ_fee(tin, _WETH), _champ_fee(_WETH, tout)))
    return ((tin, tout), (3000,))

def _usable_hubs(tin, tout):
    return [hub for hub in _HUBS if hub not in (tin, tout)]

def _hub_legs(tin, tout):
    out = []
    for hub in _usable_hubs(tin, tout):
        for fa in _FEES:
            for fb in _FEES:
                out.append(((tin, hub, tout), (fa, fb)))
    return out

def _candidates(tin, tout):
    return _direct_legs(tin, tout) + _hub_legs(tin, tout)

def _selector(sig):
    from eth_utils import keccak as _keccak
    return _keccak(text=sig)[:4]

def _qdata(route, amt):
    from eth_abi import encode as _enc
    tokens, fees = route
    sel = _selector('quoteExactInput(bytes,uint256)')
    return '0x' + (sel + _enc(['bytes', 'uint256'], [_pack(tokens, fees), int(amt)])).hex()

def _quoted_amount(blob):
    from eth_abi import decode as _dec
    return _dec(['uint256', 'uint160[]', 'uint32[]', 'uint256'], blob)[0] or None

def _qroute(w3, route, amt, block):
    try:
        from eth_utils import to_checksum_address as _ck
        r = w3.eth.call({'to': _ck(_QUOTER), 'data': _qdata(route, amt)}, block_identifier=block)
        return _quoted_amount(r)
    except Exception:
        return None

def _swap_leg(route, amt, rcpt):
    from eth_abi import encode as _enc
    from eth_utils import to_checksum_address as _ck
    tokens, fees = route
    sel = _selector('exactInput((bytes,address,uint256,uint256,uint256))')
    return '0x' + (sel + _enc(['(bytes,address,uint256,uint256,uint256)'], [(_pack(tokens, fees), _ck(rcpt), 9999999999, int(amt), 0)])).hex()

def _build(route, tin, amt, rcpt, chain_id):
    from minotaur_subnet.shared.types import Interaction as _IX
    leg = _swap_leg(route, amt, rcpt)
    return _approves(tin, amt, chain_id) + [_IX(target=_ROUTER, value='0', call_data=leg, chain_id=chain_id)]

def _wei(p, field):
    return int(p.get(field, 0) or 0)

def _amounts(p):
    return (_wei(p, 'input_amount'), _wei(p, 'min_output_amount'))

def _valid_pair(tin, tout, amt):
    return len(tin) == 42 and len(tout) == 42 and (amt > 0) and (tin != tout)

def _token(p, field):
    return str(p.get(field, '') or '').lower()

def _params(s, intent, state):
    p = s._normalized_swap_params(intent, state)
    tin = _token(p, 'input_token')
    tout = _token(p, 'output_token')
    amt, mo = _amounts(p)
    if not _valid_pair(tin, tout, amt):
        return None
    return (tin, tout, amt, mo)