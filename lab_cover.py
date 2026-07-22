"""Fill-only-empty blindfill orchestrator for the labyrinth layer.

Called ONLY when the champion stack returned an empty plan for the order, so
the worst any cover can do is deliver 0 — exactly what the champion delivered
— which scores as a skip, never a regression or drop. A live quote >= the
order's min_output_amount is required before a plan is served.

Quoting goes through the champion's own RPC channel (solver._get_web3) at the
snapshot's PINNED block: quoting external RPCs at `latest` does not reproduce
inside the benchmark (proven by the lineage's own scorecards).
"""
from __future__ import annotations

import logging

from minotaur_subnet.shared.types import ExecutionPlan

import lab_build
import lab_data
import lab_quote

logger = logging.getLogger(__name__)

_MIN_BUDGET_S = 6.0


def _order(state):
    rp = dict(getattr(state, "raw_params", None) or {})
    tin = str(rp.get("input_token", "") or "").lower()
    tout = str(rp.get("output_token", "") or "").lower()
    try:
        amt = int(rp.get("input_amount", 0) or 0)
    except Exception:
        amt = 0
    try:
        mino = int(rp.get("min_output_amount", 0) or 0)
    except Exception:
        mino = 0
    return tin, tout, amt, mino, rp


def _recipient(state, rp):
    r = str(getattr(state, "contract_address", "") or rp.get("receiver", "") or "").lower()
    return r if r.startswith("0x") and len(r) == 42 else None


def _w3_block(solver, snapshot, cid):
    w3 = None
    for c in (cid, 31337):
        try:
            w3 = solver._get_web3(c)
        except Exception:
            w3 = None
        if w3 is not None:
            break
    if w3 is None:
        return None
    block = getattr(snapshot, "block_number", None) if snapshot else None
    try:
        block = int(block) if block else "latest"
    except Exception:
        block = "latest"
    return w3, block


def blindfill(solver, intent, state, snapshot=None):
    """Best live cover plan for a champion-empty order, or None."""
    cid = int(getattr(state, "chain_id", 0) or 0)
    if cid not in lab_data.CH:
        return None
    try:
        if float(getattr(solver, "_dyn_order_budget", None) or 99.0) < _MIN_BUDGET_S:
            return None
    except Exception:
        pass
    tin, tout, amt, mino, rp = _order(state)
    if amt <= 0 or not tin or not tout or tin == tout:
        return None
    recip = _recipient(state, rp)
    if not recip:
        return None
    wb = _w3_block(solver, snapshot, cid)
    if wb is None:
        return None
    w3, block = wb
    try:
        out, cand = lab_quote.best_cover(w3, block, cid, tin, tout, amt)
    except Exception:
        logger.exception("[lab] batch quote failed")
        return None
    min_req = mino if mino > 0 else 1
    if not cand or out < min_req:
        return None
    ix = lab_build.build_ix(cid, cand, tin, amt, min_req, recip)
    if not ix:
        return None
    return ExecutionPlan(
        intent_id=intent.app_id,
        interactions=ix,
        deadline=lab_build.DEADLINE,
        nonce=int(getattr(state, "nonce", 0) or 0),
        metadata={
            "solver": "labyrinth-cover",
            "chain_id": cid,
            "venue": cand["kind"],
            "quoted": str(out),
        },
    )
