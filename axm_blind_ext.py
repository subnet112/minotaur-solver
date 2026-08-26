"""Relocated leaf helper -- _blind, moved out of _apex_ourbase.py.

Dependency-closed by construction: the body reads no module-level name, so nothing
imports back and no cycle is possible. _apex_ourbase.py re-imports the name, which keeps it in
that module's namespace and therefore in its `from ... import *` surface.
"""
from __future__ import annotations

def _blind(plan):
    """The lineage's own no-route sentinel: structurally non-empty but a
    self-declared guess that scores 0 when the default pool doesn't exist."""
    try:
        md = dict(getattr(plan, 'metadata', {}) or {})
    except Exception:
        return False
    return md.get('solver') in ('best-effort', 'offline-fallback') or md.get('route') == 'last_resort_empty'