"""Relocated leaf helper -- _quoted_amount, moved out of chain1_lib.py.

Dependency-closed by construction: the body reads no module-level name, so nothing
imports back and no cycle is possible. chain1_lib.py re-imports the name, which keeps it in
that module's namespace and therefore in its `from ... import *` surface.
"""
from __future__ import annotations

def _quoted_amount(blob):
    from eth_abi import decode as _dec
    return _dec(['uint256', 'uint160[]', 'uint32[]', 'uint256'], blob)[0] or None
