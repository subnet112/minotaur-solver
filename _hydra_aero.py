"""Aerodrome Slipstream + V2-fork quoter helpers (factored out of _hydra_rt).
Behavior-identical; small regions."""
from __future__ import annotations
from eth_abi import encode as _enc, decode as _dec
from eth_utils import keccak as _kec
from _hydra_rt import _mc_raw

_AERO_QUOTER = {8453: "0x254cF9E1E6e233aa1AC962CB9B05b2cfeAaE15b0"}
_AERO_TICKS = [1, 50, 100, 200, 2000]
_AQ_SEL = _kec(text="quoteExactInputSingle((address,address,uint256,int24,uint160))")[:4]
_AERO_V2_R = "0xcf77a3ba9a5ca399b7c97c74d54e5b1beb874e43"
_AERO_V2_F = "0x420DD381b31aEf6683db6B902084cB0FFECe40Da"
_UNIV2_R = "0x4752ba5dbc23f44d87826276bf6fd6b1c372ad24"
_AERO_SEL = _kec(text="getAmountsOut(uint256,(address,address,bool,address)[])")[:4]
_UNIV2_SEL = _kec(text="getAmountsOut(uint256,address[])")[:4]


def _aero_parse(res):
    best = None
    for ts, (ok, d) in zip(_AERO_TICKS, res):
        if ok and d and len(d) >= 32:
            try:
                out = _dec(["uint256"], d[:32])[0]
            except Exception:
                continue
            if out > 0 and (best is None or out > best["out"]):
                best = {"ts": ts, "out": out}
    return best


def aero_route(w3, cid, tin, tout, amt):
    """EXACT Aerodrome Slipstream quote via its QuoterV2, batched. {ts, out} or None."""
    q = _AERO_QUOTER.get(cid)
    if not q or amt <= 0:
        return None
    qc = w3.to_checksum_address(q)
    try:
        subs = [(qc, True, _AQ_SEL + _enc(["(address,address,uint256,int24,uint160)"],
                 [(w3.to_checksum_address(tin), w3.to_checksum_address(tout), amt, ts, 0)])) for ts in _AERO_TICKS]
        res = _mc_raw(w3, subs)
    except Exception:
        return None
    return _aero_parse(res)


def _v2_subs(ck, tin, tout, amt):
    subs, meta = [], []
    for stable in (False, True):
        subs.append((ck(_AERO_V2_R), True, _AERO_SEL + _enc(["uint256", "(address,address,bool,address)[]"], [amt, [(ck(tin), ck(tout), stable, ck(_AERO_V2_F))]])))
        meta.append(("aerodrome_v2", stable))
    subs.append((ck(_UNIV2_R), True, _UNIV2_SEL + _enc(["uint256", "address[]"], [amt, [ck(tin), ck(tout)]])))
    meta.append(("uniswap_v2", None))
    return subs, meta


def _v2_parse(meta, res):
    best = None
    for (venue, stable), (ok, d) in zip(meta, res):
        if ok and d:
            try:
                amounts = _dec(["uint256[]"], d)[0]
                out = int(amounts[-1]) if amounts else 0
            except Exception:
                out = 0
            if out > 0 and (best is None or out > best["out"]):
                best = {"venue": venue, "stable": stable, "out": out}
    return best


def v2_route(w3, cid, tin, tout, amt):
    """Best V2-fork route (Aerodrome V2 volatile/stable + Uniswap V2), fast getAmountsOut. Base only."""
    if cid != 8453 or amt <= 0:
        return None
    ck = w3.to_checksum_address
    subs, meta = _v2_subs(ck, tin, tout, amt)
    try:
        res = _mc_raw(w3, subs)
    except Exception:
        return None
    return _v2_parse(meta, res)
