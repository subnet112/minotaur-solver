"""Relocated leaf helper -- _num, moved out of _lattice_prims.py.

Dependency-closed by construction: the body reads no module-level name, so nothing
imports back and no cycle is possible. _lattice_prims.py re-imports the name, which keeps it in
that module's namespace and therefore in its `from ... import *` surface.
"""
from __future__ import annotations

def _num(v) -> int:
    """An integer field, normalised: never None, never a string. Seven sites."""
    return int(v or 0)
