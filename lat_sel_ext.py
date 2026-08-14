"""Relocated leaf helper -- _selector, moved out of chain1_lib.py.

Dependency-closed by construction: the body reads no module-level name, so nothing
imports back and no cycle is possible. chain1_lib.py re-imports the name, which keeps it in
that module's namespace and therefore in its `from ... import *` surface.
"""
from __future__ import annotations

def _selector(sig):
    from eth_utils import keccak as _keccak
    return _keccak(text=sig)[:4]
