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

_PATH = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "cover_state.json")


def _load() -> dict:
    try:
        with open(_PATH) as f:
            return _json.load(f)
    except Exception:
        return {}


def margin_bps(default: int = 10) -> int:
    """Min bps a cover must beat the champion by (in sim) before it fires."""
    try:
        return int(_load().get("margin_bps", default))
    except Exception:
        return default


def disabled(name: str) -> bool:
    """True if this cover has been turned off by the feedback loop."""
    try:
        return name in (_load().get("disabled") or [])
    except Exception:
        return False
