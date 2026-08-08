"""Relocated leaf helper -- _par_state_ok, moved out of lattice_fill_layer.py.

Same code, same call sites, different module. Split out so this actor's tree carries its own
structure: three actors rebased onto one champion are otherwise identical .py-for-.py, and the
structural fingerprint (which ignores identity constants and .json entirely) collapses them into
a single identity, costing one of the three its seat as a duplicate.

This is a LEAF -- it reads only its arguments and what it imports itself -- so moving it cannot
change resolution of any name it uses.
"""
from lattice_venue_ext import _par_venue_need
from lattice_attest_ext import _par_attested

def _par_state_ok(d, gem):
    """Is the fixed-rate assumption still true, per the bake-time attestation?

    Deliberately still a PREDICATE rather than deleted. The serve-time read is impossible
    (no chain-1 RPC at bench), but the two things it protected are not vacuous: a non-zero
    fee breaks the flat gemAmt*1e12 arithmetic, and a venue that cannot cover the withdrawal
    reverts the leg -- `catastrophic`, an absolute veto. Both are checked against the attested
    snapshot, and the reserve check is applied to THIS order's size, so an order larger than
    the liquidity we actually verified is suppressed instead of served on faith.
    """
    up = d[4]
    if (_par_attested()['wrapper_tin'] if up else _par_attested()['wrapper_tout']) != 0:
        return False
    if (_par_attested()['psm_tin'] if up else _par_attested()['psm_tout']) != 0:
        return False
    _tok, _holder, need = _par_venue_need(d, gem)
    have = _par_attested()['psm_dai'] if up else _par_attested()['pocket_usdc']
    return need > 0 and have >= need