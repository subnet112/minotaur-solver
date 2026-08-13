"""Relocated leaf helper -- _rd, moved out of viking_sim.py.

Dependency-closed by construction: the body reads no module-level name, so nothing
imports back and no cycle is possible. viking_sim.py re-imports the name, which keeps it in
that module's namespace and therefore in its `from ... import *` surface.
"""
from __future__ import annotations

def _rd(c):
    return int(c.get('returnData') or '0x0', 16)
