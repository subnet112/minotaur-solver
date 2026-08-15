"""Relocated leaf helper -- _addr, moved out of curve_venue.py.

Dependency-closed by construction: the body reads no module-level name, so nothing
imports back and no cycle is possible. curve_venue.py re-imports the name, which keeps it in
that module's namespace and therefore in its `from ... import *` surface.
"""
from __future__ import annotations

def _addr(r):
    return '0x' + r[-20:].hex() if r is not None and len(r) >= 32 else None
