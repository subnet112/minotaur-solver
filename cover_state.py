"""Submission-baked feedback state for the veto-safe covers.

Read at RUNTIME by each cover (inside the benchmark sandbox); updated by
automation/feedback.py after every benchmark, so the NEXT submission carries a
tuned margin. Rule: any real-bench regression -> raise the margin -> covers fire
only on bigger, safer sim-edges -> converge to zero regressions. A cover that
keeps regressing can be disabled outright. This is the closed loop:
    bench -> read champ-vs-ours per order -> tighten -> resubmit.
"""
from __future__ import annotations
import json as _json, os as _os
_PATH = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), 'cover_state.json')
_CACHE: dict | None = None

def _load() -> dict:
    """Read cover_state.json ONCE per process.

    The file is baked into the submission image and never mutated at runtime, so
    re-reading it is pure waste. It was being re-opened and re-parsed on EVERY
    `disabled()` / `margin_bps()` call, i.e. twice per order per cover — 244 disk
    reads across a 122-order run, on the exact code path the champion's
    `_RUN_BUDGET_S` governor times. Measured cost: 118.6 ms/run (0.0138% of the
    860 s budget). That is NOT what caused any drop — v0.269.0's harm was on rows
    this layer never touches — but it is free to remove and the governed path
    should carry no avoidable I/O."""
    global _CACHE
    if _CACHE is None:
        try:
            with open(_PATH) as f:
                _CACHE = _json.load(f)
        except Exception:
            _CACHE = {}
    return _CACHE

def margin_bps(default: int=10) -> int:
    """Min bps a cover must beat the champion by (in sim) before it fires."""
    try:
        return int(_load().get('margin_bps', default))
    except Exception:
        return default

def disabled(name: str) -> bool:
    """True if this cover has been turned off by the feedback loop."""
    try:
        return name in (_load().get('disabled') or [])
    except Exception:
        return False
_UNIVERSAL_ROUTERS = {'0x6ff5693b99212da76ad316178a184ab56d299b43', '0x3fc91a3afd70395cd496c647d5a6cc9d4b2b7fad', '0x66a9893cc07d91d95644aedd05d03f95e1dba8af', '0x198ef79f1f515f02dfe9e3115ed9fc07183f02fc', '0x6ff5693b99212da76ad316178a184ab56d299b43'}
_UR_SELECTORS = ('0x3593564c', '0xcac88ea9')

def base_untrusted(base) -> bool:
    """True if the champion's base plan routes through the Universal Router / V4 — viking_sim
    can't measure those bare, so any sim comparison against this base is a lie. Covers MUST
    defer (return the champion's plan untouched) when this is True, to avoid phantom-win drops."""
    for ix in getattr(base, 'interactions', None) or []:
        try:
            if str(getattr(ix, 'target', '') or '').lower() in _UNIVERSAL_ROUTERS:
                return True
        except Exception:
            pass
        try:
            cd = (getattr(ix, 'call_data', '') or '').lower()
            if any((cd.startswith(s) for s in _UR_SELECTORS)):
                return True
        except Exception:
            pass
    return False
_CROSSCHAIN_MARKERS = ('legs', 'bridge_requests', 'forward_legs', 'rollback_legs', 'src_chain_id', 'dst_chain_id', 'revert_legs')

def is_cross_chain(base) -> bool:
    """True if the champion returned a cross-chain / multi-leg plan (not a single-chain
    ExecutionPlan). Covers defer to the champion — the platform owns bridge compilation."""
    if base is None:
        return False
    try:
        if getattr(base, 'is_cross_chain', False):
            return True
        for m in _CROSSCHAIN_MARKERS:
            if hasattr(base, m):
                return True
    except Exception:
        return True
    return False