"""Relocated leaf helper -- _valid_pair, moved out of chain1_lib.py.

Dependency-closed by construction: the body reads no module-level name, so nothing
imports back and no cycle is possible. chain1_lib.py re-imports the name, which keeps it in
that module's namespace and therefore in its `from ... import *` surface.
"""
from __future__ import annotations

def _valid_pair(tin, tout, amt):
    return len(tin) == 42 and len(tout) == 42 and (amt > 0) and (tin != tout)
