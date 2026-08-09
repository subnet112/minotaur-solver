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


# --- UniversalRouter / V4 base-plan detector (shared drop-guard) -----------------------
# viking_sim runs the champion's base plan BARE (no app-proxy / Permit2 context), so a plan
# routed through the Universal Router or a V4 PoolManager UNDER-measures: it sims to a
# phantom-low / phantom-ZERO output while the champion actually delivers on the benchmark.
# A cover that "wins" against that phantom REVERTS on the real benchmark (champion delivers,
# we deliver 0) => a `dropped` regression (the worst outcome — worse than never firing).
# So EVERY cover must DEFER when the base is untrusted. Detection is address-independent via
# the UR `execute` selectors, plus known UR addresses as a belt. A false positive only costs
# a missed fill (safe); a false negative costs a drop — so we bias toward flagging untrusted.
_UNIVERSAL_ROUTERS = {
    "0x6ff5693b99212da76ad316178a184ab56d299b43",  # Uni UniversalRouter (ETH, curve_refresh's known one)
    "0x3fc91a3afd70395cd496c647d5a6cc9d4b2b7fad",  # Uni UniversalRouter v1 (ETH)
    "0x66a9893cc07d91d95644aedd05d03f95e1dba8af",  # Uni UniversalRouter (V4-enabled, ETH)
    "0x198ef79f1f515f02dfe9e3115ed9fc07183f02fc",  # Uni UniversalRouter (Base)
    "0x6ff5693b99212da76ad316178a184ab56d299b43",  # (dup ok — set dedupes)
}
_UR_SELECTORS = ("0x3593564c", "0xcac88ea9")  # UniversalRouter execute(bytes,bytes[],uint256) / execute(bytes,bytes[])


def base_untrusted(base) -> bool:
    """True if the champion's base plan routes through the Universal Router / V4 — viking_sim
    can't measure those bare, so any sim comparison against this base is a lie. Covers MUST
    defer (return the champion's plan untouched) when this is True, to avoid phantom-win drops."""
    for ix in (getattr(base, "interactions", None) or []):
        try:
            if str(getattr(ix, "target", "") or "").lower() in _UNIVERSAL_ROUTERS:
                return True
        except Exception:
            pass
        try:
            cd = (getattr(ix, "call_data", "") or "").lower()
            if any(cd.startswith(s) for s in _UR_SELECTORS):
                return True
        except Exception:
            pass
    return False


# --- Cross-chain guard (2026-07-28 SDK change: early cross-chain functionality) ----------
# The new SDK returns a CrossChainPlan / MultiLegPlan for cross-chain intents — it has `legs`
# + `bridge_requests` (or `forward_legs`), NOT a single-chain `interactions` list. The platform
# compiles the bridge/escrow; solvers only DECLARE the cross-chain need. Our covers exclusively
# route SINGLE-CHAIN swaps: if one fires on a cross-chain base it would (a) misread "no
# interactions" as "champion delivered nothing" and (b) override a valid multi-leg plan with a
# bogus one-chain swap => a corrupt plan / drop. So every cover MUST defer on these. Structural
# marker check (no import of harness code, works whatever the champion version): any of these
# attrs => cross-chain. A plain single-chain ExecutionPlan has only `interactions` => False.
_CROSSCHAIN_MARKERS = ("legs", "bridge_requests", "forward_legs", "rollback_legs",
                       "src_chain_id", "dst_chain_id", "revert_legs")


def is_cross_chain(base) -> bool:
    """True if the champion returned a cross-chain / multi-leg plan (not a single-chain
    ExecutionPlan). Covers defer to the champion — the platform owns bridge compilation."""
    if base is None:
        return False                       # None base = nothing single-chain; blind-fill still safe
    try:
        if getattr(base, "is_cross_chain", False):
            return True
        for m in _CROSSCHAIN_MARKERS:
            if hasattr(base, m):
                return True
    except Exception:
        return True                        # anything unexpected on the base object -> defer (safe)
    return False
