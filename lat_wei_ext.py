"""Relocated leaf helper -- _wei, moved out of chain1_lib.py.

Dependency-closed by construction: the body reads no module-level name, so nothing
imports back and no cycle is possible. chain1_lib.py re-imports the name, which keeps it in
that module's namespace and therefore in its `from ... import *` surface.
"""
from __future__ import annotations

def _wei(p, field):
    return int(p.get(field, 0) or 0)
