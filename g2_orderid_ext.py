"""Relocated leaf helper -- _bal_order_id32, moved out of g2_codec_base.py.

Dependency-closed by construction: the body reads no module-level name, so nothing
imports back and no cycle is possible. g2_codec_base.py re-imports the name, which keeps it in
that module's namespace and therefore in its `from ... import *` surface.
"""
from __future__ import annotations

def _bal_order_id32(order_id) -> bytes:
    from eth_utils import keccak as _keccak
    s = str(order_id).replace('0x', '')
    try:
        return bytes.fromhex(s.ljust(64, '0'))[:32]
    except ValueError:
        return _keccak(str(order_id).encode())