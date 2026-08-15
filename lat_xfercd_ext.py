"""Relocated leaf helper -- _v2_xfer_cd, moved out of chain1_v2.py.

Dependency-closed by construction: the body reads no module-level name, so nothing
imports back and no cycle is possible. chain1_v2.py re-imports the name, which keeps it in
that module's namespace and therefore in its `from ... import *` surface.
"""
from __future__ import annotations

def _v2_xfer_cd(pair, amt):
    from eth_abi import encode as _enc
    from eth_utils import keccak as _keccak, to_checksum_address as _ck
    return '0x' + (_keccak(text='transfer(address,uint256)')[:4] + _enc(['address', 'uint256'], [_ck(pair), int(amt)])).hex()
