# gated-tier evaluation (z / baseline-proxy / margin gates)
import logging
import shape_base as _sba

logger = logging.getLogger('viking')

def _gate_z(s, spec, tin, tout, amt, key, chain_id):
    est, mid_q = s._v_gated_est(dict(spec, tout=tout), tin, amt, chain_id)
    if not est or est <= 0:
        return (None, None)
    logger.info('[viking] GATED zero-base serve %s est=%s', key[:60], est)
    return (est, mid_q)

def _gate_base(s, spec, plan, tin, tout, amt, chain_id):
    base_out = _sba.base_out_av2(s, plan, spec, tin, tout, amt, chain_id) if 'base_mid' in spec else _sba.base_out(s, plan, chain_id)
    def _fw2(base_out=base_out):
        if not base_out and spec.get('bl'):
            qs = [s._hydra_quote_leg1({'leg1_router': rt, 'leg1_fee': fe, 'mid': tout}, tin, amt, chain_id) for rt, fe in spec['bl']]
            base_out = max([q for q in qs if q] or [0]) or None
        return (base_out,)
    base_out, = _fw2()
    return base_out

def _gate_margin(s, spec, plan, tin, tout, amt, key, chain_id):
    base_out = _gate_base(s, spec, plan, tin, tout, amt, chain_id)
    if not base_out:
        return (None, None)
    est, mid_q = s._v_gated_est(dict(spec, tout=tout), tin, amt, chain_id)
    if not est or est <= base_out * 1.002:
        return (None, None)
    logger.info('[viking] GATED override %s est=%s base=%s', key[:60], est, base_out)
    return (est, mid_q)

def gate_est(s, spec, plan, tin, tout, amt, key, chain_id):
    if spec.get('z'):
        return _gate_z(s, spec, tin, tout, amt, key, chain_id)
    return _gate_margin(s, spec, plan, tin, tout, amt, key, chain_id)

def _build_legacy(spec, tin, tout, amt, mid_q, est, rcpt, chain_id):
    import hydra_top as _ht
    import shape_lib3 as _sl3
    def _fw3():
        if spec.get('shape') == 'v3s':
            return (_ht._build_cvx_fb_ix({'alt_router': spec.get('router'), 'alt_fee': spec['fee']}, tin, tout, amt, rcpt, chain_id),)
        if spec.get('shape') == 'a3':
            q1, q2 = mid_q
            return (_sl3.build_a3(spec, tin, tout, amt, q1, q2, est, chain_id)(rcpt),)
    _fwr3 = _fw3()
    if _fwr3 is not None:
        return _fwr3[0]
    return _ht._build_cvx_chain_ix(dict(spec), tin, tout, amt, mid_q, rcpt, chain_id)

def build_gated(s, spec, tin, tout, amt, mid_q, est, rcpt, state, chain_id):
    import shape_est2 as _se
    import shape_build as _sb
    if spec.get('shape') in _se._BUILD_SHAPES:
        return _sb.build_row(s, spec, tin, tout, amt, mid_q, est, rcpt, state, chain_id)
    return _build_legacy(spec, tin, tout, amt, mid_q, est, rcpt, chain_id)

def _dyn_try(s, intent, state, snapshot, venue, param, tin, tout, amount_in, chain_id, q):
    cand = {'venue': venue, 'param': int(param), 'out': int(q), 'gas_est': 160000, 'gas_model': 450000}
    try:
        plan = s._build_singlehop_plan(intent, state, snapshot, cand, tin, tout, amount_in, chain_id)
    except Exception:
        plan = None
    if plan is not None:
        logger.info('[viking] dynamic fallback %s->%s amt=%s via %s/%s out=%s', tin[:8], tout[:8], amount_in, venue, param, q)
    return plan

def dyn_fallback(s, intent, state, snapshot, spec, tin, tout, amount_in):
    from shape_lib import _v_bs_quote
    chain_id = int(getattr(state, 'chain_id', 0) or (getattr(snapshot, 'chain_id', 0) if snapshot else 0) or 0)
    if chain_id != 8453:
        return None
    def _fw1():
        for venue, param in spec:
            q = _v_bs_quote(s, venue, param, tin, tout, amount_in, chain_id)
            if not q or int(q) <= 0:
                continue
            plan = _dyn_try(s, intent, state, snapshot, venue, param, tin, tout, amount_in, chain_id, q)
            if plan is not None:
                return (plan,)
        return (None,)
    _fwr1 = _fw1()
    if _fwr1 is not None:
        return _fwr1[0]
