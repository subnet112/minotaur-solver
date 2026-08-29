"""Relocated leaf helper -- _res_call, moved out of shape_lib.py.

Dependency-closed by construction: the body reads no module-level name, so nothing
imports back and no cycle is possible. shape_lib.py re-imports the name, which keeps it in
that module's namespace and therefore in its `from ... import *` surface.
"""
from __future__ import annotations

def _res_call(s, pair, chain_id):

    def _dz1527(pair, w3):
        res = _dec(['uint112', 'uint112', 'uint32'], w3.eth.call({'to': _ck(pair), 'data': '0x' + _keccak(text='getReserves()')[:4].hex()}))
        return res
    from eth_abi import decode as _dec
    from eth_utils import keccak as _keccak, to_checksum_address as _ck
    w3 = s._get_web3(int(chain_id))
    if w3 is None:
        return None
    res = _dz1527(pair, w3)
    return (int(res[0]), int(res[1]))