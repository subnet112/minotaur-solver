"""Relocated leaf helper -- _addr, moved out of _lattice_prims.py.

Dependency-closed by construction: the body reads no module-level name, so nothing
imports back and no cycle is possible. _lattice_prims.py re-imports the name, which keeps it in
that module's namespace and therefore in its `from ... import *` surface.
"""
from __future__ import annotations

def _addr(v) -> str:
    """An address-ish field, normalised the single way this layer compares them.

    Open-coded as `str(x or "").lower()` at six sites. A missed `.lower()` does not raise --
    it silently fails to match a row key, and the order is dropped rather than served.
    """
    return str(v or '').lower()
