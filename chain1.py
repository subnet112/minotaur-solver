_DR_UNSET = object()
from chain1_lib import _qroute, _build, _params, _champ_route
from chain1_v2 import _v2_build, _sweep, _v2_best
from bg124_kira_ext import _beats_champ
from bg124_kira_ext_v2 import _meets_min_out
from kira_rr_g1 import _decide

def _mk_plan(route, tin, amt, rcpt, intent, state):
    from minotaur_subnet.shared.types import ExecutionPlan as _EP
    if isinstance(route, tuple) and route and (route[0] == 'v2'):
        ixs = _v2_build(route[1], route[2], tin, amt, route[3], rcpt, 1)
    else:
        ixs = _build(route, tin, amt, rcpt, 1)
    return _EP(intent_id=intent.app_id, interactions=ixs, deadline=9999999999, nonce=state.nonce, metadata={'solver': 'viking-eth-dyn', 'chain_id': 1})

def _rdctx(s, snapshot):
    w3 = s._get_web3(1) or s._get_web3(31337)
    if w3 is None:
        return None
    block = getattr(snapshot, 'block_number', None) if snapshot else None
    block = int(block) if block else 'latest'
    return (w3, block)

def _guards(s, intent, state, snapshot):
    if int(getattr(state, 'chain_id', 0) or 0) != 1:
        return None
    pr = _params(s, intent, state)
    if pr is None:
        return None
    rcpt = getattr(state, 'contract_address', None) or getattr(state, 'owner', None)
    if not rcpt:
        return None
    rd = _rdctx(s, snapshot)
    if rd is None:
        return None
    return (pr, rcpt, rd[0], rd[1])

def superset(s, intent, state, snapshot, base_plan):
    """Chain-1 candidate sweep; a plan only when strictly better than the
    engine's own quoted route by the margin (or the base plan is empty)."""

    def _dz60():
        if g is None:
            return (None,)
        (tin, tout, amt, mo), rcpt, w3, block = g
        base_empty = base_plan is None or not getattr(base_plan, 'interactions', None)
        route = _decide(w3, tin, tout, amt, mo, block, base_empty)
        if route is None:
            return (None,)
        return (_mk_plan(route, tin, amt, rcpt, intent, state),)
        return _DR_UNSET
    try:
        g = _guards(s, intent, state, snapshot)
        _r_dz60 = _dz60()
        if _r_dz60 is not _DR_UNSET:
            return _r_dz60[0]
    except Exception:
        return None