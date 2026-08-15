"""Relocated leaf helper -- _v2_reserves, moved out of chain1_v2.py.

Dependency-closed by construction: the body reads no module-level name, so nothing
imports back and no cycle is possible. chain1_v2.py re-imports the name, which keeps it in
that module's namespace and therefore in its `from ... import *` surface.
"""
from __future__ import annotations

def _v2_reserves(w3, pair, block):
    from eth_abi import decode as _dec
    from eth_utils import keccak as _keccak, to_checksum_address as _ck
    r = w3.eth.call({'to': _ck(pair), 'data': '0x' + _keccak(text='getReserves()')[:4].hex()}, block_identifier=block)
    res = _dec(['uint112', 'uint112', 'uint32'], r)
    return (int(res[0]), int(res[1]))
