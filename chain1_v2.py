# chain-1 dynamic tier: v2-pair helpers + candidate sweep
from chain1_c import _V2_PAIRS, _MAX_QUOTES
from chain1_lib import _candidates, _qroute

def _v2_reserves(w3, pair, block):
    from eth_abi import decode as _dec
    from eth_utils import keccak as _keccak, to_checksum_address as _ck
    r = w3.eth.call({'to': _ck(pair), 'data': '0x' + _keccak(text='getReserves()')[:4].hex()}, block_identifier=block)
    res = _dec(['uint112', 'uint112', 'uint32'], r)
    return (int(res[0]), int(res[1]))

def _v2_quote(w3, pair, amt, in_is_t0, block):
    try:
        res = _v2_reserves(w3, pair, block)
        rin, rout = (res[0], res[1]) if in_is_t0 else (res[1], res[0])
        ai = int(amt) * 997
        return ((ai * rout) // (rin * 1000 + ai)) or None
    except Exception:
        return None

def _v2_lookup(tin, tout):
    ent = _V2_PAIRS.get(frozenset((tin, tout)))
    if not ent:
        return None
    pair, t0 = ent
    return (pair, tin == t0)

def _v2_swap_cd(in_is_t0, out, rcpt):
    from eth_abi import encode as _enc
    from eth_utils import keccak as _keccak, to_checksum_address as _ck
    a0, a1 = (0, int(out)) if in_is_t0 else (int(out), 0)
    return '0x' + (_keccak(text='swap(uint256,uint256,address,bytes)')[:4] + _enc(['uint256', 'uint256', 'address', 'bytes'], [a0, a1, _ck(rcpt), b''])).hex()

def _v2_xfer_cd(pair, amt):
    from eth_abi import encode as _enc
    from eth_utils import keccak as _keccak, to_checksum_address as _ck
    return '0x' + (_keccak(text='transfer(address,uint256)')[:4] + _enc(['address', 'uint256'], [_ck(pair), int(amt)])).hex()

def _v2_build(pair, in_is_t0, tin, amt, out, rcpt, chain_id):
    from minotaur_subnet.shared.types import Interaction as _IX
    return [_IX(target=tin, value='0', call_data=_v2_xfer_cd(pair, amt), chain_id=chain_id), _IX(target=pair, value='0', call_data=_v2_swap_cd(in_is_t0, out, rcpt), chain_id=chain_id)]

def _sweep(w3, tin, tout, amt, block):
    best, n = None, 0
    for cand in _candidates(tin, tout):
        if n >= _MAX_QUOTES:
            break
        n += 1
        q = _qroute(w3, cand, amt, block)
        if q and (best is None or q > best[0]):
            best = (q, cand)
    return best

def _v2_best(w3, tin, tout, amt, block, best):
    v2 = _v2_lookup(tin, tout)
    if v2 is not None:
        q2 = _v2_quote(w3, v2[0], amt, v2[1], block)
        if q2 and (best is None or q2 > best[0]):
            best = (q2, ('v2', v2[0], v2[1], q2))
    return best
