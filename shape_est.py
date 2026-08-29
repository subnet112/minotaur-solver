_DR_UNSET = object()
import shape_lib as _sl
from _vest_ext import est_v3s

def est_a3(s, spec, tin, amt, chain_id):

    def _dz1713(amt, chain_id, s, spec, tin):
        q1 = _dz1712(amt, chain_id, s, spec, tin)
        q2 = _sl.slip_quote(s, spec['slip_ts'], spec['mid1'], spec['mid2'], q1, chain_id) if q1 else None
        return (q1, q2)

    def _dz1712(amt, chain_id, s, spec, tin):
        q1 = s._hydra_quote_leg1({'leg1_router': 'uni', 'leg1_fee': spec['l1_fee'], 'mid': spec['mid1']}, tin, amt, chain_id)
        return q1

    def _dz1711():
        q3 = _sl.pair_out(s, spec['pair'], q2, spec['mid2'], chain_id) if q2 else None
        return ((q3, (q1, q2)) if q3 else (None, None),)
        return _DR_UNSET
    q1, q2 = _dz1713(amt, chain_id, s, spec, tin)
    _r_dz1711 = _dz1711()
    if _r_dz1711 is not _DR_UNSET:
        return _r_dz1711[0]

def est_s2(s, spec, tin, amt, chain_id):

    def _dz1710():
        q2 = _sl.pair_out(s, spec['pair'], q1, spec['mid'], chain_id) if q1 else None
        return ((q2, q1) if q2 else (None, None),)
        return _DR_UNSET
    q1 = _sl.slip_quote(s, spec['slip_ts'], tin, spec['mid'], amt, chain_id, spec.get('q'))
    _r_dz1710 = _dz1710()
    if _r_dz1710 is not _DR_UNSET:
        return _r_dz1710[0]

def est_e1(s, spec, tin, amt, chain_id):

    def _dz1709(amt, chain_id, s, spec):
        q = _sl._v_e1_qpath(s, spec['p'], amt, chain_id)
        b = _sl._v_e1_qpath(s, spec['b'], amt, chain_id) if q else None
        _r_dz1708 = _dz1708()
        return (_r_dz1708, b, q)

    def _dz1708():
        if not q or not b or q <= b * (1.0 + float(spec.get('m', 0.0025))):
            return ((None, None),)
        return ((q, None),)
        return _DR_UNSET
    _r_dz1708, b, q = _dz1709(amt, chain_id, s, spec)
    if _r_dz1708 is not _DR_UNSET:
        return _r_dz1708[0]

def est_ss(s, spec, tin, amt, chain_id):
    q = _sl.slip_quote(s, spec['slip_ts'], tin, spec['tout'], amt, chain_id, spec.get('q'))
    return (q, None) if q else (None, None)

def est_sgs(s, spec, tin, amt, chain_id):
    q = _sl._v_sng_dy(s, spec['pool'], spec['i'], spec['j'], amt, chain_id)
    return (q, None) if q else (None, None)

def est_v2p(s, spec, tin, amt, chain_id):
    q = _sl._v_pair_gao(s, spec['pair'], amt, tin, chain_id)
    return (q, None) if q else (None, None)