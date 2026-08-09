_DR_UNSET = object()
from chain1_lib import _qroute, _build, _params, _champ_route
from chain1_v2 import _v2_build, _sweep, _v2_best
from chain1_rdctx_ext import _rdctx
from chain1_guards_ext import _guards

def _beats_champ(w3, tin, tout, amt, block, q_mine, route):
    croute = _champ_route(tin, tout)
    if route == croute:
        return False
    q_champ = _qroute(w3, croute, amt, block)
    if not q_champ or q_mine * 10000 < q_champ * 10012:
        return False
    return True

def _meets_min_out(q, mo):
    """Whether quote `q` clears the order's declared minimum output.

    `mo > 0` is what separates "no minimum declared" from a floor: _amounts coerces a missing
    or null min_output_amount to 0, and 0 has to mean unset. The clause is redundant as pure
    arithmetic -- a quote is never negative, so `q < 0` could not fire anyway -- but writing
    the intent down is the point. Read without it, the test looks like it enforces a
    zero floor, and the next edit to _amounts (a sentinel, a signed value) would silently
    turn every unset order into a rejection with nothing here to contradict it.
    """
    return not (mo > 0 and q < mo)

def _decide(w3, tin, tout, amt, mo, block, base_empty):
    best = _v2_best(w3, tin, tout, amt, block, _sweep(w3, tin, tout, amt, block))
    if best is None:
        return None
    q_mine, route = best
    if not _meets_min_out(q_mine, mo):
        return None
    if not base_empty and (not _beats_champ(w3, tin, tout, amt, block, q_mine, route)):
        return None
    return route

def _mk_plan(route, tin, amt, rcpt, intent, state):
    from minotaur_subnet.shared.types import ExecutionPlan as _EP
    if isinstance(route, tuple) and route and (route[0] == 'v2'):
        ixs = _v2_build(route[1], route[2], tin, amt, route[3], rcpt, 1)
    else:
        ixs = _build(route, tin, amt, rcpt, 1)
    return _EP(intent_id=intent.app_id, interactions=ixs, deadline=9999999999, nonce=state.nonce, metadata={'solver': 'viking-eth-dyn', 'chain_id': 1})

def superset(s, intent, state, snapshot, base_plan):
    """Chain-1 candidate sweep; a plan only when strictly better than the
    engine's own quoted route by the margin (or the base plan is empty)."""

    def _dz43():
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
        _r_dz43 = _dz43()
        if _r_dz43 is not _DR_UNSET:
            return _r_dz43[0]
    except Exception:
        return None