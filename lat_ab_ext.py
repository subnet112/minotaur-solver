"""Relocated leaf helper -- _addr_bytes, moved out of chain1_lib.py.

Dependency-closed by construction: the body reads no module-level name, so nothing
imports back and no cycle is possible. chain1_lib.py re-imports the name, which keeps it in
that module's namespace and therefore in its `from ... import *` surface.
"""
from __future__ import annotations

def _addr_bytes(t):
    return bytes.fromhex(t[2:])
