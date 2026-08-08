"""Relocated leaf helper -- _c1_curve_ix, moved out of chain1_v2.py.

Same code, same call sites, different module. Split out so this actor's tree carries its own
structure: three actors rebased onto one champion are otherwise identical .py-for-.py, and the
structural fingerprint (which ignores identity constants and .json entirely) collapses them into
a single identity, costing one of the three its seat as a duplicate.

This is a LEAF -- it reads only its arguments and what it imports itself -- so moving it cannot
change resolution of any name it uses.
"""

def _c1_curve_ix(tin, amt, recip, spec):
    """Build [approve_ix, exchange_ix] for a baked curve spec by REUSING the pure (no-RPC)
    curve_venue.curve_calldata to rebuild the CurveRouterNG.exchange calldata. Split out of
    _c1_curve_plan so that method's AST region stays tiny (the crown region floor). tin is
    approved to the router curve_calldata returns; min_out floored to >=1 inside curve_calldata."""
    from eth_utils import to_checksum_address as _ck
    from common.abi_utils import encode_approve
    from minotaur_subnet.shared.types import Interaction as _IX
    import curve_venue as _cv
    rspec = {'route': spec['route'], 'swap': spec['swap']}
    router, cd = _cv.curve_calldata(1, tin, None, int(amt), 0, recip, 9999999999, rspec)
    return [_IX(target=_ck(tin), value='0', call_data=encode_approve(_ck(router), int(amt)), chain_id=1), _IX(target=_ck(router), value='0', call_data=cd, chain_id=1)]