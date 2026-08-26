"""Pure calldata encoders + return decoders for the venue quoting layer.

Split out of `venues` for the same reason `consts` was: a module top level is
itself a region and every top-level def header counts in it, so parking the
encode/decode pairs beside the I/O pushed `venues.<module>` past the largest
region in the tree. Nothing here touches the network or the clock, which is also
why the batched scan can share it -- a quote assembled here is byte-identical
whether it is sent on its own (`venues.q_*`) or inside an aggregate3 batch
(`venue_batch`). One encoder per venue, one decoder per return shape, no branches.
"""
from __future__ import annotations
from eth_abi import encode as _enc, decode as _dec
from consts import S_QUOTE_SINGLE, S_QUOTE_PATH, S_V2_AMOUNTS, S_AERO_GAO

def _v3_path_bytes(tokens, fees):
    b = bytes.fromhex(tokens[0][2:])
    for i, f in enumerate(fees):
        b += int(f).to_bytes(3, 'big') + bytes.fromhex(tokens[i + 1][2:])
    return b

def _cd_v3_single(tin, tout, amt, fee):
    return '0x' + S_QUOTE_SINGLE + _enc(['(address,address,uint256,uint24,uint160)'], [(tin, tout, int(amt), int(fee), 0)]).hex()

def _cd_v3_path(tokens, fees, amt):
    return '0x' + S_QUOTE_PATH + _enc(['bytes', 'uint256'], [_v3_path_bytes(tokens, fees), int(amt)]).hex()

def _cd_v2(path, amt):
    return '0x' + S_V2_AMOUNTS + _enc(['uint256', 'address[]'], [int(amt), path]).hex()

def _cd_aero(routes, amt):
    return '0x' + S_AERO_GAO + _enc(['uint256', '(address,address,bool,address)[]'], [int(amt), routes]).hex()

def _dec_u256(r):
    """Single uint256 return (the v3 quoter). 0 on revert/short/garbage."""
    if not r:
        return 0
    try:
        return int(_dec(['uint256'], r[:32])[0])
    except Exception:
        return 0

def _dec_last(r):
    """Final element of a uint256[] return (v2 / Aerodrome getAmountsOut)."""
    if not r:
        return 0
    try:
        outs = _dec(['uint256[]'], r)[0]
        return int(outs[-1]) if outs else 0
    except Exception:
        return 0