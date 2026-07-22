# SN112 per-shape estimators + gated-row dispatch (split from shape_lib).
import shape_lib as _sl

def est_v3s(s, spec, tin, amt, chain_id):
    return (s._hydra_quote_leg1({'leg1_router': spec.get('router'), 'leg1_fee': spec['fee'], 'mid': spec['tout']}, tin, amt, chain_id), None)

def est_a3(s, spec, tin, amt, chain_id):
    q1 = s._hydra_quote_leg1({'leg1_router': 'uni', 'leg1_fee': spec['l1_fee'], 'mid': spec['mid1']}, tin, amt, chain_id)
    def _fw1():
        q2 = _sl.slip_quote(s, spec['slip_ts'], spec['mid1'], spec['mid2'], q1, chain_id) if q1 else None
        q3 = _sl.pair_out(s, spec['pair'], q2, spec['mid2'], chain_id) if q2 else None
        return ((q3, (q1, q2)) if q3 else (None, None),)
    _fwr1 = _fw1()
    if _fwr1 is not None:
        return _fwr1[0]

def est_s2(s, spec, tin, amt, chain_id):
    q1 = _sl.slip_quote(s, spec['slip_ts'], tin, spec['mid'], amt, chain_id, spec.get('q'))
    q2 = _sl.pair_out(s, spec['pair'], q1, spec['mid'], chain_id) if q1 else None
    return (q2, q1) if q2 else (None, None)

def est_e1(s, spec, tin, amt, chain_id):
    q = _sl._v_e1_qpath(s, spec['p'], amt, chain_id)
    b = _sl._v_e1_qpath(s, spec['b'], amt, chain_id) if q else None
    if not q or not b or q <= b * (1.0 + float(spec.get('m', 0.0025))):
        return (None, None)
    return (q, None)

def est_ss(s, spec, tin, amt, chain_id):
    q = _sl.slip_quote(s, spec['slip_ts'], tin, spec['tout'], amt, chain_id, spec.get('q'))
    return (q, None) if q else (None, None)

def est_sgs(s, spec, tin, amt, chain_id):
    q = _sl._v_sng_dy(s, spec['pool'], spec['i'], spec['j'], amt, chain_id)
    return (q, None) if q else (None, None)

def est_v2p(s, spec, tin, amt, chain_id):
    q = _sl._v_pair_gao(s, spec['pair'], amt, tin, chain_id)
    return (q, None) if q else (None, None)

