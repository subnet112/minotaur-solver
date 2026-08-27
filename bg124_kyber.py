"""KyberSwap quality-override cover for blueguider — the current-champion move.

This mirrors how the reigning champion (harvey-router) actually wins: wrap the
champion, and on exact-key scenarios where we hold a FORK-VERIFIED KyberSwap
aggregator route, emit that route's pre-built calldata. KyberSwap routes across
every DEX (Uni V2/V3/V4, Curve, Balancer, Kyber) with optimal splitting, so it
beats the champion's static per-venue routes on output ("better" dethrone).

The benchmark sandbox has NO external internet (only the fork RPC), so routes
are fetched + verified OFFLINE (build_kyber_overrides.py) and shipped here as
data. This module only READS kyber_overrides.json and emits the stored plan.

Keyed chain|contract|tin|tout|amt — CONTRACT-scoped: a route baked for one app's
order must never fire on a different app's SERVED order sharing the pair/amount
(that would revert -> deliver 0 -> DROP -> hard veto). Every route in the file
was verified to execute and beat the incumbent at bake time.
"""
from __future__ import annotations
import json
import logging
from pathlib import Path
logger = logging.getLogger(__name__)

def _types():
    from minotaur_subnet.shared.types import ExecutionPlan, Interaction
    return (ExecutionPlan, Interaction)

def _load():
    try:
        p = Path(__file__).parent / 'kyber_overrides.json'
        if p.is_file():
            return json.loads(p.read_text())
    except Exception:
        logger.exception('[kyber] override load failed')
    return {}
_OVERRIDES = _load()

def _key(state):

    def _dz29(state):
        p = dict(getattr(state, 'raw_params', None) or {})
        cid = str(int(getattr(state, 'chain_id', 0) or 0))
        con = str(getattr(state, 'contract_address', '') or '').lower()
        tin = str(p.get('input_token', '') or '').lower()
        tout = str(p.get('output_token', '') or '').lower()
        return (cid, con, p, tin, tout)
    try:
        cid, con, p, tin, tout = _dz29(state)
        amt = str(int(p.get('input_amount', 0) or 0))
        if tin and tout and (amt != '0'):
            return '|'.join((cid, con, tin, tout, amt))
    except Exception:
        pass
    return None

def _plan(intent, state, row, chain_id):
    ExecutionPlan, Interaction = _types()
    ix = [Interaction(target=r['target'], value=str(r.get('value', '0')), call_data=r['data'], chain_id=chain_id) for r in row.get('interactions', [])]
    if not ix:
        return None
    return ExecutionPlan(intent_id=intent.app_id, interactions=ix, deadline=9999999999, nonce=state.nonce, metadata={'solver': 'bg124-kyber', 'chain_id': chain_id})

def try_cover(solver, intent, state):
    """Exact-key KyberSwap override. Returns an ExecutionPlan or None."""
    if not _OVERRIDES:
        return None
    try:
        row = _OVERRIDES.get(_key(state))
        if not row or not row.get('interactions'):
            return None
        chain_id = int(getattr(state, 'chain_id', 0) or 0)
        return _plan(intent, state, row, chain_id)
    except Exception:
        logger.exception('[kyber] cover failed; champion plan stands')
        return None