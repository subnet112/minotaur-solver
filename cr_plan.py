"""Plan assembly + param normalization for the solver. Split from solver.py so
its module region stays small (each top-level def header counts there).
"""
from __future__ import annotations

import cr_venues as venues
from minotaur_subnet.shared.types import ExecutionPlan, Interaction

def _param_src(state) -> dict:
    """raw_params is canonical; extra is the compatibility view."""
    return dict(getattr(state, "raw_params", None) or {}) or \
        dict(getattr(state, "extra", None) or {})


def _safe_params(intent, state):
    """_params, but never raises — a malformed state yields None, not a crash."""
    try:
        return _params(intent, state)
    except Exception:
        return None


def _recipient(state, src) -> str:
    """The intent CONTRACT receives the swap output (king_base.py:1298)."""
    return str(getattr(state, "contract_address", "")
               or src.get("receiver") or getattr(state, "owner", "") or "")


def _params(intent, state) -> dict:
    """Normalize the swap params off IntentState."""
    src = _param_src(state)
    return {
        "tin": str(src.get("input_token") or ""),
        "tout": str(src.get("output_token") or ""),
        "amount": int(src.get("input_amount") or 0),
        "min_out": int(src.get("min_output_amount") or 0),
        "recipient": _recipient(state, src),
        "chain_id": int(getattr(state, "chain_id", 0) or 0),
        "contract": str(getattr(state, "contract_address", "") or "").lower(),
    }


def _meta(base: dict, cand: dict | None) -> dict:
    """Plan metadata. ``expected_output`` is read downstream as the baseline
    hint (king_base.py:1402) — omitting it makes later layers read us as 0.
    """
    meta = dict(base)
    if cand:
        meta.update({
            "route": cand.get("venue"),
            "venue_param": cand.get("param"),
            "expected_output": str(cand.get("out")),
        })
    return meta


def _ix(i: dict, chain_id: int) -> Interaction:
    """One raw interaction dict -> Interaction (0x-normalized)."""
    return Interaction(
        target=str(i.get("target") or i.get("to") or ""),
        value=str(i.get("value") or "0"),
        call_data=str(i.get("data") or i.get("call_data") or "0x"),
        chain_id=chain_id,
    )


def _plan(intent, state, interactions: list, meta: dict) -> ExecutionPlan:
    """Wrap raw interaction dicts into an ExecutionPlan.

    ``deadline`` is a far-future pin (king_base.py:1402); a 0 reads as expired
    and the plan moves nothing (a drop).
    """
    cid = int(meta.get("chain_id") or 1)
    return ExecutionPlan(
        intent_id=getattr(intent, "app_id", "") or "",
        interactions=[_ix(i, cid) for i in interactions],
        deadline=venues._deadline(),
        nonce=int(getattr(state, "nonce", 0) or 0),
        metadata=meta,
    )



def _valid(p) -> bool:
    """A routable swap: has tokens and a positive amount."""
    return bool(p and p["amount"] > 0 and p["tin"] and p["tout"])


def _base(p) -> dict:
    return {"solver": "clean-router", "chain_id": (p or {}).get("chain_id", 1)}


def _assemble(intent, state, p, got) -> ExecutionPlan:
    """(interactions, cand) -> ExecutionPlan; empty plan when nothing routed."""
    if not got:
        return _plan(intent, state, [], _base(p))
    interactions, cand = got
    return _plan(intent, state, interactions, _meta(_base(p), cand))
