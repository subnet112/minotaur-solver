"""Relocated leaf helper -- _lift_bal_swap_cd_0, moved out of g2_codec_base.py.

Dependency-closed by construction: the body reads no module-level name, so nothing
imports back and no cycle is possible. g2_codec_base.py re-imports the name, which keeps it in
that module's namespace and therefore in its `from ... import *` surface.
"""
from __future__ import annotations

def _lift_bal_swap_cd_0(_ck, _enc, _keccak, amount, deadline, funds, route, tin, tout):
    """Lifted from _bal_swap_cd: a return-terminated branch, verbatim."""
    sel = _keccak(text='swap((bytes32,uint8,address,address,uint256,bytes),(address,bool,address,bool),uint256,uint256)')[:4]
    single = (bytes.fromhex(str(route[1]).replace('0x', '')), 0, _ck(tin), _ck(tout), amount, b'')
    return sel + _enc(['(bytes32,uint8,address,address,uint256,bytes)', '(address,bool,address,bool)', 'uint256', 'uint256'], [single, funds, 0, int(deadline)])