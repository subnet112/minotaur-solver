# chain-1 dynamic tier: decision + entry
from chain1_lib import _qroute, _build, _params, _champ_route
from chain1_v2 import _v2_build, _sweep, _v2_best

def _beats_champ(w3, tin, tout, amt, block, q_mine, route):
    croute = _champ_route(tin, tout)
    if route == croute:
        return False
    q_champ = _qroute(w3, croute, amt, block)
    if not q_champ or q_mine * 10000 < q_champ * 10012:
        return False
    return True

def _decide(w3, tin, tout, amt, mo, block, base_empty):
    best = _v2_best(w3, tin, tout, amt, block, _sweep(w3, tin, tout, amt, block))
    if best is None:
        return None
    q_mine, route = best
    if mo > 0 and q_mine < mo:
        return None
    if not base_empty and not _beats_champ(w3, tin, tout, amt, block, q_mine, route):
        return None
    return route

def _mk_plan(route, tin, amt, rcpt, intent, state):
    from minotaur_subnet.shared.types import ExecutionPlan as _EP
    if isinstance(route, tuple) and route and route[0] == 'v2':
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
    return w3, block

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
    return pr, rcpt, rd[0], rd[1]

def superset(s, intent, state, snapshot, base_plan):
    """Chain-1 candidate sweep; a plan only when strictly better than the
    engine's own quoted route by the margin (or the base plan is empty)."""
    try:
        g = _guards(s, intent, state, snapshot)
        if g is None:
            return None
        (tin, tout, amt, mo), rcpt, w3, block = g
        base_empty = base_plan is None or not getattr(base_plan, 'interactions', None)
        route = _decide(w3, tin, tout, amt, mo, block, base_empty)
        if route is None:
            return None
        return _mk_plan(route, tin, amt, rcpt, intent, state)
    except Exception:
        return None
