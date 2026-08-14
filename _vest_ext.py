"""Relocated leaf helper -- est_v3s, moved out of shape_est.py.

Dependency-closed by construction: the body reads no module-level name, so nothing
imports back and no cycle is possible. shape_est.py re-imports the name, which keeps it in
that module's namespace and therefore in its `from ... import *` surface.
"""
from __future__ import annotations

def est_v3s(s, spec, tin, amt, chain_id):
    return (s._hydra_quote_leg1({'leg1_router': spec.get('router'), 'leg1_fee': spec['fee'], 'mid': spec['tout']}, tin, amt, chain_id), None)
