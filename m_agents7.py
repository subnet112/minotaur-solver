"""Relocated leaf helper -- _load_agent_strategies, moved out of _apex_champ.py.

Dependency-closed by construction: the body reads no module-level name, so nothing
imports back and no cycle is possible. _apex_champ.py re-imports the name, which keeps it in
that module's namespace and therefore in its `from ... import *` surface.
"""
from __future__ import annotations

def _load_agent_strategies() -> dict:
    """No agent-strategy blind-spot layer: delivery is fully handled by the
    VikingSolver best-verified-route (multi-venue on-chain + KyberSwap table,
    verified, Base + chain-1). The old runtime module loader is removed — the
    deployed screener rejects dynamic code construction, and the winning champion
    bases carry no such loader. Static no-op: the base's generate_plan sees an
    empty strategy map and falls through to its own plan, which our override
    supersedes anyway."""
    return {}
