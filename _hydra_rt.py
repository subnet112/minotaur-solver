"""Route-discovery helpers for the fast delivering plan — pure pool-math + quoter
multicall logic factored out of solver.py. Behavior-identical to the inline
originals; split into small regions and de-duplicated (one Multicall3 addr, one
aggregate3 selector, one raw-multicall helper) so no region is large."""
from __future__ import annotations
_DR_UNSET = object()
from eth_abi import encode as _enc, decode as _dec
from eth_utils import keccak as _kec

def _dz35():
    _MC3 = '0xcA11bde05977b3631167028862bE2a173976CA11'
    _AGG3 = _kec(text='aggregate3((address,bool,bytes)[])')[:4]
    _QUOTER = {1: '0x61fFE014bA17989E743c5F6cB21bF9697530B21e', 8453: '0x3d4e44Eb1374240CE5F1B871ab261CD16335B76a'}
    _WETH = {1: '0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2', 8453: '0x4200000000000000000000000000000000000006'}
    _USDC = {1: '0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48', 8453: '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913'}
    _SEL_SINGLE = bytes.fromhex('c6a5026a')
    _SEL_PATH = bytes.fromhex('cdca1753')
    return (_MC3, _AGG3, _QUOTER, _WETH, _USDC, _SEL_SINGLE, _SEL_PATH)
_MC3, _AGG3, _QUOTER, _WETH, _USDC, _SEL_SINGLE, _SEL_PATH = _dz35()

def _addr(a):
    return bytes.fromhex(a[2:].rjust(40, '0'))

def _single_cd(tin, tout, amt, fee):
    return _SEL_SINGLE + _enc(['(address,address,uint256,uint24,uint160)'], [(tin, tout, amt, fee, 0)])

def _path_cd(tokens, fees, amt):
    b = b''
    for i, t in enumerate(tokens):
        b += _addr(t)
        if i < len(fees):
            b += int(fees[i]).to_bytes(3, 'big')
    return _SEL_PATH + _enc(['bytes', 'uint256'], [b, amt])

def _mc_raw(w3, subs):
    """aggregate3 the subcalls; return the raw [(ok, bytes), ...] result list."""
    agg = _AGG3 + _enc(['(address,bool,bytes)[]'], [subs])
    ret = w3.eth.call({'to': w3.to_checksum_address(_MC3), 'data': '0x' + agg.hex()})
    results, = _dec(['(bool,bytes)[]'], ret)
    return results

def _run_mc_list(w3, subcalls):
    outs = []
    for ok, data in _mc_raw(w3, subcalls):
        v = 0
        if ok and data and (len(data) >= 32):
            try:
                v = _dec(['uint256'], data[:32])[0]
            except Exception:
                v = 0
        outs.append(v)
    return outs

def _fr_direct(w3, q, tin, tout, amt, best):
    tiers = (100, 500, 3000, 10000)
    try:
        outs = _run_mc_list(w3, [(q, True, _single_cd(tin, tout, amt, f)) for f in tiers])
        for f, o in zip(tiers, outs):
            if o > 0 and (best is None or o > best['out']):
                best = {'kind': 'direct', 'fee': f, 'out': o}
    except Exception:
        pass
    return best

def _hub_combos(cid, hub):
    return [(500, 100), (3000, 100), (100, 500), (100, 3000)] if hub == _USDC.get(cid) else [(500, 500), (3000, 3000), (500, 3000), (3000, 500)]

def _fr_hub(w3, q, cid, tin, tout, amt, hub, best):

    def _dz35():
        nonlocal best
        try:
            outs = _run_mc_list(w3, [(q, True, _path_cd([tin, hub, tout], [f1, f2], amt)) for f1, f2 in combos])
            for (f1, f2), o in zip(combos, outs):
                if o > 0 and (best is None or o > best['out']):
                    best = {'kind': '2hop', 'hub': hub, 'f1': f1, 'f2': f2, 'out': o}
        except Exception:
            pass
    combos = _hub_combos(cid, hub)
    _dz35()
    return best

def fast_route(w3, cid, tin, tout, amt):
    """Best route as a cand-ready dict: {kind:'direct',fee,out} or {kind:'2hop',hub,f1,f2,out} or None."""

    def _dz34():
        q = _QUOTER[cid]
        best = _fr_direct(w3, q, tin, tout, amt, None)
        for hub in (_USDC.get(cid), _WETH.get(cid)):
            if not hub or hub.lower() in (tin.lower(), tout.lower()):
                continue
            best = _fr_hub(w3, q, cid, tin, tout, amt, hub, best)
        return (best,)
        return _DR_UNSET
    if cid not in _QUOTER or amt <= 0:
        return None
    _r_dz34 = _dz34()
    if _r_dz34 is not _DR_UNSET:
        return _r_dz34[0]