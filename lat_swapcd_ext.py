"""Relocated leaf helper -- _v2_swap_cd, moved out of chain1_v2.py.

Dependency-closed by construction: the body reads no module-level name, so nothing
imports back and no cycle is possible. chain1_v2.py re-imports the name, which keeps it in
that module's namespace and therefore in its `from ... import *` surface.
"""
from __future__ import annotations
_DR_UNSET = object()

def _v2_swap_cd(in_is_t0, out, rcpt):

    def _dz1528():
        return ('0x' + (_keccak(text='swap(uint256,uint256,address,bytes)')[:4] + _enc(['uint256', 'uint256', 'address', 'bytes'], [a0, a1, _ck(rcpt), b''])).hex(),)
        return _DR_UNSET
    from eth_abi import encode as _enc
    from eth_utils import keccak as _keccak, to_checksum_address as _ck
    a0, a1 = (0, int(out)) if in_is_t0 else (int(out), 0)
    _r_dz1528 = _dz1528()
    if _r_dz1528 is not _DR_UNSET:
        return _r_dz1528[0]