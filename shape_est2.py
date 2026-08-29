_DR_UNSET = object()
import shape_lib as _sl
from shape_est import est_v3s, est_a3, est_s2, est_e1, est_ss, est_sgs, est_v2p

def est_sg2(s, spec, tin, amt, chain_id):

    def _dz2432(amt, chain_id, s, spec, tin):
        q1 = s._hydra_quote_leg1({'leg1_router': spec.get('l1r') or 'uni', 'leg1_fee': spec['l1_fee'], 'mid': spec['mid']}, tin, amt, chain_id)
        return q1
    q1 = _dz2432(amt, chain_id, s, spec, tin)
    q2 = _sl._v_sng_dy(s, spec['pool'], spec['i'], spec['j'], q1, chain_id) if q1 else None
    return (q2, q1) if q2 else (None, None)

def est_gs2(s, spec, tin, amt, chain_id):

    def _dz2431(amt, chain_id, s, spec):
        q1 = _sl._v_sng_dy(s, spec['pool'], spec['i'], spec['j'], amt, chain_id)
        return q1
    q1 = _dz2431(amt, chain_id, s, spec)
    q2 = s._hydra_quote_leg1({'leg1_router': spec.get('l2r') or 'uni', 'leg1_fee': spec['l2_fee'], 'mid': spec['tout']}, spec['mid'], q1, chain_id) if q1 else None
    return (q2, q1) if q2 else (None, None)

def est_sv3(s, spec, tin, amt, chain_id):

    def _dz2430(amt, chain_id, s, spec, tin):
        q1 = _sl.slip_quote(s, spec['slip_ts'], tin, spec['mid1'], amt, chain_id, spec.get('q'))
        _r_dz294 = _dz294()
        return (_r_dz294, q1)

    def _dz294():

        def _dz2427():
            q2 = _dz2426()
            q3 = s._hydra_quote_leg1({'leg1_router': 'uni', 'leg1_fee': spec['f3'], 'mid': spec['tout']}, spec['mid2'], q2, chain_id) if q2 else None
            return (q2, q3)

        def _dz2426():
            q2 = s._hydra_quote_leg1({'leg1_router': 'uni', 'leg1_fee': spec['f2'], 'mid': spec['mid2']}, spec['mid1'], q1, chain_id) if q1 else None
            return q2
        q2, q3 = _dz2427()
        return ((q3, q1) if q3 else (None, None),)
        return _DR_UNSET
    _r_dz294, q1 = _dz2430(amt, chain_id, s, spec, tin)
    if _r_dz294 is not _DR_UNSET:
        return _r_dz294[0]

def est_vs2(s, spec, tin, amt, chain_id):

    def _dz2429(amt, chain_id, s, spec, tin):
        q1 = s._hydra_quote_leg1({'leg1_router': spec.get('l1_router') or 'uni', 'leg1_fee': spec['l1_fee'], 'mid': spec['mid']}, tin, amt, chain_id)
        return q1
    q1 = _dz2429(amt, chain_id, s, spec, tin)
    q2 = _sl.slip_quote(s, spec['slip_ts'], spec['mid'], spec['tout'], q1, chain_id, spec.get('q')) if q1 else None
    return (q2, q1) if q2 else (None, None)

def est_p2(s, spec, tin, amt, chain_id):

    def _dz2428(amt, chain_id, s, spec, tin):
        q1 = s._hydra_quote_leg1({'leg1_router': 'pancake', 'leg1_fee': spec['l1_fee'], 'mid': spec['mid']}, tin, amt, chain_id)
        return q1
    q1 = _dz2428(amt, chain_id, s, spec, tin)
    q2 = _sl._v_v2_out(s, spec['pair'], q1, bool(spec.get('mid_is_t0')), chain_id) if q1 else None
    return (q2, q1) if q2 else (None, None)
_V_EST = {'v3s': est_v3s, 'a3': est_a3, 's2': est_s2, 'e1': est_e1, 'ss': est_ss, 'sgs': est_sgs, 'v2p': est_v2p, 'sg2': est_sg2, 'gs2': est_gs2, 'sv3': est_sv3, 'vs2': est_vs2, 'p2': est_p2}
_BUILD_SHAPES = ('s2', 'ss', 'p2', 'vs2', 'sg2', 'sgs', 'gs2', 'sv3', 'v2p', 'e1')