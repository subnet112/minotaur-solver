_DR_UNSET = object()
from chain1_c import _WETH, _USDT, _QUOTER, _ROUTER, _FEES, _HUBS, _CHAMP_FEE
from _vaddr_ext import _addr_bytes

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

    def _dz595():
        if _WETH not in (tin, tout):
            return (((tin, _WETH, tout), (_champ_fee(tin, _WETH), _champ_fee(_WETH, tout))),)
        return (((tin, tout), (3000,)),)
        return _DR_UNSET
    fs = frozenset((tin, tout))
    if fs in _CHAMP_FEE:
        return ((tin, tout), (_CHAMP_FEE[fs],))
    _r_dz595 = _dz595()
    if _r_dz595 is not _DR_UNSET:
        return _r_dz595[0]

def _direct_legs(tin, tout):
    """Every (route, fees) pair for the single-hop tin -> tout, one per fee tier.

    Sibling of `_hub_legs`, named for the same reason: the two differ in ARITY -- a direct
    route carries ONE fee, a two-hop an ordered pair -- and `_pack` walks fees alongside
    tokens, so a one-element tuple written `(f)` instead of `(f,)` is not a tuple at all and
    packs a truncated path that quotes some other pool rather than raising.

    ORDER IS LOAD-BEARING and belongs to the caller: these are emitted BEFORE any hub leg so
    the sweep's strict `>` leaves a direct route in place when a two-hop merely ties it.
    """
    return [((tin, tout), (f,)) for f in _FEES]

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
from lat_sel_ext import _selector

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

    def _dz594():
        if _needs_reset_approve(tin):
            ixs.append(_IX(target=tin, value='0', call_data=encode_approve(_ck(_ROUTER), 0), chain_id=chain_id))
    from eth_utils import to_checksum_address as _ck
    from common.abi_utils import encode_approve
    from minotaur_subnet.shared.types import Interaction as _IX
    ixs = []
    _dz594()
    ixs.append(_IX(target=tin, value='0', call_data=encode_approve(_ck(_ROUTER), int(amt)), chain_id=chain_id))
    return ixs

def _build(route, tin, amt, rcpt, chain_id):
    from minotaur_subnet.shared.types import Interaction as _IX
    leg = _swap_leg(route, amt, rcpt)
    return _approves(tin, amt, chain_id) + [_IX(target=_ROUTER, value='0', call_data=leg, chain_id=chain_id)]
from bg124_minota_ext import _amounts
from _mvp_ext import _valid_pair

def _token(p, field):
    return str(p.get(field, '') or '').lower()

def _params(s, intent, state):

    def _dz593():
        tout = _token(p, 'output_token')
        amt, mo = _amounts(p)
        if not _valid_pair(tin, tout, amt):
            return (None,)
        return ((tin, tout, amt, mo),)
        return _DR_UNSET
    p = s._normalized_swap_params(intent, state)
    tin = _token(p, 'input_token')
    _r_dz593 = _dz593()
    if _r_dz593 is not _DR_UNSET:
        return _r_dz593[0]