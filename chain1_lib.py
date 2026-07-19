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
    def _fw1():
        if _WETH not in (tin, tout):
            f1 = _CHAMP_FEE.get(frozenset((tin, _WETH)), 3000)
            f2 = _CHAMP_FEE.get(frozenset((_WETH, tout)), 3000)
            return (((tin, _WETH, tout), (f1, f2)),)
        return (((tin, tout), (3000,)),)
    _fwr1 = _fw1()
    if _fwr1 is not None:
        return _fwr1[0]

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

_MC3 = '0xcA11bde05977b3631167028862bE2a173976CA11'  # Multicall3 (same on all chains)

def _qbytes(route, amt):
    from eth_abi import encode as _enc
    from eth_utils import keccak as _keccak
    tokens, fees = route
    sel = _keccak(text='quoteExactInput(bytes,uint256)')[:4]
    return sel + _enc(['bytes', 'uint256'], [_pack(tokens, fees), int(amt)])

def _qdec(ok, rb):
    """One aggregate3 result decoded exactly as _qroute would: amountOut or None."""
    if not ok:
        return None
    try:
        from eth_abi import decode as _dec
        return _dec(['uint256', 'uint160[]', 'uint32[]', 'uint256'], bytes(rb))[0] or None
    except Exception:
        return None

def _agg3_data(calls):
    from eth_abi import encode as _enc
    from eth_utils import keccak as _keccak, to_checksum_address as _ck
    sel = _keccak(text='aggregate3((address,bool,bytes)[])')[:4]
    arr = [(_ck(t), True, cb) for t, cb in calls]
    return '0x' + (sel + _enc(['(address,bool,bytes)[]'], [arr])).hex()

def _agg3(w3, calls, block):
    """One aggregate3 eth_call for [(target, callbytes)...] at block ->
    [(ok, bytes)...], or None if the batch call itself fails. allowFailure=True
    per sub-call so a reverting (no-pool) quote is ok=False, mirroring _qroute's
    per-candidate try/except -> None. Route selection is unchanged; the whole
    candidate sweep collapses from ~36 individual quotes to 1 round-trip (each
    individual quote is an independent flake chance under bench archive-load)."""
    if not calls:
        return []
    try:
        from eth_abi import decode as _dec
        from eth_utils import to_checksum_address as _ck
        r = w3.eth.call({'to': _ck(_MC3), 'data': _agg3_data(calls)}, block_identifier=block)
        return _dec(['(bool,bytes)[]'], bytes(r))[0]
    except Exception:
        return None

def _swap_leg(route, amt, rcpt):
    from eth_abi import encode as _enc
    from eth_utils import keccak as _keccak, to_checksum_address as _ck
    tokens, fees = route
    sel = _keccak(text='exactInput((bytes,address,uint256,uint256,uint256))')[:4]
    return '0x' + (sel + _enc(['(bytes,address,uint256,uint256,uint256)'], [(_pack(tokens, fees), _ck(rcpt), 9999999999, int(amt), 0)])).hex()

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

def _params(s, intent, state):
    p = s._normalized_swap_params(intent, state)
    tin = str(p.get('input_token', '') or '').lower()
    def _fw1():
        tout = str(p.get('output_token', '') or '').lower()
        amt, mo = _amounts(p)
        if len(tin) != 42 or len(tout) != 42 or amt <= 0 or (tin == tout):
            return (None,)
        return ((tin, tout, amt, mo),)
    _fwr1 = _fw1()
    if _fwr1 is not None:
        return _fwr1[0]
