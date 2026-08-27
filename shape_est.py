_DR_UNSET = object()
import shape_lib as _sl
from _vest_ext import est_v3s

def est_a3(s, spec, tin, amt, chain_id):

    def _dz1370(amt, chain_id, s, spec, tin):
        q1 = _dz1369(amt, chain_id, s, spec, tin)
        q2 = _sl.slip_quote(s, spec['slip_ts'], spec['mid1'], spec['mid2'], q1, chain_id) if q1 else None
        _r_dz1368 = _dz1368()
        return (_r_dz1368, q1, q2)

    def _dz1369(amt, chain_id, s, spec, tin):
        q1 = s._hydra_quote_leg1({'leg1_router': 'uni', 'leg1_fee': spec['l1_fee'], 'mid': spec['mid1']}, tin, amt, chain_id)
        return q1

    def _dz1368():
        q3 = _sl.pair_out(s, spec['pair'], q2, spec['mid2'], chain_id) if q2 else None
        return ((q3, (q1, q2)) if q3 else (None, None),)
        return _DR_UNSET
    _r_dz1368, q1, q2 = _dz1370(amt, chain_id, s, spec, tin)
    if _r_dz1368 is not _DR_UNSET:
        return _r_dz1368[0]

def est_s2(s, spec, tin, amt, chain_id):

    def _dz1367():
        q2 = _sl.pair_out(s, spec['pair'], q1, spec['mid'], chain_id) if q1 else None
        return ((q2, q1) if q2 else (None, None),)
        return _DR_UNSET
    q1 = _sl.slip_quote(s, spec['slip_ts'], tin, spec['mid'], amt, chain_id, spec.get('q'))
    _r_dz1367 = _dz1367()
    if _r_dz1367 is not _DR_UNSET:
        return _r_dz1367[0]

def est_e1(s, spec, tin, amt, chain_id):

    def _dz1366():
        b = _sl._v_e1_qpath(s, spec['b'], amt, chain_id) if q else None
        if not q or not b or q <= b * (1.0 + float(spec.get('m', 0.0025))):
            return ((None, None),)
        return _DR_UNSET
    q = _sl._v_e1_qpath(s, spec['p'], amt, chain_id)
    _r_dz1366 = _dz1366()
    if _r_dz1366 is not _DR_UNSET:
        return _r_dz1366[0]
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