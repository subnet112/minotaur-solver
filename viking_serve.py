"""Viking serve chain (hoisted from VikingSolver.generate_plan / _v_gated,
behavior-identical): override precedence, gated eval, cached-bar guard,
stale-row engine serve, fill-only-empty."""
import logging
import viking_gate as _vg
from viking_tables import _v_gated_table, _viking_override, _viking_cached_bar, _viking_frozen_index, _viking_replay
from minotaur_subnet.shared.types import ExecutionPlan as _EP
logger = logging.getLogger('solver')

def head_serve(s, intent, state, snapshot):
    key = s._v_swap_key(intent, state)
    return (key, override_serve(s, key, intent, state, snapshot))

def override_serve(s, key, intent, state, snapshot):
    """Unconditional replay serve on scorecard-proven champion-0 keys."""
    if key and key in _viking_override():
        plan = s._v_replay_plan(key, intent, state, snapshot)
        if plan is not None:
            logger.info('[viking] override serve %s', key[:64])
            return plan
    return None

def _plan_sig(plan):
    sig = None
    try:
        sig = frozenset(((str(getattr(i, 'target', '')).lower(), str(getattr(i, 'call_data', '')).lower()) for i in plan.interactions))
    except Exception:
        pass
    return sig

def _bar_hit(s, key, row, bar, intent, state, snapshot):
    rp = s._v_replay_plan(key, intent, state, snapshot)
    if rp is not None:
        logger.info('[viking] cached-bar serve %s (stamp %s >= bar %s)', key[:64], row.get('out'), bar)
    return rp

def _bar_serve(s, key, row, plan, bar, intent, state, snapshot):
    """Replay serve when the fresh row's stamp meets the champion's cached bar
    and the base plan is NOT a frozen-table serve (those wei-tie by construction)."""
    import time as _time
    fresh_row = _time.time() - float(row.get('at') or 0) <= s._V_ROW_FRESH_S

    def _fw3():
        if not (fresh_row and int(row.get('out') or 0) >= bar):
            return (None,)
        sig = _plan_sig(plan)
        if sig is None or sig not in _viking_frozen_index().get(key, []):
            return (_bar_hit(s, key, row, bar, intent, state, snapshot),)
        return (None,)
    _fwr3 = _fw3()
    if _fwr3 is not None:
        return _fwr3[0]

def nonempty_serve(s, key, row, plan, intent, state, snapshot):
    bar = _viking_cached_bar(key)
    if bar and row:
        rp = _bar_serve(s, key, row, plan, bar, intent, state, snapshot)
        if rp is not None:
            return rp
    return plan

def stale_serve(s, key, row, intent, state, snapshot):
    if not row:
        return None
    import time as _time
    age = _time.time() - float(row.get('at') or 0)
    if age > s._V_ROW_FRESH_S:
        fresh = s._v_engine_fresh(intent, state, snapshot)
        if fresh is not None:
            logger.info('[viking] stale-row engine serve %s (age %.0fs)', key[:64], age)
            return fresh
    return None

def fill_empty(s, key, plan, intent, state, snapshot):
    rp = s._v_replay_plan(key, intent, state, snapshot)
    if rp is not None:
        logger.info('[viking] fill-empty serve %s', key[:64])
        return rp
    dyn = s._v_dynamic_fallback(intent, state, snapshot)
    if dyn is not None:
        return dyn
    return plan

def tail_serve(s, key, plan, intent, state, snapshot):
    """Post-superset serve order: non-empty base -> cached-bar guard/base;
    empty base -> stale-row engine, replay fill, dynamic fallback, base."""
    row = _viking_replay().get(key) if key else None
    if not s._v_is_empty(plan):
        return nonempty_serve(s, key, row, plan, intent, state, snapshot)
    sv = stale_serve(s, key, row, intent, state, snapshot)
    if sv is not None:
        return sv
    return fill_empty(s, key, plan, intent, state, snapshot)

def _fw1():

    def _gated_gate(s, state, snapshot, plan, key):
        spec = _v_gated_table().get(key or '')
        if spec is None:
            return None
        if (plan is None or s._v_is_empty(plan)) and (not spec.get('z')):
            return None
        chain_id = int(getattr(state, 'chain_id', 0) or (getattr(snapshot, 'chain_id', 0) if snapshot else 0) or 0)
        return None if chain_id not in (8453, 1) else (spec, chain_id)

    def _gated_plan(s, intent, state, spec, tin, tout, amt, mid_q, est, chain_id):
        rcpt = state.contract_address or getattr(state, 'owner', None)
        ixs = _vg.build_gated(s, spec, tin, tout, amt, mid_q, est, rcpt, state, chain_id)
        return _EP(intent_id=intent.app_id, interactions=ixs, deadline=9999999999, nonce=state.nonce, metadata={'solver': 'viking-gated', 'chain_id': chain_id})

    def gated_eval(s, intent, state, snapshot, plan, key):
        hit = _gated_gate(s, state, snapshot, plan, key)
        if hit is None:
            return None
        spec, chain_id = hit

        def _fw2():
            tin, tout, amt_s = key.split('|')
            amt = int(amt_s)
            est, mid_q = _vg.gate_est(s, spec, plan, tin, tout, amt, key, chain_id)
            if not est:
                return (None,)
            return (_gated_plan(s, intent, state, spec, tin, tout, amt, mid_q, est, chain_id),)
        _fwr2 = _fw2()
        if _fwr2 is not None:
            return _fwr2[0]
    globals().update(locals())
_fw1()