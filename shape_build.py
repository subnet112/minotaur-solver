import shape_lib2 as _sl2
import shape_lib3 as _sl3

def _b_e1(c):
    return _sl2._v_build_e1(c[1], c[2], c[4], c[9])(c[7])

def _b_s2(c):
    return _sl3.build_s2(c[1], c[2], c[3], c[4], c[5], c[6], c[9])(c[7])

def _b_ss(c):
    return _sl2._v_build_ss(c[1], c[2], c[3], c[4], c[9])(c[7])

def _b_vs2(c):
    return _sl3._v_build_vs2(c[1], c[2], c[3], c[4], c[5], c[9])(c[7])

def _b_sg2(c):
    return _sl2._v_build_sg2(c[1], c[2], c[3], c[4], c[5], c[9])(c[7])

def _b_gs2(c):
    ea = getattr(c[8], 'account', None) or c[7]
    return _sl2._v_build_gs2(c[1], c[2], c[3], c[4], c[5], ea, c[9])(c[7])

def _b_sv3(c):
    ea = getattr(c[8], 'account', None) or c[7]
    return _sl3._v_build_sv3(c[1], c[2], c[3], c[4], c[5], ea, c[9])(c[7])

def _b_sgs(c):
    return _sl2._v_build_sgs(c[1], c[2], c[3], c[4], c[9])(c[7])

def _b_v2p(c):
    return _sl3._v_build_v2p(c[1], c[2], c[3], c[4], c[6], c[9])(c[7])

def _b_p2(c):
    return _sl3._v_build_p2(c[1], c[2], c[3], c[4], c[6], c[9])(c[7])
_V_BUILD = {'e1': _b_e1, 's2': _b_s2, 'ss': _b_ss, 'vs2': _b_vs2, 'sg2': _b_sg2, 'gs2': _b_gs2, 'sv3': _b_sv3, 'sgs': _b_sgs, 'v2p': _b_v2p, 'p2': _b_p2}

def build_row(s, spec, tin, tout, amt, mid_q, est, rcpt, state, chain_id):
    return _V_BUILD[spec['shape']]((s, spec, tin, tout, amt, mid_q, est, rcpt, state, chain_id))